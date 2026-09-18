#!/usr/bin/env bash
# Idempotent installer for Ubuntu 24.04 LTS. Host-agnostic: it ran on an
# AWS EC2 (ARM64 / Graviton) and now targets a VM on the home Proxmox host
# (x86-64); everything host-specific is selected by marker files under
# /etc/alt-bitnodes (see EDGE_MODE / CRAWLER_PROFILE / PARKED_UNITS_FILE).
# Sets up: pyenv + Python 3.12.4, redis-server, ifuensan/bitnodes (crawler),
# ifuensan/alt-bitnodes (dashboard), Tor pool, i2pd, nginx, the public edge
# (Cloudflare Tunnel or, legacy, CloudFront origin), systemd units.
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
# dials across every proxy listed in tor_proxies, one fixed instance per
# onion address (see tor_proxy_affinity below).
TOR_POOL_SIZE=8

# A/B arm for the MaxCircuitDirtiness experiment: space-separated pool
# instance numbers that get TOR_DIRTINESS_VALUE instead of Tor's 600s
# default. Empty means no experiment — every instance keeps the default.
# Both arms must be in place BEFORE the pool starts, or the treated half
# re-ramps while the control half is already warm and the run is worthless.
#
# Set here rather than passed in: the deploy runs `sudo bash install.sh` over
# SSH with no environment, so an env-only knob would silently deploy an empty
# arm and produce a run with nothing to compare. Empty this when the
# experiment ends — it is a temporary state of the deployment, in git so it
# is visible.
#
# 1-4 treated, 5-8 control. tor@default (9050) is neither: its torrc is
# managed separately and the sampler does not read it, so it stays out of
# the comparison entirely.
TOR_DIRTINESS_ARM="${TOR_DIRTINESS_ARM:-1 2 3 4}"
TOR_DIRTINESS_VALUE="${TOR_DIRTINESS_VALUE:-3600}"

# Pin each .onion to one Tor instance so revisits reuse the descriptor and
# rendezvous circuit that instance already holds. Without this,
# MaxCircuitDirtiness is nearly inert: a revisit meets the warm circuit only
# 1/N of the time.
TOR_PROXY_AFFINITY="${TOR_PROXY_AFFINITY:-True}"

log() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }

require_root() { [[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }; }

# Units the operator has deliberately parked, one name per line. A deploy
# must never undo that decision: stopping the crawler stack is how running
# costs are cut (the egress bill is ~99% Tor/I2P overlay traffic), and an
# installer that silently restarts it turns a docs push into a bill.
#
#   Park:   echo bitnodes.service | sudo tee -a /etc/alt-bitnodes/parked-units
#           sudo systemctl disable --now bitnodes.service
#   Unpark: sudo sed -i '/^bitnodes\.service$/d' /etc/alt-bitnodes/parked-units
#           sudo bash deploy/install.sh
#
# `systemctl is-enabled` cannot be used for this: a freshly installed unit
# that was never enabled also reports "disabled", so it would break first
# installs. An explicit file states intent unambiguously.
PARKED_UNITS_FILE=/etc/alt-bitnodes/parked-units

is_parked() {
  [[ -f "${PARKED_UNITS_FILE}" ]] || return 1
  grep -qxF "$1" "${PARKED_UNITS_FILE}"
}

# Host-specific switches live in files, for the same reason parked-units
# does: the deploy runs this script over SSH with no environment, so an
# env-only knob silently takes its default on every deploy. An ABSENT file
# means "the behaviour of the host that predates the switch", so a push
# during a transition cannot change an existing host.
#
#   /etc/alt-bitnodes/edge             cloudfront (legacy EC2) | cloudflare
#   /etc/alt-bitnodes/crawler-profile  full | clearnet
#
# Provisioning a new host writes both before the first run:
#   echo cloudflare | sudo tee /etc/alt-bitnodes/edge
#   echo clearnet   | sudo tee /etc/alt-bitnodes/crawler-profile
read_marker() {
  local file="/etc/alt-bitnodes/$1" default="$2" value
  if [[ -s "${file}" ]]; then
    value="$(tr -d '[:space:]' < "${file}")"
    printf '%s' "${value:-${default}}"
  else
    printf '%s' "${default}"
  fi
}
EDGE_MODE="$(read_marker edge cloudfront)"
CRAWLER_PROFILE="$(read_marker crawler-profile full)"
case "${EDGE_MODE}" in cloudfront|cloudflare) ;; *) echo "bad /etc/alt-bitnodes/edge: ${EDGE_MODE}"; exit 1 ;; esac
case "${CRAWLER_PROFILE}" in full|clearnet) ;; *) echo "bad /etc/alt-bitnodes/crawler-profile: ${CRAWLER_PROFILE}"; exit 1 ;; esac

# Overlay daemons (Tor pool, tor@default, i2pd) run only under the `full`
# profile. Under `clearnet` they are provisioned but kept disabled and
# stopped, so switching profiles is a marker edit plus a re-run. Parking
# still wins under `full`.
enable_overlay_unit() {
  local unit="$1"; shift
  if [[ "${CRAWLER_PROFILE}" == "clearnet" ]]; then
    if systemctl is-enabled --quiet "${unit}" 2>/dev/null || systemctl is-active --quiet "${unit}" 2>/dev/null; then
      log "${unit}: crawler profile is clearnet; disabling and stopping"
      systemctl disable --now "${unit}" 2>/dev/null || true
    fi
    return 0
  fi
  enable_unit "${unit}" "$@"
}

# systemctl enable [--now] that respects parked units.
enable_unit() {
  local unit="$1"; shift
  if is_parked "${unit}"; then
    log "${unit} is parked; leaving it stopped"
    return 0
  fi
  systemctl enable "$@" "${unit}"
}

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
  enable_overlay_unit tor.service --now
}

# Collected data lives on its own volume when the host has one (the
# 2026-08-13 layout, see docs/follow-ups.md). Bind mounts, not symlinks:
# the units run ProtectHome=read-only with ReadWritePaths under /home and
# the crawler confs use relative paths, so every path must stay identical.
# The point is failure isolation -- a full data disk stops collection, not
# the OS. Without a /data mountpoint (a dev box) this warns and continues.
setup_data_volume() {
  if ! mountpoint -q /data; then
    echo "WARNING: /data is not a mountpoint; collected data will live on the root filesystem" >&2
    return 0
  fi
  log "Provisioning /data layout"
  local d
  for d in bitnodes-data bitnodes-log alt-bitnodes-data attic; do
    install -d -o "${INSTALL_USER}" -g "${INSTALL_USER}" "/data/${d}"
  done
  install -d -o redis -g redis -m 0750 /data/redis

  sudo -u "${INSTALL_USER}" mkdir -p "${CRAWLER_DIR}/data" "${CRAWLER_DIR}/log" "${DASHBOARD_DIR}/data"

  # One fstab line per bind, added only if no line already maps src -> dst
  # (whatever its options), and a mount only if dst is not a mountpoint yet,
  # so a hand-built layout (the EC2) is neither duplicated nor stacked.
  # Redis is already running from install_apt_packages: its first bind must
  # move the live RDB, not hide it under the mount.
  local src dst
  while read -r src dst; do
    if ! grep -qE "^${src}[[:space:]]+${dst}[[:space:]]" /etc/fstab; then
      printf '%s %s none bind,nofail 0 0\n' "${src}" "${dst}" >> /etc/fstab
    fi
    if ! mountpoint -q "${dst}"; then
      if [[ "${dst}" == /var/lib/redis ]]; then
        log "Moving Redis data to /data/redis"
        systemctl stop redis-server
        if [[ -f /var/lib/redis/dump.rdb && ! -f /data/redis/dump.rdb ]]; then
          cp -a /var/lib/redis/. /data/redis/
        fi
        mount "${dst}"
        systemctl start redis-server
      else
        mount "${dst}"
      fi
    fi
  done <<EOF_BINDS
/data/redis /var/lib/redis
/data/bitnodes-data ${CRAWLER_DIR}/data
/data/bitnodes-log ${CRAWLER_DIR}/log
/data/alt-bitnodes-data ${DASHBOARD_DIR}/data
EOF_BINDS
  systemctl daemon-reload
}

setup_i2pd() {
  log "Installing i2pd (I2P router with SAM bridge)"
  if ! command -v i2pd >/dev/null; then
    add-apt-repository -y ppa:purplei2p/i2pd >/dev/null
    apt-get update -qq
    apt-get install -y -qq i2pd
  fi
  enable_overlay_unit i2pd.service --now
  [[ "${CRAWLER_PROFILE}" == "clearnet" ]] && return
  is_parked i2pd.service && return
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
  #
  # UseEntryGuards 0 (2026-07-22): a crawler funnels all circuit creation
  # through 1-2 entry guards per daemon and their per-IP anti-DoS throttles
  # exactly that (247k circuit timeouts vs 212 completed on one guard;
  # onion pinned at ~0 under load while the daemons sat idle). Random entry
  # per circuit spreads creation across the relay set: onion 3 -> ~10.8k
  # open connections in 13h. No anonymity requirement here, so the guard
  # trade-off does not apply. NumEntryGuards is inert with it but kept so
  # the desired torrc byte-matches the live files (a mismatch would rewrite
  # and restart every daemon, collapsing the ramp).
  #
  # HeartbeatPeriod 900 (2026-08-12): each daemon logs its own circuit
  # handshake and connection counters every 15 min. That journal line is the
  # per-instance measurement of handshake churn, which is what the
  # MaxCircuitDirtiness A/B needs and what no external tool can attribute.
  local tor_opts="MaxClientCircuitsPending 512
NumEntryGuards 8
UseEntryGuards 0
HeartbeatPeriod 900"

  # Per-unit egress accounting for the same experiment. systemd counts bytes
  # in the unit's cgroup, so it attributes exactly, where paired `ss` deltas
  # miss every connection that begins and ends between two samples -- most of
  # them at ~1k new TLS connections/min. Written inline rather than copied
  # from the repo: this function runs before setup_dashboard clones it.
  # IPAccounting takes effect when a unit starts, which the torrc rewrite
  # below already forces for any instance whose configuration changed.
  local accounting_dir=/etc/systemd/system/tor@.service.d
  local accounting_file="${accounting_dir}/ip-accounting.conf"
  local accounting_desired="# Managed by alt-bitnodes install.sh
# Per-instance byte counters: systemctl show tor@bitnodes1 -p IPEgressBytes
# Counters reset with the unit, so any interval spanning a restart is void.
[Service]
IPAccounting=yes"
  mkdir -p "${accounting_dir}"
  if [[ ! -f "${accounting_file}" ]] || [[ "$(cat "${accounting_file}")" != "${accounting_desired}" ]]; then
    printf '%s\n' "${accounting_desired}" > "${accounting_file}"
    systemctl daemon-reload
  fi

  local i name port torrc desired
  for i in $(seq 1 "${TOR_POOL_SIZE}"); do
    name="bitnodes${i}"
    port=$((9050 + i))
    torrc="/etc/tor/instances/${name}/torrc"
    [[ -d "/etc/tor/instances/${name}" ]] || tor-instance-create "${name}"
    desired="SocksPort 127.0.0.1:${port}
${tor_opts}"
    # A/B arm: only the instances named in TOR_DIRTINESS_ARM get a
    # non-default circuit lifetime, so both lifetimes run side by side in one
    # pool under identical network conditions. Written into `desired` so the
    # byte-comparison below still decides restarts per instance.
    if [[ " ${TOR_DIRTINESS_ARM} " == *" ${i} "* ]]; then
      desired="${desired}
MaxCircuitDirtiness ${TOR_DIRTINESS_VALUE}"
    fi
    if [[ ! -f "${torrc}" ]] || [[ "$(cat "${torrc}")" != "${desired}" ]]; then
      printf '%s\n' "${desired}" > "${torrc}"
      # Full restart, not reload: also clears degraded guard/circuit state.
      systemctl try-restart "tor@${name}" 2>/dev/null || true
    fi
    enable_overlay_unit "tor@${name}.service" --now
  done

  # Same treatment for the default instance (SocksPort 9050): it shares the
  # crawler workload via tor_proxies.
  if ! grep -q "^# alt-bitnodes crawler tuning" /etc/tor/torrc; then
    printf '\n# alt-bitnodes crawler tuning\n%s\n' "${tor_opts}" >> /etc/tor/torrc
    systemctl try-restart tor@default 2>/dev/null || true
  fi
  # Under `full` tor.service owns tor@default, exactly as before this knob
  # existed; only `clearnet` has to act on it explicitly.
  if [[ "${CRAWLER_PROFILE}" == "clearnet" ]]; then
    enable_overlay_unit tor@default.service
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

  # Network profile. `onion` and `i2p` are boolean gates in crawl.py and
  # ping.py; under `clearnet` the crawler dials IPv4/IPv6 only and the
  # overlay daemons stay down (enable_overlay_unit). Everything else --
  # tor_proxies, sampling rates, the I2P seed file -- is rendered under both
  # profiles so the switch is a marker edit plus a re-run. The conf change
  # moves crawler_fingerprint, so the crawler restarts when the profile does.
  local overlays=True
  [[ "${CRAWLER_PROFILE}" == "clearnet" ]] && overlays=False
  log "Crawler profile: ${CRAWLER_PROFILE} (onion/i2p = ${overlays})"
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" onion "${overlays}"
  ensure_conf_key "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf" onion "${overlays}"

  # I2P ring: dial .b32.i2p peers through the local i2pd SAM bridge.
  # ensure_conf_key because live conf files may predate these keys.
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p "${overlays}"
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p_proxies 127.0.0.1:7656
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p_peers_sampling_rate 100
  # Seed the I2P ring: clearnet peers rarely gossip .b32.i2p, so without
  # seeds it never bootstraps. The list ships with the crawler fork.
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" i2p_nodes_file conf/i2p_seeds.txt
  ensure_conf_key "${CRAWLER_DIR}/conf/crawl.f9beb4d9.conf" tor_proxy_affinity "${TOR_PROXY_AFFINITY}"
  ensure_conf_key "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf" tor_proxy_affinity "${TOR_PROXY_AFFINITY}"

  ensure_conf_key "${CRAWLER_DIR}/conf/ping.f9beb4d9.conf" i2p "${overlays}"
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

  # Cache-bust static assets by stamping the deployed commit into their
  # URLs (?v=<sha>). A content change ships a new URL, so no browser or
  # CloudFront edge can ever serve a stale app.js/app.css against fresh
  # HTML — the recurring "forgot to invalidate CloudFront" breakage.
  # Idempotent: replaces whatever ?v= value is present, so re-runs are safe
  # and `git reset --hard` (which restores the ?v=dev placeholder) re-stamps.
  local sha
  sha="$(git -C "${DASHBOARD_DIR}" rev-parse --short HEAD)"
  sudo -u "${INSTALL_USER}" sed -i -E \
    "s#(/static/[a-zA-Z0-9._-]+\?v=)[^\"']*#\1${sha}#g" \
    "${DASHBOARD_DIR}"/templates/*.html
  log "Stamped static asset version: ${sha}"
}

install_systemd_units() {
  log "Installing logrotate for crawler logs"
  sed "s|__CRAWLER_DIR__|${CRAWLER_DIR}|g" \
    "${DASHBOARD_DIR}/deploy/logrotate-bitnodes" > /etc/logrotate.d/bitnodes
  chmod 0644 /etc/logrotate.d/bitnodes

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
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-window-stats.service" /etc/systemd/system/alt-bitnodes-window-stats.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-window-stats.timer" /etc/systemd/system/alt-bitnodes-window-stats.timer
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-collector.service" /etc/systemd/system/alt-bitnodes-collector.service
  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-collector.timer" /etc/systemd/system/alt-bitnodes-collector.timer
  install -m 0755 "${DASHBOARD_DIR}/deploy/run-bitnodes.sh" "${CRAWLER_DIR}/run-bitnodes.sh"
  chown "${INSTALL_USER}:${INSTALL_USER}" "${CRAWLER_DIR}/run-bitnodes.sh"

  install -m 0644 "${DASHBOARD_DIR}/deploy/alt-bitnodes-tor-experiment.service" /etc/systemd/system/alt-bitnodes-tor-experiment.service
  install -d -m 0755 /var/log/alt-bitnodes

  sed -i "s|__USER__|${INSTALL_USER}|g; s|__CRAWLER_DIR__|${CRAWLER_DIR}|g; s|__DASHBOARD_DIR__|${DASHBOARD_DIR}|g; s|__EXPORT_DIR__|${CRAWLER_DIR}/data/export/f9beb4d9|g" \
    /etc/systemd/system/bitnodes.service /etc/systemd/system/alt-bitnodes.service \
    /etc/systemd/system/alt-bitnodes-mcp.service /etc/systemd/system/geoip-update.service \
    /etc/systemd/system/export-prune.service /etc/systemd/system/alt-bitnodes-archive.service \
    /etc/systemd/system/alt-bitnodes-window-stats.service \
    /etc/systemd/system/alt-bitnodes-collector.service \
    /etc/systemd/system/alt-bitnodes-tor-experiment.service

  sed -i "s|__TOR_POOL_SIZE__|${TOR_POOL_SIZE}|g; s|__TOR_DIRTINESS_ARM__|${TOR_DIRTINESS_ARM}|g; s|__TOR_DIRTINESS_VALUE__|${TOR_DIRTINESS_VALUE}|g" \
    /etc/systemd/system/alt-bitnodes-tor-experiment.service

  systemctl daemon-reload
  systemctl enable alt-bitnodes.service alt-bitnodes-mcp.service
  enable_unit bitnodes.service
  enable_unit export-prune.timer --now
  enable_unit alt-bitnodes-archive.timer --now
  enable_unit alt-bitnodes-window-stats.timer --now
  enable_unit alt-bitnodes-collector.timer --now
  # The sampler only exists while an A/B is configured; with no arm there is
  # nothing to compare and no reason to keep a process writing CSV forever.
  if [[ -n "${TOR_DIRTINESS_ARM}" ]]; then
    enable_unit alt-bitnodes-tor-experiment.service --now
  else
    systemctl disable --now alt-bitnodes-tor-experiment.service 2>/dev/null || true
  fi
  # Dashboard + MCP are stateless: restart on every deploy so re-runs pick up
  # unit-file changes. The crawler is stateful (open sockets, onion circuits):
  # restart only if its inputs changed or it isn't running.
  systemctl restart alt-bitnodes.service alt-bitnodes-mcp.service
  if is_parked bitnodes.service; then
    # "not running" is the parked state, not a fault to repair.
    log "bitnodes.service is parked; not restarting it"
  elif [[ "$(crawler_fingerprint)" != "${CRAWLER_STATE_BEFORE}" ]] \
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
  # Group stays INSTALL_USER: the token files in this directory are read by
  # the service user, and this now runs after generate_token_file.
  install -d -m 0750 -o root -g "${INSTALL_USER}" "${dir}"
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

generate_token_file() {
  # Write a random token to $1 if absent. Owned by the service user so systemd
  # can read it without giving the file world access. Rotation: delete the file
  # and re-run install.sh; the service picks it up on its next restart.
  local file="$1" label="$2"
  install -d -m 0750 -o root -g "${INSTALL_USER}" /etc/alt-bitnodes
  if [[ ! -f "${file}" ]]; then
    log "Generating ${file}"
    umask 077
    # 32 random bytes, base64url-encoded, no newline.
    openssl rand -base64 32 | tr -d '\n=' | tr '/+' '_-' > "${file}"
    chmod 0640 "${file}"
    chown root:"${INSTALL_USER}" "${file}"
    echo "    ${label} written (chmod 0640 root:${INSTALL_USER})"
  else
    log "${file} already present; leaving as-is"
  fi
}

bootstrap_mcp_token() {
  # Bearer token required by the MCP HTTP transport (alt-bitnodes-mcp.service
  # validates Authorization: Bearer <this>).
  generate_token_file /etc/alt-bitnodes/mcp-token "MCP bearer token"
}

bootstrap_research_token() {
  # Gate token for /research. The page holds exploratory charts that are not
  # maintained to the standard of the public dashboard, so it is served only
  # to a caller presenting ?token=<this>. Without this file the page stays
  # closed (the gate fails closed by design).
  generate_token_file /etc/alt-bitnodes/research-token "Research gate token"
}

configure_nginx() {
  log "Configuring nginx"
  install -m 0644 "${DASHBOARD_DIR}/deploy/nginx/alt-bitnodes-limits.conf" \
    /etc/nginx/conf.d/alt-bitnodes-limits.conf

  local site=/etc/nginx/sites-available/alt-bitnodes
  if [[ "${EDGE_MODE}" == "cloudflare" ]]; then
    # Tunnel edge: loopback only, no shared secret, real IP from cloudflared.
    sed \
      -e "s|__SERVER_NAME__|${PUBLIC_HOST} _|g" \
      "${DASHBOARD_DIR}/deploy/nginx/alt-bitnodes-tunnel.conf.template" > "${site}"
  else
    # Legacy CloudFront origin. Use a delimiter that won't appear in the
    # secret (hex only) or hostnames.
    sed \
      -e "s|__SERVER_NAME__|origin.hacknodes.xyz pesquisa.hacknodes.xyz _|g" \
      -e "s|__SECRET__|${ORIGIN_AUTH_SECRET}|g" \
      "${DASHBOARD_DIR}/deploy/nginx/alt-bitnodes.conf.template" > "${site}"
  fi
  chmod 0644 "${site}"

  ln -sf "${site}" /etc/nginx/sites-enabled/alt-bitnodes
  rm -f /etc/nginx/sites-enabled/default

  nginx -t
  systemctl enable nginx
  systemctl reload nginx
}

# Cloudflare Tunnel: cloudflared keeps outbound connections to Cloudflare's
# edge and routes the public hostnames into nginx on loopback, so the host
# opens no inbound port. Locally-managed tunnel: the ingress rules are
# rendered from the repo template; the tunnel id and hostnames come from
# /etc/alt-bitnodes/cloudflared.env (written at provisioning, see
# deploy/README.md); the credentials JSON is created once by
# `cloudflared tunnel create` and never touched here.
CLOUDFLARED_ENV=/etc/alt-bitnodes/cloudflared.env

load_cloudflared_env() {
  [[ -f "${CLOUDFLARED_ENV}" ]] || { echo "missing ${CLOUDFLARED_ENV} (TUNNEL_ID, PUBLIC_HOST, SSH_HOST)"; exit 1; }
  # shellcheck disable=SC1090
  source "${CLOUDFLARED_ENV}"
  : "${TUNNEL_ID:?TUNNEL_ID unset in ${CLOUDFLARED_ENV}}"
  : "${PUBLIC_HOST:?PUBLIC_HOST unset in ${CLOUDFLARED_ENV}}"
  : "${SSH_HOST:?SSH_HOST unset in ${CLOUDFLARED_ENV}}"
}

setup_cloudflared() {
  log "Configuring Cloudflare Tunnel (${TUNNEL_ID}) for ${PUBLIC_HOST}"
  if ! command -v cloudflared >/dev/null; then
    install -d -m 0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
      -o /usr/share/keyrings/cloudflare-main.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
      > /etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq
    apt-get install -y -qq cloudflared
  fi
  local creds="/etc/cloudflared/${TUNNEL_ID}.json"
  [[ -f "${creds}" ]] || { echo "missing tunnel credentials ${creds}; run 'cloudflared tunnel create' first"; exit 1; }

  local cfg=/etc/cloudflared/config.yml desired
  desired="$(sed \
    -e "s|__TUNNEL_ID__|${TUNNEL_ID}|g" \
    -e "s|__PUBLIC_HOST__|${PUBLIC_HOST}|g" \
    -e "s|__SSH_HOST__|${SSH_HOST}|g" \
    "${DASHBOARD_DIR}/deploy/cloudflared/config.yml.template")"
  if [[ ! -f "${cfg}" ]] || [[ "$(cat "${cfg}")" != "${desired}" ]]; then
    printf '%s\n' "${desired}" > "${cfg}"
    chmod 0644 "${cfg}"
    systemctl try-restart cloudflared.service 2>/dev/null || true
  fi
  # `service install` writes the unit once; re-running it fails on an
  # existing unit, so gate on the unit file.
  if [[ ! -f /etc/systemd/system/cloudflared.service ]]; then
    cloudflared --config "${cfg}" service install
  fi
  systemctl enable --now cloudflared.service
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
  setup_data_volume
  bootstrap_mcp_token
  bootstrap_research_token
  install_systemd_units
  case "${EDGE_MODE}" in
    cloudflare)
      load_cloudflared_env
      configure_nginx
      setup_cloudflared
      ;;
    cloudfront)
      bootstrap_origin_secret
      configure_nginx
      install_cloudwatch_agent
      ;;
  esac

  log "Done (edge=${EDGE_MODE}, crawler-profile=${CRAWLER_PROFILE})"
  echo
  echo "Verify:"
  echo "  systemctl status bitnodes alt-bitnodes alt-bitnodes-mcp"
  echo "  ssh tunnel: ssh -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 <this-host>"
  echo "  open http://localhost:8000   # dashboard"
  echo "  curl -H \"Authorization: Bearer \$(sudo cat /etc/alt-bitnodes/mcp-token)\" http://localhost:8001/mcp/"
}

main "$@"
