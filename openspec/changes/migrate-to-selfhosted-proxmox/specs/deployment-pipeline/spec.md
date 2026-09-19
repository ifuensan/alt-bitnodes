# deployment-pipeline

## Purpose

How a commit on `main` becomes the running production system when the
production host is a VM on a home LAN with no public inbound path, and what
the installer must reproduce on a bare host so that a rebuild is a
documented procedure rather than archaeology.

## ADDED Requirements

### Requirement: Deploys reach the host through Cloudflare Access

The GitHub Actions deploy job SHALL connect to the production host over SSH
via `cloudflared access ssh` as `ProxyCommand`, authenticated with a
Cloudflare Access service token held in repository secrets. The host SHALL
expose SSH to the tunnel only (`ssh.hacknodes.xyz`), never on a public
port. The job's semantics — run only after the test job, `deploy-prod`
concurrency without cancellation, skip on docs-only pushes,
`workflow_dispatch` available, smoke-test port 8000 after `install.sh` —
SHALL be unchanged.

#### Scenario: Push to main deploys to the VM
- **WHEN** a non-docs commit lands on `main` and tests pass
- **THEN** the job runs `git reset --hard origin/main` and
  `sudo bash deploy/install.sh` on the VM through the Access tunnel and
  the smoke test returns `200` from `127.0.0.1:8000`

#### Scenario: Revoked service token blocks deploys
- **WHEN** the Access service token is revoked
- **THEN** the deploy job fails at the SSH step and nothing runs on the host

### Requirement: Host behaviour is selected by marker files, not environment

`install.sh` SHALL read every host-specific switch from files under
`/etc/alt-bitnodes/` (`edge`, `crawler-profile`, `parked-units`,
`cloudflared.env`) and SHALL NOT depend on environment variables for them.
An absent switch SHALL mean the behaviour of the host that predates the
switch, so a push during a transition cannot change an existing host.

#### Scenario: Installer completes on a bare host
- **WHEN** `install.sh` runs on a host with no crawler checkout, no
  generated confs and no `bitnodes.service` yet
- **THEN** the pre-run crawler fingerprint is computed from empty input
  and the installer proceeds instead of aborting at the first line of `main`

#### Scenario: Legacy host is unaffected by new switches
- **WHEN** `install.sh` with the new switches runs on a host that has no
  marker files
- **THEN** it renders the same nginx config, the same crawler confs and
  enables the same units as the previous version did

### Requirement: The installer reproduces the data-volume layout

When `/data` is a mountpoint, `install.sh` SHALL create
`/data/{bitnodes-data,bitnodes-log,alt-bitnodes-data,redis,attic}` and bind
mount the first four onto `~/bitnodes/data`, `~/bitnodes/log`,
`~/alt-bitnodes/data` and `/var/lib/redis` via `/etc/fstab`, idempotently,
before any of those directories are populated. When `/data` is not a
mountpoint it SHALL warn and continue.

#### Scenario: Fresh host with a data disk
- **WHEN** `/data` is mounted and `install.sh` runs for the first time
- **THEN** `findmnt ~/bitnodes/data` shows a bind from `/data/bitnodes-data`
  and the first export lands on the data volume

#### Scenario: Re-run adds nothing
- **WHEN** `install.sh` runs again on that host
- **THEN** `/etc/fstab` has exactly one entry per bind and `mount -a`
  reports nothing new

#### Scenario: Dev box without a data disk
- **WHEN** `/data` is not a mountpoint
- **THEN** the installer logs a warning naming the missing layout and
  completes with everything on the root filesystem

### Requirement: Hosts carry no cloud-provider agent unless the edge requires it

The installer SHALL install the CloudWatch agent only while
`edge = cloudfront`; a Cloudflare-edge host SHALL have no AWS component.

#### Scenario: Cloudflare host is provider-free
- **WHEN** `edge` contains `cloudflare` and `install.sh` runs
- **THEN** `dpkg -s amazon-cloudwatch-agent` reports not installed and no
  `/opt/aws` directory is created
