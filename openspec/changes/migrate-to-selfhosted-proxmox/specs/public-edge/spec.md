# public-edge

## ADDED Requirements

### Requirement: Public TLS via Cloudflare Tunnel

The system SHALL serve the dashboard, the API and the MCP endpoint at
`https://pesquisa.hacknodes.xyz` through a Cloudflare Tunnel terminated by a
`cloudflared` systemd unit on the production host. TLS SHALL be terminated
by Cloudflare with a certificate valid for the hostname; the host SHALL
expose no inbound listener to the Internet for this purpose.

#### Scenario: Client fetches the dashboard over HTTPS
- **WHEN** a client requests `GET https://pesquisa.hacknodes.xyz/`
- **THEN** the response is `200 OK` with the dashboard HTML over a
  certificate whose SAN includes `pesquisa.hacknodes.xyz`

#### Scenario: Plain HTTP is upgraded
- **WHEN** a client requests `GET http://pesquisa.hacknodes.xyz/`
- **THEN** Cloudflare answers with a `301` to the HTTPS equivalent

#### Scenario: Tunnel down means unavailable, not exposed
- **WHEN** `cloudflared.service` is stopped on the host
- **THEN** the public hostname returns a Cloudflare 5xx and no port on the
  host's LAN address answers HTTP

### Requirement: Origin isolation by construction

nginx on the host SHALL listen only on `127.0.0.1:80`. There SHALL be no
shared-secret header, no IP allow-list and no inbound firewall rule for the
web path: the tunnel process is the only route to the origin.

#### Scenario: LAN access to the origin is refused
- **WHEN** a host on the same LAN connects to `<vm-ip>:80` or `<vm-ip>:8000`
- **THEN** the connection is refused (nothing listens on the LAN address)

#### Scenario: Request through the tunnel is served
- **WHEN** `cloudflared` forwards a request to `http://127.0.0.1:80`
- **THEN** nginx proxies it to `127.0.0.1:8000` (or `:8001/mcp` for `/mcp/`)
  and returns the upstream response unchanged

### Requirement: Real client IP from Cloudflare

nginx SHALL derive the client address from the `CF-Connecting-IP` header,
trusting it only from `127.0.0.1` (the local `cloudflared`), and SHALL
apply the `/api/*` and `/mcp/*` rate limits and access logging to that
address.

#### Scenario: Rate limit keys on the real client
- **WHEN** one client sends a burst above `limit_req` on `/api/*` through
  the tunnel
- **THEN** that client receives `503` for the excess while other clients
  behind the same tunnel are unaffected

### Requirement: Cache behaviour by route

Cloudflare SHALL NOT cache `/api/*` or `/mcp/*` responses. Static assets
under `/static/*` MAY be cached at the edge; the installer SHALL keep
stamping `?v=<commit>` into static URLs so a deploy never serves stale
assets against fresh HTML.

#### Scenario: API responses are not cached
- **WHEN** a client requests `/api/v1/snapshots/latest/` twice
- **THEN** both responses carry `cf-cache-status: DYNAMIC` (or `BYPASS`)

#### Scenario: Static asset is cacheable
- **WHEN** a client requests `/static/app.js?v=<sha>`
- **THEN** repeated requests MAY return `cf-cache-status: HIT`
- **AND** a new deploy changes the URL, so no client receives an old asset

### Requirement: Edge configuration lives in the repo

The tunnel ingress rules SHALL be rendered by `deploy/install.sh` from
`deploy/cloudflared/config.yml.template` using values in
`/etc/alt-bitnodes/cloudflared.env`; the tunnel credentials file SHALL be
created once at provisioning and never by the installer. Re-running the
installer SHALL be idempotent for the tunnel, nginx and their units.

#### Scenario: Re-run leaves the tunnel up
- **WHEN** `install.sh` runs on a host with a working tunnel and unchanged
  `cloudflared.env`
- **THEN** `cloudflared.service` is not restarted and the public hostname
  stays reachable throughout

#### Scenario: Hostname change is picked up
- **WHEN** `PUBLIC_HOST` in `cloudflared.env` changes and `install.sh` runs
- **THEN** the rendered config changes, `cloudflared` restarts, and the new
  hostname routes to nginx

### Requirement: Operational documentation for the Cloudflare edge

`deploy/README.md` SHALL document: the nameserver move, tunnel creation,
public hostnames and cache rules, the Access application for SSH, the
contents of `cloudflared.env`, smoke tests, and rollback (re-pointing the
CNAME while an alternative origin exists).

#### Scenario: Operator provisions a fresh host
- **WHEN** an operator follows `deploy/README.md` on a bare Ubuntu 24.04 VM
- **THEN** they reach a serving host without consulting any AWS document

## REMOVED Requirements

### Requirement: TLS público vía CloudFront
**Reason**: Production leaves AWS; TLS is terminated by Cloudflare in front
of a tunnel. **Migration**: see "Public TLS via Cloudflare Tunnel".

### Requirement: Aislamiento del origin EC2
**Reason**: There is no security group, no prefix list and no shared
secret; the origin has no inbound path at all. **Migration**: see "Origin
isolation by construction".

### Requirement: Cache diferenciado por tipo de ruta
**Reason**: CloudFront cache policies are replaced by Cloudflare cache
rules. **Migration**: see "Cache behaviour by route".

### Requirement: Rate limiting en el origin
**Reason**: Same nginx mechanism, different real-IP source. **Migration**:
see "Real client IP from Cloudflare".

### Requirement: Despliegue automatizado e idempotente
**Reason**: The CloudFormation bootstrap is gone. **Migration**: see "Edge
configuration lives in the repo".

### Requirement: Documentación operativa para DNS externo
**Reason**: DNS is at Cloudflare and there are no ACM validation records.
**Migration**: see "Operational documentation for the Cloudflare edge".
