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

#### Scenario: Stopped crawler is started unless parked
- **WHEN** `install.sh` runs and `bitnodes.service` is not active and not parked
- **THEN** the service is (re)started regardless of the fingerprint

### Requirement: Deploys respect deliberately parked units

`install.sh` SHALL read `/etc/alt-bitnodes/parked-units` (one unit name per
line, exact match) and SHALL NOT enable, start or restart any unit listed
there. This covers the crawler, the Tor pool, i2pd and the timers. Parking
is how running costs are cut — the crawler's egress is ~99% Tor/I2P overlay
traffic — so a deploy that silently restarts a parked unit turns an
unrelated push into a bill. An absent file parks nothing, so first installs
are unaffected. Unit enablement state SHALL NOT be used to infer intent: a
freshly installed unit also reports `disabled`.

#### Scenario: Deploy leaves a parked crawler stopped
- **WHEN** `bitnodes.service` is listed in `/etc/alt-bitnodes/parked-units`
  and `install.sh` runs
- **THEN** the service is neither enabled nor restarted, and the run logs
  that it is parked

#### Scenario: Parked overlays stay down
- **WHEN** `i2pd.service` or a `tor@*.service` instance is parked
- **THEN** `install.sh` does not enable or start it, and does not wait on
  the i2pd SAM bridge

#### Scenario: First install with no parked file
- **WHEN** `/etc/alt-bitnodes/parked-units` does not exist
- **THEN** every unit is enabled as usual

