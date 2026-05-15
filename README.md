# alt-bitnodes

[Español](#alt-bitnodes-es) · [English](#alt-bitnodes-en)

---

<a id="alt-bitnodes-es"></a>

## alt-bitnodes (Español)

[Ir a la versión en inglés](#alt-bitnodes-en)

Dashboard y API públicos de tipo bitnodes.io para la red Bitcoin: snapshots de
nodos alcanzables y rankings por país, ASN y user-agent.

### Contexto

[bitnodes.io](https://bitnodes.io) (Addy Yeow, 2013-2024) fue la referencia
pública para inspeccionar la red Bitcoin: payload de snapshots, distribución
geográfica y banderas de seeders DNS. Su API dejó de mantenerse y los
endpoints originales ya no son fiables.

Este proyecto es un sucesor:

- Reutiliza el crawler upstream `ayeowch/bitnodes` (mantenido aquí en el fork
  [`ifuensan/bitnodes`](https://github.com/ifuensan/bitnodes), rama
  `fix/empty-include-asns`), que sigue siendo la pieza correcta para descubrir
  nodos y hacer handshake.
- Añade una capa propia (`alt-bitnodes`, este repositorio) con FastAPI que
  expone una API v1 estable más un dashboard HTML mínimo.
- Convive en una sola instancia (Ubuntu 24.04 ARM, **c7g.2xlarge** en
  AWS): consulta Redis para el estado vivo y los JSON de export para los
  snapshots. Sirve público en `https://pesquisa.hacknodes.xyz` detrás de
  CloudFront (TLS + cache de estáticos) con nginx como reverse proxy en el
  origen.

El alcance es deliberadamente acotado: no se intenta reproducir todas las
secciones de bitnodes.io, solo las que tienen valor analítico (snapshots y
rankings).

### Arquitectura

```
┌───────────────────────────────────────────────────────────────────────┐
│                       BITCOIN P2P NETWORK                             │
│                     (peers públicos en Internet)                      │
└──────────────────┬────────────────────────────────────────────────────┘
                   │  handshake / peers (Bitcoin)
                   ▼
            ┌─────────────┐
            │  crawl.py   │
            │  (5 procs)  │
            └──────┬──────┘
                   │
                   ▼
        ┌──────────────────────────────────────────────────┐
        │                   REDIS  (vivo)                  │
        │   opendata · up · node:* · height · ip:* · …     │
        └─────┬────────────────────────────────────────────┘
              │
   export.py  │
   cada       │
   ~10 min    ▼
        ┌────────────────────┐
        │ data/export/       │
        │   <ts>.json        │
        │ (snapshot completo │
        │  de la red)        │
        └─────────┬──────────┘
                  │
                  ▼
                  ┌──────────────────────────────────┐
                  │   FastAPI  :8000                 │
                  │   - lee Redis (estado vivo)      │
                  │   - lee data/export/*.json       │
                  └────────────────┬─────────────────┘
                                   │ HTTP/JSON
                                   ▼
                            Browser / curl


────────────────────────────────────────────────────────────────────────
LOGS DE TEXTO (canal aparte, NO son datos del producto — son diagnóstico)
────────────────────────────────────────────────────────────────────────
  bitnodes/log/crawl.f9beb4d9.log         ← actividad del crawler
  bitnodes/log/ping.f9beb4d9.log          ← actividad de ping
  bitnodes/log/export.f9beb4d9.log        ← cuándo se generan snapshots
  journalctl -u bitnodes / -u alt-bitnodes  (systemd)
```

### Almacenes

| Almacén | Tipo | Rol | Persistencia |
|---|---|---|---|
| Redis | KV en RAM | Estado vivo de la red | TTL 1-3 h, volátil |
| `data/export/*.json` | JSON | Snapshot histórico completo de la red | Permanente |
| `log/*.log` + journalctl | Texto | Diagnóstico operacional | No es dato de negocio |

### Endpoints v1 principales

```
GET /api/v1/snapshots/                 lista de snapshots disponibles
GET /api/v1/snapshots/latest/          snapshot más reciente
GET /api/v1/nodes/{addr}-{port}/       detalle de un nodo
GET /api/v1/rankings/countries/        agregado por país
GET /api/v1/rankings/asns/             agregado por ASN
GET /api/v1/rankings/user-agents/      agregado por user-agent
GET /api/v1/groups/by-ip/              IPs que hospedan más de un nodo
```

### Geolocalización (GeoIP)

País, ASN, ciudad y zona horaria de cada nodo se resuelven contra las bases
**MaxMind GeoLite2** (gratuitas) que `bitnodes/resolve.py` consulta en cada
ciclo:

- `GeoLite2-City.mmdb` — ciudad, lat/lon, zona horaria.
- `GeoLite2-Country.mmdb` — código ISO de país.
- `GeoLite2-ASN.mmdb` — ASN y nombre del operador.

Las `.mmdb` viven en `bitnodes/geoip/` y se versionan en git con un snapshot
inicial. MaxMind republica las bases martes y viernes, así que se quedan
obsoletas con el tiempo. En producción una unidad systemd
`geoip-update.timer` las refresca cada miércoles 06:00 UTC ejecutando
`geoip/update.sh`, que requiere una license key gratuita de MaxMind en
`bitnodes/geoip/.maxmind_license_key` (ya excluido de git). Detalles y pasos
de activación en [`deploy/README.md`](deploy/README.md#maxmind-geolite2-refresh).

### Despliegue

Para AWS (instancia única, Ubuntu 24.04 ARM64) ver [`deploy/README.md`](deploy/README.md):
crea la instancia, ejecuta `install.sh` (idempotente, instala redis, pyenv,
clona los dos repos, deja las unidades systemd `bitnodes` / `alt-bitnodes` /
`alt-bitnodes-mcp` / `geoip-update.timer`).

El dashboard escucha en `127.0.0.1:8000` y se accede vía túnel SSH:

```
ssh -L 8000:127.0.0.1:8000 ubuntu@<host>
```

### Especificaciones

Las capabilities están versionadas con OpenSpec en `openspec/`:

- `rankings-api` — rankings agregados y same-IP groups.
- `crawler-systemd-units` — contrato de unidades systemd del crawler.
- `mcp-service` — servidor MCP que expone los mismos datos.
- `public-edge` — CloudFront + nginx en el origen.
- `dashboard-bar-charts`, `dashboard-design-system` — frontend.

---

<a id="alt-bitnodes-en"></a>

## alt-bitnodes (English)

[Go to Spanish version](#alt-bitnodes-es)

A bitnodes.io-style public dashboard and API for the Bitcoin network:
reachable-node snapshots and rankings by country, ASN, and user-agent.

### Context

[bitnodes.io](https://bitnodes.io) (Addy Yeow, 2013-2024) was the public
reference for inspecting the Bitcoin network: snapshot payloads, geographic
distribution, and DNS-seeder service flags. Its API is no longer maintained
and the original endpoints are no longer reliable.

This project is a successor:

- Reuses the upstream `ayeowch/bitnodes` crawler (maintained here in the fork
  [`ifuensan/bitnodes`](https://github.com/ifuensan/bitnodes), branch
  `fix/empty-include-asns`), which is still the right component for peer
  discovery and handshakes.
- Adds a separate layer (`alt-bitnodes`, this repository) with FastAPI that
  exposes a stable v1 API plus a minimal HTML dashboard.
- Runs alongside the crawler on a single host (Ubuntu 24.04 ARM,
  **c7g.2xlarge** on AWS): reads Redis for live state and the export JSONs
  for snapshots. Public at `https://pesquisa.hacknodes.xyz` behind
  CloudFront (TLS + static cache) with nginx as the origin reverse proxy.

Scope is deliberately narrow: no attempt to reproduce every section of
bitnodes.io, only those with analytical value (snapshots and rankings).

### Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                       BITCOIN P2P NETWORK                             │
│                       (public peers on the Internet)                  │
└──────────────────┬────────────────────────────────────────────────────┘
                   │  handshake / peers (Bitcoin)
                   ▼
            ┌─────────────┐
            │  crawl.py   │
            │  (5 procs)  │
            └──────┬──────┘
                   │
                   ▼
        ┌──────────────────────────────────────────────────┐
        │                   REDIS  (live)                  │
        │   opendata · up · node:* · height · ip:* · …     │
        └─────┬────────────────────────────────────────────┘
              │
   export.py  │
   every      │
   ~10 min    ▼
        ┌────────────────────┐
        │ data/export/       │
        │   <ts>.json        │
        │ (full network      │
        │  snapshot)         │
        └─────────┬──────────┘
                  │
                  ▼
                  ┌──────────────────────────────────┐
                  │   FastAPI  :8000                 │
                  │   - reads Redis (live state)     │
                  │   - reads data/export/*.json     │
                  └────────────────┬─────────────────┘
                                   │ HTTP/JSON
                                   ▼
                            Browser / curl


────────────────────────────────────────────────────────────────────────
TEXT LOGS (separate channel, NOT product data — operational only)
────────────────────────────────────────────────────────────────────────
  bitnodes/log/crawl.f9beb4d9.log         ← crawler activity
  bitnodes/log/ping.f9beb4d9.log          ← ping activity
  bitnodes/log/export.f9beb4d9.log        ← when snapshots are produced
  journalctl -u bitnodes / -u alt-bitnodes  (systemd)
```

### Stores

| Store | Type | Role | Persistence |
|---|---|---|---|
| Redis | In-memory KV | Live network state | TTL 1-3 h, volatile |
| `data/export/*.json` | JSON | Full network snapshots history | Permanent |
| `log/*.log` + journalctl | Text | Operational diagnostics | Not product data |

### Main v1 endpoints

```
GET /api/v1/snapshots/                 list available snapshots
GET /api/v1/snapshots/latest/          most recent snapshot
GET /api/v1/nodes/{addr}-{port}/       node detail
GET /api/v1/rankings/countries/        per-country aggregate
GET /api/v1/rankings/asns/             per-ASN aggregate
GET /api/v1/rankings/user-agents/      per-user-agent aggregate
GET /api/v1/groups/by-ip/              IPs hosting more than one node
```

### Geolocation (GeoIP)

Country, ASN, city, and timezone for each node are resolved against the
**MaxMind GeoLite2** databases (free tier), queried by `bitnodes/resolve.py`
on every cycle:

- `GeoLite2-City.mmdb` — city, lat/lon, timezone.
- `GeoLite2-Country.mmdb` — ISO country code.
- `GeoLite2-ASN.mmdb` — ASN and operator name.

The `.mmdb` files live under `bitnodes/geoip/` and are versioned in git as an
initial snapshot. MaxMind republishes Tuesdays and Fridays, so the shipped
copy goes stale. In production a `geoip-update.timer` systemd unit refreshes
them every Wednesday at 06:00 UTC by running `geoip/update.sh`, which
requires a free MaxMind license key at `bitnodes/geoip/.maxmind_license_key`
(already excluded from git). Details and activation steps in
[`deploy/README.md`](deploy/README.md#maxmind-geolite2-refresh).

### Deployment

For AWS (single instance, Ubuntu 24.04 ARM64) see
[`deploy/README.md`](deploy/README.md): create the instance, run `install.sh`
(idempotent — installs redis, pyenv, clones both repos, drops the systemd
units `bitnodes` / `alt-bitnodes` / `alt-bitnodes-mcp` /
`geoip-update.timer`).

The dashboard listens on `127.0.0.1:8000` and is reached over an SSH tunnel:

```
ssh -L 8000:127.0.0.1:8000 ubuntu@<host>
```

### Specifications

Capabilities are versioned with OpenSpec under `openspec/`:

- `rankings-api` — aggregated rankings and same-IP groups.
- `crawler-systemd-units` — crawler systemd-unit contract.
- `mcp-service` — MCP server exposing the same data.
- `public-edge` — CloudFront + nginx at the origin.
- `dashboard-bar-charts`, `dashboard-design-system` — frontend.
