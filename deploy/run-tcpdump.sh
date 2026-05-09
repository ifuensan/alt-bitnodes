#!/usr/bin/env bash
# Foreground tcpdump producer for cache_inv. Captures TCP frames whose payload
# starts with the Bitcoin mainnet magic (0xf9beb4d9), drops privileges to the
# bitnodes user, and rotates dumps into the crawler's pcap dir.
#
# Run by tcpdump-pcap.service (User=root, ExecStart=this script).
set -euo pipefail

DROP_USER="${DROP_USER:-__USER__}"
PCAP_DIR="${PCAP_DIR:-__CRAWLER_DIR__/data/pcap/f9beb4d9}"
ROTATE_SECONDS="${ROTATE_SECONDS:-30}"
KEEP_FILES="${KEEP_FILES:-8}"
IFACE="${TCPDUMP_IFACE:-}"

mkdir -p "${PCAP_DIR}"
chown "${DROP_USER}:${DROP_USER}" "${PCAP_DIR}"

# tcpdump on -i any uses LINUX_SLL2 link-layer, which dpkt.ethernet cannot
# parse → cache_inv extracts 0 packets. Auto-pick the interface used for the
# default route, which records as Ethernet.
if [[ -z "${IFACE}" ]]; then
  IFACE="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{ for (i=1;i<=NF;i++) if ($i=="dev") { print $(i+1); exit } }')"
fi
if [[ -z "${IFACE}" ]]; then
  echo "could not detect default-route interface; set TCPDUMP_IFACE" >&2
  exit 1
fi

echo "tcpdump producer starting: iface=${IFACE} dir=${PCAP_DIR} rotate=${ROTATE_SECONDS}s keep=${KEEP_FILES}"

exec tcpdump \
  -i "${IFACE}" \
  -nn -s 0 \
  -G "${ROTATE_SECONDS}" \
  -W "${KEEP_FILES}" \
  -Z "${DROP_USER}" \
  -w "${PCAP_DIR}/%s.pcap" \
  'tcp and tcp[((tcp[12]&0xf0)>>2):4] = 0xf9beb4d9'
