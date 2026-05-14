## ADDED Requirements

### Requirement: pcap capture is never a side effect of the crawler
The crawler service (`bitnodes.service`) SHALL NOT start, want, require, or otherwise pull in the pcap-capture service (`tcpdump-pcap.service`) as a dependency. Starting pcap capture SHALL be an explicit, manual action.

#### Scenario: Crawler restart does not start pcap capture
- **WHEN** `bitnodes.service` is started or restarted (e.g. during a deploy)
- **THEN** `tcpdump-pcap.service` SHALL NOT be activated as a consequence — its `ExecMainStartTimestamp` SHALL NOT coincide with the crawler's

#### Scenario: pcap capture remains manually startable
- **WHEN** an operator runs `systemctl start tcpdump-pcap.service` explicitly
- **THEN** the pcap-capture service SHALL start normally, so it stays available as an opt-in tool

### Requirement: Disabling pcap capture survives deploys
The deployment (`install.sh`) SHALL leave `tcpdump-pcap.service` inert by default after every run — neither enabled for boot nor pulled in by another unit — so that the snapshot-stability decision from the 2026-05-13 postmortem holds across deploys.

#### Scenario: After a deploy, pcap capture is inert
- **WHEN** `install.sh` finishes on a host
- **THEN** `tcpdump-pcap.service` SHALL be neither `active` (unless an operator started it manually) nor reachable as a dependency of `bitnodes.service`

#### Scenario: A stray tcpdump from a prior state is cleaned up
- **WHEN** `install.sh` runs and a `tcpdump` process or `tcpdump-pcap.service` instance is alive from a previous configuration
- **THEN** `install.sh` SHALL stop and kill it as part of its idempotent sanitation, leaving the host in the inert state
