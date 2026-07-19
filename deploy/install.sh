#!/usr/bin/env bash
# Idempotent installer for Ubuntu 24.04 LTS (ARM64 / Graviton) on AWS EC2.
# Sets up: pyenv + Python 3.12.4, redis-server, ifuensan/bitnodes (crawler),
# ifuensan/alt-bitnodes (dashboard), systemd units.
#
# Usage (as the ubuntu user):
#   curl -fsSL https://raw.githubusercontent.com/ifuensan/alt-bitnodes/main/deploy/install.sh | bash
# or after scp'ing this file:
#   bash install.sh

set -euo pipefail

CRAWLER_REPO="https://github.com/ifuensan/bitnodes.git"
CRAWLER_BRANCH="feat/i2p-sam-crawl"
DASHBOARD_REPO="https://github.com/ifuensan/alt-bitnodes.git"

INSTALL_USER="${SUDO_USER:-${USER}}"
INSTALL_HOME="$(getent passwd "${INSTALL_USER}" | cut -d: -f6)"
CRAWLER_DIR="${INSTALL_HOME}/bitnodes"
DASHBOARD_DIR="${INSTALL_HOME}/alt-bitnodes"
PYENV_ROOT="${INSTALL_HOME}/.pyenv"
PYTHON_VERSION="3.12.4"
USER_AGENT="${BITNODES_USER_AGENT:-/alt-bitnodes:0.1/}"
# Extra Tor instances (tor@bitnodes1..N on SocksPorts 9051..905N) besides the
# distro default on 9050. Tor is single-threaded; the crawler spreads onion
# dials across every proxy listed in tor_proxies.
TOR_POOL_SIZE=8

log() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }

require_root() { [[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }; }

install_apt_packages() {
  log "Installing apt packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libncursesw5-dev xz-utils tk-dev libxml2-dev \
    libxmlsec1-dev libffi-dev liblzma-dev curl wget git ca-certificates \
    redis-server sqlite3 tor nginx
  systemctl enable --now redis-server
  systemctl enable --now tor
}

setup_i2pd() {
  log "Installing i2pd (I2P router with SAM bridge)"
  if ! command -v i2pd >/dev/null; then
    add-apt-repository -y ppa:purplei2p/i2pd >/dev/null
    apt-get update -qq
    apt-get install -y -qq i2pd
  fi
  systemctl enable --now i2pd
  # SAM is enabled by default on 127.0.0.1:7656 in current i2pd. Verify with
  # a bounded wait; warn-only because I2P is a best-effort ring and a broken
  # SAM must not block clearnet/Tor deploys.
  local i
  for i in $(seq 1 15); do
    if ss -ltn "sport = :7656" | grep -q 7656; then
      log "i2pd SAM bridge listening on 7656"
      return
    fi
    sleep 2
  done
  echo "WARNING: i2pd SAM bridge not listening on 7656; I2P dials will fail" >&2
}

# Everything that, if changed, requires a bitnodes.service restart. Restarts
# kill ~12k live connections and cost hours of snapshot ramp-up, so deploys
# that don't touch the crawler must leave it running (see
# crawler-systemd-units spec).
crawler_fingerprint() {
  {
    git -C "${CRAWLER_DIR}" rev-parse HEAD 2>/dev/null
    cat "${CRAWLER_DIR}"/conf/*.f9beb4d9.conf 2>/dev/null
    cat "${CRAWLER_DIR}/run-bitnodes.sh" 2>/dev/null
    cat /etc/systemd/system/bitnodes.service 2>/dev/null
  } | sha256sum | cut -d' ' -f1
}

# Set key to value in a single-section crawler conf, appending if the key
# does not exist yet (live conf files may predate newer keys).
ensure_conf_key() {
  local file="$1" key="$2" value="$3"
  if grep -q "^${key} *=" "${file}"; then
    sudo -u "${INSTALL_USER}" sed -i "s|^${key} *=.*|${key} = ${value}|" "${file}"
  else
    printf '\n%s = %s\n' "${key}" "${value}" | sudo -u "${INSTALL_USER}" tee -a "${file}" >/dev/null
  fi
}

setup_tor_pool() {
  log "Provisioning Tor SOCKS pool (tor@bitnodes1..${TOR_POOL_SIZE})"
  # Tor is single-threaded: each daemon tops out at ~1 core regardless of
  # box-wide idle. A full-day sar showed the c7g.2xlarge at only ~64% busy
  # (36% idle) while onion decayed -- the ceiling was per-daemon thread
  # pressure, not global CPU. The lever is MORE daemons spread across the
  # idle cores, not a lower cap: cap 32 throttled (~12 onions), 1024
  # saturated per-thread, 256 starved circuit builds (~40 onions after 8h).
  # 9 daemons (pool 8 + default) at cap 512 use the idle headroom.
  local tor_opts="MaxClientCircuitsPending 512
NumEntryGuards 8"
  local i name port torrc desired
  for i in $(seq 1 "${TOR_POOL_SIZE}"); do
    name="bitnodes${i}"
    port=$((9050 + i))
    torrc="/etc/tor/instances/${name}/torrc"
    [[ -d "/etc/tor/instances/${name}" ]] || tor-instance-create "${name}"
    desired="SocksPort 127.0.0.1:${port}
${tor_opts}"
    if [[ ! -f "${torrc}" ]] || [[ "$(cat "${torrc}")" != "${desired}" ]]; then
      printf '%s\n' "${desired}" > "${torrc}"
      # Full restart, not reload: also clears degraded guard/circuit state.
      systemctl try-restart "tor@${name}" 2>/dev/null || true
    fi
    systemctl enable --now "tor@${name}"
  done

  # Same treatment for the default instance (SocksPort 9050): it shares the
  # crawler workload via tor_proxies.
  if ! grep -q "^# alt-bitnodes crawler tuning" /etc/tor/torrc; then
    printf '\n# alt-bitnodes crawler tuning\n%s\n' "${tor_opts}" >> /etc/tor/torrc
    systemctl try-restart tor@default 2>/dev/null || true
  fi
}

install_pyenv() {
  if [[ -d "${PYENV_ROOT}" ]]; then
    log "pyenv already present"
  else
    log "Installing pyenv"
    sudo -u "${INSTALL_USER}" git clone -q https://github.com/pyenv/pyenv.git "${PYENV_ROOT}"
    sudo -u "${INSTALL_USER}" bash -c "cd '${PYENV_ROOT}' && src/configure && make -C src" >/dev/null
  fi

  local profile="${INSTALL_HOME}/.bashrc"
  if ! grep -q PYENV_ROOT "${profile}"; then
    cat >> "${profile}" <<'EOF'

# pyenv
export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
EOF
    chown "${INSTALL_USER}:${INSTALL_USER}" "${profile}"
  fi

  log "Installing Python ${PYTHON_VERSION}"
  sudo -u "${INSTALL_USER}" "${PYENV_ROOT}/bin/pyenv" install -s "${PYTHON_VERSION}"
}

clone_or_update() {
  local repo="$1" dest="$2" branch="${3:-}"
  if [[ -d "${dest}/.git" ]]; then
    log "Updating ${dest}"
    sudo -u "${INSTALL_USER}" git -C "${dest}" fetch -q origin
    if [[ -n "${branch}" ]]; then
      sudo -u "${INSTALL_USER}" git -C "${dest}" checkout -q "${branch}"
      sudo -u "${INSTALL_USER}" git -C "${dest}" pull -q --ff-only origin "${branch}"
    else
      sudo -u "${INSTALL_USER}" git -C "${dest}" pull -q --ff-only
    fi
  else
    log "Cloning ${repo} -> ${dest}"
    sudo -u "${INSTALL_USER}" git clone -q "${repo}" "${dest}"
    if [[ -n "${branch}" ]]; then
      sudo -u "${INSTALL_USER}" git -C "${dest}" checkout -q "${branch}"
    fi
  fi
}

setup_crawler() {
  clone_or_update "${CRAWLER_REPO}" "${CRAWLER_DIR}" "${CRAWLER_BRANCH}"

  log "Creating crawler venv"
  sudo -u "${INSTALL_USER}" "${PYENV_ROOT}/versions/${PYTHON_VERSION}/bin/python" \
    -m venv "${CRAWLER_DIR}/venv"
  sudo -u "${INSTALL_USER}" "${CRAWLER_DIR}/venv/bin/pip" install -q --upgrade pip
  sudo -u "${INSTALL_USER}" "${CRAWLER_DIR}/venv/bin/pip" install -q -r "${CRAWLER_DIR}/requirements.txt"

  log "Generating crawler configs"
  for f in "${CRAWLER_DIR}/conf"/*.conf.default; do
    base="$(basename "$f" .conf.default)"
    target="${CRAWLER_DIR}/conf/${base}.f9beb4d9.conf"
    if [[ ! -f "${target}" ]]; then
      sudo -u "${INSTALL_USER}" cp "${f}" "${target}"
    fi
  done

  # bitnodes parses config lists one item per line (utils.txt_items), so the
  # pool goes in as indented continuation lines. Deleting any previous
  # continuation lines first keeps re-runs from accumulating duplicates.
  local i tor_proxies="127.0.0.1:9050"
  for i in $(seq 1 "${TOR_POOL_SIZE}"); do
    tor_proxies+="\\n    127.0.0.1:$((9050 + i))"
  done
  for cfg in "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf"; do
    sudo -u "${INSTALL_USER}" sed -i "s|^user_agent = .*|user_agent = ${USER_AGENT}|" "${cfg}"
    sudo -u "${INSTALL_USER}" sed -i '/^tor_proxies =/,/^[^[:space:]]/{/^[[:space:]]/d}' "${cfg}"
    sudo -u "${INSTALL_USER}" sed -i "s|^tor_proxies =.*|tor_proxies = ${tor_proxies}|" "${cfg}"
    sudo -u "${INSTALL_USER}" sed -i "s|^socket_timeout = .*|socket_timeout = 60|" "${cfg}"
  done

  # c7g.2xlarge: 8 vCPU, 16 GB RAM. Crawler is CPU-bound at handshake
  # parsing, so workers scale ~linearly with vCPU count (rule of thumb:
  # ~150 crawl workers per vCPU). Full onion sampling is served by the
  # Tor pool (6 SocksPorts); a single Tor daemon at sampling 100 caused
  # the 2026-05-12 saturation. Snapshot size == simultaneously open
  # sockets == ping processes x ping.workers, so ping capacity is the
  # snapshot ceiling: 12 procs x 2000 = 24k slots (upstream default is
  # 2000; the old 600 capped snapshots at 7 x 600 = 4.2k).
  sudo -u "${INSTALL_USER}" sed -i \
    -e "s|^workers = .*|workers = 1200|" \
    -e "s|^onion_peers_sampling_rate = .*|onion_peers_sampling_rate = 100|" \
    -e "s|^snapshot_delay = .*|snapshot_delay = 1800|" \
    "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf"
  sudo -u "${INSTALL_USER}" sed -i \
    -e "s|^workers = .*|workers = 2000|" \
    "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf"

  # I2P ring: dial .b32.i2p peers through the local i2pd SAM bridge.
  # ensure_conf_key because live conf files may predate these keys.
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p True
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p_proxies 127.0.0.1:7656
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p_peers_sampling_rate 100
  # Seed the I2P ring: clearnet peers rarely gossip .b32.i2p, so without
  # seeds it never bootstraps. The list ships with the crawler fork.
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p_nodes_file conf/i2p_seeds.txt
  ensure_conf_key "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf" i2p True
  ensure_conf_key "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf" i2p_proxies 127.0.0.1:7656

  sudo -u "${INSTALL_USER}" mkdir -p "${CRAWLER_DIR}/log" "${CRAWLER_DIR}/data"
}

setup_dashboard() {
  clone_or_update "${DASHBOARD_REPO}" "${DASHBOARD_DIR}"

  log "Creating dashboard venv"
  sudo -u "${INSTALL_USER}" "${PYENV_ROOT}/versions/${PYTHON_VERSION}/bin/python" \
    -m venv "${DASHBOARD_DIR}/venv"
  sudo -u "${INSTALL_USER}" "${DASHBOARD_DIR}/venv/bin/pip" install -q --upgrade pip
  sudo -u "${INSTALL_USER}" "${DASHBOARD_DIR}/venv/bin/pip" install -q -r "${DASHBOARD_DIR}/requirements.txt"

  sudo -u "${INSTALL_USER}" mkdir -p "${DASHBOARD_DIR}/data"
}

install_systemd_units() {
  log "Installing systemd units"
  install -m 0644 "${DASHBOARD_DIR}/deploy/bitnodes.service" /etc/systemd/system/bitnodes.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes.service" /etc/systemd/system/alt-bitnodes.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-mcp.service" /etc/systemd/system/alt-bitnodes-mcp.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/geoip-update.service" /etc/systemd/system/geoip-update.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/geoip-update.timer" /etc/systemd/system/geoip-update.timer
  install -m 0644 "${DASHBOARD_DIR}/deploy/export-prune.service" /etc/systemd/system/export-prune.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/export-prune.timer" /etc/systemd/system/export-prune.timer
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-archive.service" /etc/systemd/system/alt-bitnodes-archive.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-archive.timer" /etc/systemd/system/alt-bitnodes-archive.timer
  install -m 0755 "${DASHBOARD_DIR}/deploy/run-bitnodes.sh" "${CRAWLER_DIR}/run-bitnodes.sh"
  chown "${INSTALL_USER}:${INSTALL_USER}" "${CRAWLER_DIR}/run-bitnodes.sh"

  sed -i "s|__USER__|${INSTALL_USER}|g; s|__CRAWLER_DIR__|${CRAWLER_DIR}|g; s|__DASHBOARD_DIR__|${DASHBOARD_DIR}|g; s|__EXPORT_DIR__|${CRAWLER_DIR}/data/export/f9beb4d9|g" \
    /etc/systemd/system/bitnodes.service /etc/systemd/system/alt-bitnodes.service \
    /etc/systemd/system/alt-bitnodes-mcp.service /etc/systemd/system/geoip-update.service \
    /etc/systemd/system/export-prune.service /etc/systemd/system/alt-bitnodes-archive.service

  systemctl daemon-reload
  systemctl enable bitnodes.service alt-bitnodes.service alt-bitnodes-mcp.service
  systemctl enable --now export-prune.timer
  systemctl enable --now alt-bitnodes-archive.timer
  # Dashboard + MCP are stateless: restart on every deploy so re-runs pick up
  # unit-file changes. The crawler is stateful (open sockets, onion circuits):
  # restart only if its inputs changed or it isn't running.
  systemctl restart alt-bitnodes.service alt-bitnodes-mcp.service
  if [[ "$(crawler_fingerprint)" != "${CRAWLER_STATE_BEFORE}" ]] \
      || ! systemctl is-active --quiet bitnodes.service; then
    log "Crawler changed or not running; restarting bitnodes.service"
    systemctl restart bitnodes.service
  else
    log "Crawler unchanged; leaving bitnodes.service untouched"
  fi

  # GeoIP timer only when license key is present. Idempotent: re-running
  # install.sh after the operator drops the key picks it up.
  if [[ -s "${CRAWLER_DIR}/geoip/.maxmind_license_key" ]]; then
    log "MaxMind license key found; enabling weekly GeoIP refresh"
    systemctl enable --now geoip-update.timer
  else
    log "No MaxMind license key at ${CRAWLER_DIR}/geoip/.maxmind_license_key"
    echo "    GeoLite2 .mmdb files will go stale. To enable weekly refresh:"
    echo "      1. Get a free license: https://www.maxmind.com/en/accounts/current/license-key"
    echo "      2. echo 'YOUR_KEY' | sudo -u ${INSTALL_USER} tee ${CRAWLER_DIR}/geoip/.maxmind_license_key"
    echo "      3. sudo chmod 600 ${CRAWLER_DIR}/geoip/.maxmind_license_key"
    echo "      4. Re-run this installer (it'll enable geoip-update.timer)."
    systemctl disable geoip-update.timer 2>/dev/null || true
  fi
}

bootstrap_origin_secret() {
  # Shared secret CloudFront injects as X-Origin-Auth; nginx rejects requests
  # without it. Generated once on first install; rotation is a manual op
  # (delete the file and re-run, then update the CloudFormation parameter).
  local dir=/etc/alt-bitnodes
  local file="${dir}/origin-auth.env"
  install -d -m 0750 -o root -g root "${dir}"
  if [[ ! -f "${file}" ]]; then
    log "Generating ${file}"
    umask 077
    printf 'ORIGIN_AUTH_SECRET=%s\n' "$(openssl rand -hex 32)" > "${file}"
    chmod 0600 "${file}"
    chown root:root "${file}"
  else
    log "${file} already present; leaving as-is"
  fi
  # shellcheck disable=SC1090
  source "${file}"
  export ORIGIN_AUTH_SECRET
}

bootstrap_mcp_token() {
  # Bearer token required by the MCP HTTP transport (alt-bitnodes-mcp.service
  # validates Authorization: Bearer <this>). Owned by the service user so
  # systemd can read it without giving the file world access. Rotation:
  # delete the file and re-run install.sh; the service will pick up the new
  # token on its next restart.
  local dir=/etc/alt-bitnodes
  local file="${dir}/mcp-token"
  install -d -m 0750 -o root -g "${INSTALL_USER}" "${dir}"
  if [[ ! -f "${file}" ]]; then
    log "Generating ${file}"
    umask 077
    # 32 random bytes, base64url-encoded, no newline.
    openssl rand -base64 32 | tr -d '\n=' | tr '/+' '_-' > "${file}"
    chmod 0640 "${file}"
    chown root:"${INSTALL_USER}" "${file}"
    echo "    MCP bearer token written (chmod 0640 root:${INSTALL_USER})"
  else
    log "${file} already present; leaving as-is"
  fi
}

configure_nginx() {
  log "Configuring nginx"
  install -m 0644 "${DASHBOARD_DIR}/deploy/nginx/alt-bitnodes-limits.conf" \
    /etc/nginx/conf.d/alt-bitnodes-limits.conf

  local site=/etc/nginx/sites-available/alt-bitnodes
  # Use a delimiter that won't appear in the secret (hex only) or hostnames.
  sed \
    -e "s|__SERVER_NAME__|origin.hacknodes.xyz pesquisa.hacknodes.xyz _|g" \
    -e "s|__SECRET__|${ORIGIN_AUTH_SECRET}|g" \
    "${DASHBOARD_DIR}/deploy/nginx/alt-bitnodes.conf.template" > "${site}"
  chmod 0644 "${site}"

  ln -sf "${site}" /etc/nginx/sites-enabled/alt-bitnodes
  rm -f /etc/nginx/sites-enabled/default

  nginx -t
  systemctl enable nginx
  systemctl reload nginx
}

install_cloudwatch_agent() {
  log "Installing amazon-cloudwatch-agent"
  local arch deb cfg_target
  arch="$(dpkg --print-architecture)"   # arm64 on Graviton, amd64 otherwise
  deb="/tmp/amazon-cloudwatch-agent.deb"
  if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    curl -fsSL -o "${deb}" \
      "https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/${arch}/latest/amazon-cloudwatch-agent.deb"
    dpkg -i "${deb}"
    rm -f "${deb}"
  fi

  cfg_target="/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"
  install -m 0644 "${DASHBOARD_DIR}/deploy/cloudwatch-agent.json" "${cfg_target}"

  /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 -s -c "file:${cfg_target}"
}

main() {
  require_root
  CRAWLER_STATE_BEFORE="$(crawler_fingerprint)"
  install_apt_packages
  setup_tor_pool
  setup_i2pd
  install_pyenv
  setup_crawler
  setup_dashboard
  bootstrap_origin_secret
  bootstrap_mcp_token
  install_systemd_units
  configure_nginx
  install_cloudwatch_agent

  log "Done"
  echo
  echo "Verify:"
  echo "  systemctl status bitnodes alt-bitnodes alt-bitnodes-mcp"
  echo "  ssh tunnel: ssh -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 <this-host>"
  echo "  open http://localhost:8000   # dashboard"
  echo "  curl -H \"Authorization: Bearer \$(sudo cat /etc/alt-bitnodes/mcp-token)\" http://localhost:8001/mcp/"
}

main "$@"
