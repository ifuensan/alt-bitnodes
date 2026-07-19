# i2p-crawling

## ADDED Requirements

### Requirement: The installer provisions an I2P router with SAM

`install.sh` SHALL install `i2pd` (PurpleI2P PPA) and enable its service.
The SAM bridge SHALL be reachable on `127.0.0.1:7656`. If the bridge is not
listening after a bounded wait, the installer SHALL warn but NOT fail the
deploy — I2P is a best-effort ring.

#### Scenario: Fresh install brings up SAM
- **WHEN** `install.sh` runs on a host without i2pd
- **THEN** the `i2pd` service is enabled and running and port 7656 is
  listening on localhost within the wait window

#### Scenario: SAM down does not break the deploy
- **WHEN** i2pd fails to expose SAM within the wait window
- **THEN** the installer logs a warning and completes; crawler I2P dials
  fail as ordinary connection errors without affecting other rings

### Requirement: The crawler is configured to crawl I2P at full sampling

The generated crawl conf SHALL contain `i2p = True`,
`i2p_proxies = 127.0.0.1:7656` and `i2p_peers_sampling_rate = 100`; the ping
conf SHALL contain `i2p = True` and the same proxy. Because conf files on an
upgraded host predate these keys, the installer SHALL set-or-append them
idempotently (re-runs converge, no duplicate keys).

#### Scenario: Upgraded host gains the keys
- **WHEN** `install.sh` runs on a host whose `.f9beb4d9.conf` files lack any
  `i2p` keys
- **THEN** after the run both confs contain the keys with the values above,
  and a second run leaves the files unchanged

### Requirement: The deployed crawler branch carries the SAM dial path

`install.sh` SHALL deploy `ifuensan/bitnodes` branch `feat/i2p-sam-crawl`
(which supersedes `fix/empty-include-asns`).

#### Scenario: Branch switch on an existing checkout
- **WHEN** `install.sh` runs on a host whose crawler checkout is on the old
  branch
- **THEN** the checkout ends up on `feat/i2p-sam-crawl` at origin's tip
