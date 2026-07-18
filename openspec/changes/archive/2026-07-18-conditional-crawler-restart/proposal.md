# Conditional crawler restart on deploy

## Why

Every deploy restarts `bitnodes.service`, killing ~12k live TCP connections
(and their onion rendezvous circuits) even when the change was
dashboard-only. Each restart costs hours of snapshot ramp-up and pollutes the
historical series with dips. The original bitnodes.io avoided this by never
touching the crawler daemons on web deploys — same separation, applied to our
single-installer flow.

## What Changes

- `install.sh` fingerprints the crawler-relevant state (fork git rev,
  generated `*.f9beb4d9.conf` files, `run-bitnodes.sh`, `bitnodes.service`
  unit) before making changes, and restarts `bitnodes.service` only when the
  fingerprint changed or the service isn't running.
- `alt-bitnodes.service` and `alt-bitnodes-mcp.service` keep restarting on
  every deploy (stateless, instant).

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities
- `crawler-systemd-units`: new requirement — deploys leave a running,
  unchanged crawler untouched.

## Impact

- `deploy/install.sh` only. Doc-only pushes already skip deploys entirely;
  this extends the protection to dashboard/nginx/edge-only changes.
- Risk: fingerprint misses some crawler-relevant input → stale crawler after
  a deploy that should have restarted it. Mitigated by fingerprinting every
  input the installer itself writes; manual `systemctl restart bitnodes`
  remains the escape hatch.
