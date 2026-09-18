# crawler-systemd-units

## ADDED Requirements

### Requirement: The installer applies a crawler network profile

`install.sh` SHALL read `/etc/alt-bitnodes/crawler-profile` (`full` or
`clearnet`; absent means `full`) and SHALL render it into the generated
crawler configuration and the overlay daemons' unit state. Under `clearnet`
both `crawl.f9beb4d9.conf` and `ping.f9beb4d9.conf` SHALL carry
`onion = False` and `i2p = False`, and `tor@default`, every `tor@bitnodesN`
and `i2pd` SHALL be disabled and stopped. Under `full` the confs SHALL carry
`onion = True` and `i2p = True` and the daemons SHALL be enabled and started
unless parked. Provisioning of the Tor pool, its torrc files, `tor_proxies`
and the I2P seed file SHALL happen under both profiles so that switching is
a marker edit plus a re-run.

#### Scenario: Clearnet profile keeps overlays off
- **WHEN** `crawler-profile` contains `clearnet` and `install.sh` runs
- **THEN** the generated confs have `onion = False` and `i2p = False`,
  `tor@*` and `i2pd` are inactive and disabled, and `bitnodes.service`
  runs dialing IPv4/IPv6 only

#### Scenario: Switching to full restarts the crawler once
- **WHEN** the marker changes from `clearnet` to `full` and `install.sh` runs
- **THEN** the confs change, the Tor pool and `i2pd` start, and
  `bitnodes.service` is restarted exactly once because its fingerprint moved

#### Scenario: Absent marker preserves legacy behaviour
- **WHEN** the marker file does not exist and `install.sh` runs on a host
  whose confs already say `onion = True` / `i2p = True`
- **THEN** the rendered confs are byte-identical to before and the crawler
  is not restarted

#### Scenario: Parking still wins
- **WHEN** the profile is `full` but `i2pd.service` is listed in
  `parked-units`
- **THEN** `i2pd` stays stopped
