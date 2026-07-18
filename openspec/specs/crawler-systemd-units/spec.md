# crawler-systemd-units

## Purpose

Defines the systemd contract for the bitnodes crawler stack deployment. After the `remove-rtt-pipeline` change there is no pcap-capture pipeline at all — this capability now exists to make that absence load-bearing: the deployment ships no `tcpdump-pcap.service`/`pcap-cleanup.*`/`run-tcpdump.sh`, and `install.sh` contains no tcpdump or pcap logic.
## Requirements
### Requirement: The deployment ships no pcap-capture component

The deployment SHALL contain no packet-capture pipeline at all: no `tcpdump-pcap.service`, no `run-tcpdump.sh`, no `pcap-cleanup.service`/`pcap-cleanup.timer`. `install.sh` SHALL neither install nor sanitise any tcpdump/pcap unit — there is no such unit to enable, disable, want, or clean up.

#### Scenario: No pcap units in the repository or on the host
- **WHEN** `install.sh` runs on a host
- **THEN** no `tcpdump-pcap.service`, `pcap-cleanup.service`, or `pcap-cleanup.timer` is installed, and `deploy/` contains none of `tcpdump-pcap.service`, `run-tcpdump.sh`, `pcap-cleanup.service`, `pcap-cleanup.timer`

#### Scenario: install.sh has no tcpdump/pcap logic
- **WHEN** `install.sh` is inspected
- **THEN** it SHALL contain no install, placeholder-substitution, `stop`, `disable`, or `pkill` logic referring to tcpdump or pcap

#### Scenario: A host upgraded across this change loses the pcap units
- **WHEN** `install.sh` runs on a host that still had `tcpdump-pcap.service` from a previous deploy
- **THEN** the deploy SHALL leave the host with no pcap-capture units installed (the units are removed, not merely disabled)

### Requirement: Deploys restart the crawler only when it changed

`install.sh` SHALL restart `bitnodes.service` only if the crawler-relevant
state changed during the run — the crawler checkout's git revision, the
generated `*.f9beb4d9.conf` files, the installed `run-bitnodes.sh`, or the
`bitnodes.service` unit — or if the service is not active. The dashboard and
MCP services SHALL still restart on every deploy.

#### Scenario: Dashboard-only deploy leaves the crawler running
- **WHEN** `install.sh` runs and none of the crawler-relevant inputs changed
- **THEN** `bitnodes.service` is not restarted and its open connections
  survive the deploy, while `alt-bitnodes.service` and
  `alt-bitnodes-mcp.service` are restarted

#### Scenario: Crawler change triggers a restart
- **WHEN** `install.sh` runs and the crawler branch, a generated conf, the
  run script, or the unit file changed
- **THEN** `bitnodes.service` is restarted

#### Scenario: Stopped crawler is always started
- **WHEN** `install.sh` runs and `bitnodes.service` is not active
- **THEN** the service is (re)started regardless of the fingerprint

