## MODIFIED Requirements

### Requirement: pcap capture is never a side effect of the crawler
The deployment SHALL ship no pcap-capture service at all. `tcpdump-pcap.service`, `run-tcpdump.sh`, and the `pcap-cleanup` units are removed from the repository, and `install.sh` neither installs nor sanitises them. RTT collection no longer involves packet capture (see the `rtt-collection` capability).

#### Scenario: No pcap-capture unit exists
- **WHEN** the crawler stack is deployed
- **THEN** there SHALL be no `tcpdump-pcap.service` unit installed, no `run-tcpdump.sh` on the host, and `install.sh` SHALL contain no tcpdump/pcap install or sanitation logic

#### Scenario: Crawler runs with no sniffer
- **WHEN** `bitnodes.service` is started or restarted
- **THEN** no `tcpdump` process is started as a consequence — there is no pcap-capture unit to pull in, and snapshot stability holds permanently

## REMOVED Requirements

### Requirement: Disabling pcap capture survives deploys
**Reason**: This requirement existed to keep `tcpdump-pcap.service` inert across deploys while it still shipped in the repo (the `fix-tcpdump-revival` era). With `active-ping-rtt` the pcap-capture service is deleted entirely — there is nothing left to keep "inert", so the requirement is obsolete rather than changed.

**Migration**: No action for operators. The pcap units are gone; the host no longer has a `tcpdump-pcap.service` to enable, disable, or sanitise. Any host upgraded across this change will have the units removed by `install.sh` on the next deploy.
