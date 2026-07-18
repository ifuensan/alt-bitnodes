# crawler-systemd-units

## ADDED Requirements

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
