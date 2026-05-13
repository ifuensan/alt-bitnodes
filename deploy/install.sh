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
CRAWLER_BRANCH="fix/empty-include-asns"
DASHBOARD_REPO="https://github.com/ifuensan/alt-bitnodes.git"

INSTALL_USER="${SUDO_USER:-${USER}}"
INSTALL_HOME="$(getent passwd "${INSTALL_USER}" | cut -d: -f6)"
CRAWLER_DIR="${INSTALL_HOME}/bitnodes"
DASHBOARD_DIR="${INSTALL_HOME}/alt-bitnodes"
PYENV_ROOT="${INSTALL_HOME}/.pyenv"
PYTHON_VERSION="3.12.4"
USER_AGENT="${BITNODES_USER_AGENT:-/alt-bitnodes:0.1/}"

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
    redis-server tcpdump sqlite3 tor nginx
  systemctl enable --now redis-server
  systemctl enable --now tor
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

  for cfg in "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf"; do
    sudo -u "${INSTALL_USER}" sed -i "s|^user_agent = .*|user_agent = ${USER_AGENT}|" "${cfg}"
    sudo -u "${INSTALL_USER}" sed -i "s|^tor_proxies =.*|tor_proxies = 127.0.0.1:9050|" "${cfg}"
    sudo -u "${INSTALL_USER}" sed -i "s|^socket_timeout = .*|socket_timeout = 60|" "${cfg}"
  done

  # c7g.2xlarge: 8 vCPU, 16 GB RAM. Crawler is CPU-bound at handshake
  # parsing, so workers scale ~linearly with vCPU count (rule of thumb:
  # ~150 crawl workers per vCPU). Upstream defaults (crawl=700,
  # ping=2000, sampling=100%) still over-subscribe Tor; keep
  # onion_peers_sampling_rate low and ping.workers modest.
  sudo -u "${INSTALL_USER}" sed -i \
    -e "s|^workers = .*|workers = 1200|" \
    -e "s|^onion_peers_sampling_rate = .*|onion_peers_sampling_rate = 25|" \
    -e "s|^snapshot_delay = .*|snapshot_delay = 900|" \
    "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf"
  sudo -u "${INSTALL_USER}" sed -i \
    -e "s|^workers = .*|workers = 600|" \
    "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf"

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
  install -m 0644 "${DASHBOARD_DIR}/deploy/tcpdump-pcap.service" /etc/systemd/system/tcpdump-pcap.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/geoip-update.service" /etc/systemd/system/geoip-update.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/geoip-update.timer" /etc/systemd/system/geoip-update.timer
  install -m 0644 "${DASHBOARD_DIR}/deploy/pcap-cleanup.service" /etc/systemd/system/pcap-cleanup.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/pcap-cleanup.timer" /etc/systemd/system/pcap-cleanup.timer
  install -m 0755 "${DASHBOARD_DIR}/deploy/run-bitnodes.sh" "${CRAWLER_DIR}/run-bitnodes.sh"
  install -m 0755 "${DASHBOARD_DIR}/deploy/run-tcpdump.sh"  "${CRAWLER_DIR}/run-tcpdump.sh"
  chown "${INSTALL_USER}:${INSTALL_USER}" "${CRAWLER_DIR}/run-bitnodes.sh" "${CRAWLER_DIR}/run-tcpdump.sh"

  sudo -u "${INSTALL_USER}" mkdir -p "${CRAWLER_DIR}/data/pcap/f9beb4d9"

  sed -i "s|__USER__|${INSTALL_USER}|g; s|__CRAWLER_DIR__|${CRAWLER_DIR}|g; s|__DASHBOARD_DIR__|${DASHBOARD_DIR}|g; s|__EXPORT_DIR__|${CRAWLER_DIR}/data/export/f9beb4d9|g" \
    /etc/systemd/system/bitnodes.service /etc/systemd/system/alt-bitnodes.service /etc/systemd/system/tcpdump-pcap.service \
    /etc/systemd/system/geoip-update.service /etc/systemd/system/pcap-cleanup.service \
    "${CRAWLER_DIR}/run-tcpdump.sh"

  systemctl daemon-reload
  systemctl enable bitnodes.service tcpdump-pcap.service alt-bitnodes.service
  systemctl enable --now pcap-cleanup.timer
  # Restart so re-runs pick up unit-file changes (enable --now is a no-op on
  # already-running services; we explicitly want them to reload config).
  systemctl restart bitnodes.service tcpdump-pcap.service alt-bitnodes.service

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
  install_apt_packages
  install_pyenv
  setup_crawler
  setup_dashboard
  install_systemd_units
  bootstrap_origin_secret
  configure_nginx
  install_cloudwatch_agent

  log "Done"
  echo
  echo "Verify:"
  echo "  systemctl status bitnodes alt-bitnodes"
  echo "  ssh tunnel: ssh -L 8000:127.0.0.1:8000 <this-host>"
  echo "  open http://localhost:8000"
}

main "$@"
