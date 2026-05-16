## MODIFIED Requirements

### Requirement: The deployment ships no pcap-capture component

The deployment SHALL contain no packet-capture pipeline at all: no `tcpdump-pcap.service`, no `run-tcpdump.sh`, no `pcap-cleanup.service`/`pcap-cleanup.timer`. `install.sh` SHALL neither install nor sanitise any tcpdump/pcap unit — there is no such unit to enable, disable, want, or clean up.

This replaces the `fix-tcpdump-revival`-era requirements ("pcap capture is never a side effect of the crawler" and "Disabling pcap capture survives deploys"), which existed to keep a still-shipped `tcpdump-pcap.service` inert. With the pcap subsystem removed entirely, there is nothing left to orchestrate.

#### Scenario: No pcap units in the repository or on the host
- **WHEN** `install.sh` runs on a host
- **THEN** no `tcpdump-pcap.service`, `pcap-cleanup.service`, or `pcap-cleanup.timer` is installed, and `deploy/` contains none of `tcpdump-pcap.service`, `run-tcpdump.sh`, `pcap-cleanup.service`, `pcap-cleanup.timer`

#### Scenario: install.sh has no tcpdump/pcap logic
- **WHEN** `install.sh` is inspected
- **THEN** it SHALL contain no install, placeholder-substitution, `stop`, `disable`, or `pkill` logic referring to tcpdump or pcap

#### Scenario: A host upgraded across this change loses the pcap units
- **WHEN** `install.sh` runs on a host that still had `tcpdump-pcap.service` from a previous deploy
- **THEN** the deploy SHALL leave the host with no pcap-capture units installed (the units are removed, not merely disabled)

## REMOVED Requirements

### Requirement: pcap capture is never a side effect of the crawler
**Reason**: Introduced by `fix-tcpdump-revival` to keep a still-shipped `tcpdump-pcap.service` from being pulled in by `bitnodes.service`. The pcap subsystem is now deleted entirely — there is no capture service to be a side effect of anything.

**Migration**: No operator action. The pcap units are removed by `install.sh` on the next deploy.

### Requirement: Disabling pcap capture survives deploys
**Reason**: Introduced by `fix-tcpdump-revival` to keep `tcpdump-pcap.service` inert across deploys while it still shipped. With the units deleted, there is nothing to keep inert.

**Migration**: No operator action. The host no longer has a `tcpdump-pcap.service` to enable, disable, or sanitise.
