# alt-bitnodes

[Español](#alt-bitnodes-es) · [English](#alt-bitnodes-en)

---

<a id="alt-bitnodes-es"></a>

## alt-bitnodes (Español)

[Ir a la versión en inglés](#alt-bitnodes-en)

Dashboard y API públicos de tipo bitnodes.io para la red Bitcoin: snapshots de
nodos alcanzables, latencias por nodo, leaderboards y rankings por país, ASN y
user-agent.

### Contexto

[bitnodes.io](https://bitnodes.io) (Addy Yeow, 2013-2024) fue la referencia
pública para inspeccionar la red Bitcoin: payload de snapshots, distribución
geográfica, latencias y banderas de seeders DNS. Su API dejó de mantenerse y
los endpoints originales ya no son fiables.

Este proyecto es un sucesor:

- Reutiliza el crawler upstream `ayeowch/bitnodes` (mantenido aquí en el fork
  [`ifuensan/bitnodes`](https://github.com/ifuensan/bitnodes), rama
  `fix/empty-include-asns`), que sigue siendo la pieza correcta para descubrir
  nodos, hacer handshake y emitir pings.
- Añade una capa propia (`alt-bitnodes`, este repositorio) con FastAPI + SQLite
  que persiste el RTT por nodo y expone una API v1 estable, además de un
  dashboard HTML mínimo.
- Convive en una sola instancia (Ubuntu 24.04 ARM, t4g.medium en AWS):
  consulta Redis para el estado vivo y SQLite para histórico.

El alcance es deliberadamente acotado: no se intenta reproducir todas las
secciones de bitnodes.io, solo las que tienen valor analítico (snapshots,
fastest nodes, rankings, latencia por nodo).

### Arquitectura

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         BITCOIN P2P NETWORK                               │
│                       (peers públicos en Internet)                        │
└──────────────────┬───────────────┬────────────────────┬───────────────────┘
                   │               │                    │ paquetes con magic
   handshake/peers │   ping/pong   │                    │ f9beb4d9 (BPF)
                   │  (Bitcoin)    │                    │
                   ▼               ▼                    ▼
            ┌─────────────┐ ┌─────────────┐  ┌────────────────────────────┐
            │  crawl.py   │ │  ping.py    │  │  tcpdump  (captura pasiva  │
            │  (5 procs)  │ │ (16 procs)  │  │   del NIC, drop privs -Z)  │
            └──────┬──────┘ └──────┬──────┘  └─────────────┬──────────────┘
                   │               │                       │
                   │               │                       ▼
                   │               │         ┌──────────────────────────┐
                   │               │         │ data/pcap/f9beb4d9/      │
                   │               │         │   *.pcap  (binario,      │
                   │               │         │   rotado -G 30s -W 8)    │
                   │               │         └─────────────┬────────────┘
                   │               │                       │ "oldest first"
                   │               │                       ▼
                   │               │         ┌──────────────────────────┐
                   │               │         │  cache_inv.py (3 procs)  │
                   │               │         │   parsea pcap → mensajes │
                   │               │         │   Bitcoin (pong, inv…)   │
                   │               │         └─────────────┬────────────┘
                   │               │                       │
                   │  ping_send_ts │                       │ pong_recv_ts
                   │  (lpush)      ▼                       ▼
                   │       ┌───────────────────────────────────┐
                   │       │  ping:<addr>-<port>:<nonce>       │ ← TTL 3 h
                   │       │       = [send_ts_ms, pong_ts_ms]  │
                   │       └─────────────────┬─────────────────┘
                   │                         │ rtt = pong - ping
                   │                         ▼
                   │       ┌───────────────────────────────────┐
                   │       │  rtt:<addr>-<port>  = [rtt_ms,…]  │ ← 36 últimas,
                   │       │  (lpush + ltrim a rtt_count=36)   │   TTL 1 día
                   │       └───────────────────────────────────┘
                   ▼
        ┌──────────────────────────────────────────────────┐
        │                   REDIS  (vivo)                  │
        │   opendata · up · node:* · height · ip:* · …     │
        │   ping:* · rtt:*                                 │
        └─────┬───────────────────────┬────────────────────┘
              │                       │
   export.py  │                       │ alt-bitnodes ingest task
   cada       │                       │ cada 30 s:
   ~10 min    ▼                       │   SCAN rtt:* → INSERT OR IGNORE
        ┌────────────────────┐        ▼
        │ data/export/       │  ┌──────────────────────────┐
        │   <ts>.json        │  │ data/rtt.sqlite          │
        │ (snapshot completo │  │   rtt_samples            │
        │  de la red)        │  │   (PK addr,port,ts,rtt)  │
        └─────────┬──────────┘  │   retención 30 días      │
                  │             └─────────────┬────────────┘
                  │                           │
                  └─────────────┬─────────────┘
                                ▼
                  ┌──────────────────────────────────┐
                  │   FastAPI  :8000                 │
                  │   - lee Redis (estado vivo)      │
                  │   - lee data/export/*.json       │
                  │   - lee data/rtt.sqlite          │
                  │     (medianas + time series)     │
                  └────────────────┬─────────────────┘
                                   │ HTTP/JSON
                                   ▼
                            Browser / curl


─────────────────────────────────────────────────────────────────────────────
LOGS DE TEXTO  (canal aparte, NO son datos del producto — son diagnóstico)
─────────────────────────────────────────────────────────────────────────────
  bitnodes/log/crawl.f9beb4d9.log         ← actividad del crawler
  bitnodes/log/ping.f9beb4d9.log          ← actividad de ping
  bitnodes/log/cache_inv.f9beb4d9.log     ← pkt=N tx=N pong=N por pcap
  bitnodes/log/export.f9beb4d9.log        ← cuándo se generan snapshots
  journalctl -u bitnodes / -u tcpdump-pcap / -u alt-bitnodes  (systemd)
```

### Almacenes

| Almacén | Tipo | Rol | Persistencia |
|---|---|---|---|
| Redis | KV en RAM | Estado vivo de la red, RTTs recientes | TTL 1-3 h, volátil |
| `data/pcap/*.pcap` | Binario | Buffer transitorio para `cache_inv` | Rotado, ~4 min |
| `data/export/*.json` | JSON | Snapshot histórico completo de la red | Permanente |
| `data/rtt.sqlite` | SQLite | Histórico de latencias por nodo | 30 días configurable |
| `log/*.log` + journalctl | Texto | Diagnóstico operacional | No es dato de negocio |

`tcpdump` no produce logs textuales: produce pcap binario que es la entrada de
`cache_inv`. Los logs de texto vienen de los procesos Python y de systemd.

### Flujo de una medida de latencia

1. `ping.py` envía un mensaje Bitcoin `ping(nonce)` a un peer y guarda el
   timestamp del envío en Redis bajo `ping:<addr>-<port>:<nonce>`.
2. `tcpdump` (filtro BPF por magic `f9beb4d9`) captura el `pong(nonce)` de
   respuesta cuando entra por el NIC y lo escribe a un fichero `.pcap`.
3. `cache_inv.py` lee el pcap más antiguo, parsea los mensajes Bitcoin, y para
   cada `pong` válido hace `rpushx` del timestamp de recepción sobre la misma
   clave `ping:<addr>-<port>:<nonce>`.
4. Cuando esa lista tiene los dos timestamps, `cache_inv.cache_rtt()` calcula
   `rtt_ms = pong_ts - ping_ts` y hace `lpush` sobre `rtt:<addr>-<port>`,
   manteniendo solo las 36 últimas muestras.
5. El proceso ingest del dashboard hace `SCAN rtt:*` cada 30 s y persiste las
   muestras nuevas en `data/rtt.sqlite`.
6. La API consulta SQLite para calcular medianas en ventana, time series por
   nodo y rankings agregados.

### Endpoints v1 principales

```
GET /api/v1/snapshots/                 lista de snapshots disponibles
GET /api/v1/snapshots/latest/          snapshot más reciente con latency_ms
GET /api/v1/nodes/{addr}-{port}/       detalle de un nodo
GET /api/v1/nodes/{addr}-{port}/latency/?hours=N    serie temporal RTT
GET /api/v1/leaderboard/?limit=N       fastest nodes
GET /api/v1/rankings/countries/        agregado por país
GET /api/v1/rankings/asns/             agregado por ASN
GET /api/v1/rankings/user-agents/      agregado por user-agent
GET /api/v1/groups/by-ip/              IPs que hospedan más de un nodo
```

`latency_ms` es la mediana de las muestras de RTT del nodo dentro de
`RTT_WINDOW_SECONDS` (1800 s por defecto), o `null` si no hay muestras en la
ventana.

### Despliegue

Para AWS (instancia única, Ubuntu 24.04 ARM64) ver [`deploy/README.md`](deploy/README.md):
crea la instancia, ejecuta `install.sh` (idempotente, instala redis, pyenv,
clona los dos repos, deja las tres unidades systemd `bitnodes` /
`tcpdump-pcap` / `alt-bitnodes`).

El dashboard escucha en `127.0.0.1:8000` y se accede vía túnel SSH:

```
ssh -L 8000:127.0.0.1:8000 ubuntu@<host>
```

### Especificaciones

Las capabilities están versionadas con OpenSpec en `openspec/`:

- `rtt-history` — persistencia de RTTs en SQLite e ingesta desde Redis.
- `latency-api` — endpoints v1 con `latency_ms` y time series.
- `rankings-api` — leaderboard, rankings y same-IP groups.

---

<a id="alt-bitnodes-en"></a>

## alt-bitnodes (English)

[Go to Spanish version](#alt-bitnodes-es)

A bitnodes.io-style public dashboard and API for the Bitcoin network:
reachable-node snapshots, per-node latencies, leaderboards, and rankings by
country, ASN, and user-agent.

### Context

[bitnodes.io](https://bitnodes.io) (Addy Yeow, 2013-2024) was the public
reference for inspecting the Bitcoin network: snapshot payloads, geographic
distribution, latencies, and DNS-seeder service flags. Its API is no longer
maintained and the original endpoints are no longer reliable.

This project is a successor:

- Reuses the upstream `ayeowch/bitnodes` crawler (maintained here in the fork
  [`ifuensan/bitnodes`](https://github.com/ifuensan/bitnodes), branch
  `fix/empty-include-asns`), which is still the right component for peer
  discovery, handshakes, and ping emission.
- Adds a separate layer (`alt-bitnodes`, this repository) with FastAPI +
  SQLite that persists per-node RTT and exposes a stable v1 API, plus a
  minimal HTML dashboard.
- Runs alongside the crawler on a single host (Ubuntu 24.04 ARM, t4g.medium
  on AWS): reads Redis for live state and SQLite for history.

Scope is deliberately narrow: no attempt to reproduce every section of
bitnodes.io, only those with analytical value (snapshots, fastest nodes,
rankings, per-node latency).

### Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         BITCOIN P2P NETWORK                               │
│                        (public peers on the Internet)                     │
└──────────────────┬───────────────┬────────────────────┬───────────────────┘
                   │               │                    │ packets with magic
   handshake/peers │   ping/pong   │                    │ f9beb4d9 (BPF)
                   │  (Bitcoin)    │                    │
                   ▼               ▼                    ▼
            ┌─────────────┐ ┌─────────────┐  ┌────────────────────────────┐
            │  crawl.py   │ │  ping.py    │  │  tcpdump (passive capture  │
            │  (5 procs)  │ │ (16 procs)  │  │   from NIC, drop privs -Z) │
            └──────┬──────┘ └──────┬──────┘  └─────────────┬──────────────┘
                   │               │                       │
                   │               │                       ▼
                   │               │         ┌──────────────────────────┐
                   │               │         │ data/pcap/f9beb4d9/      │
                   │               │         │   *.pcap  (binary,       │
                   │               │         │   rotated -G 30s -W 8)   │
                   │               │         └─────────────┬────────────┘
                   │               │                       │ "oldest first"
                   │               │                       ▼
                   │               │         ┌──────────────────────────┐
                   │               │         │  cache_inv.py (3 procs)  │
                   │               │         │   parses pcap → Bitcoin  │
                   │               │         │   messages (pong, inv…)  │
                   │               │         └─────────────┬────────────┘
                   │               │                       │
                   │  ping_send_ts │                       │ pong_recv_ts
                   │  (lpush)      ▼                       ▼
                   │       ┌───────────────────────────────────┐
                   │       │  ping:<addr>-<port>:<nonce>       │ ← TTL 3 h
                   │       │       = [send_ts_ms, pong_ts_ms]  │
                   │       └─────────────────┬─────────────────┘
                   │                         │ rtt = pong - ping
                   │                         ▼
                   │       ┌───────────────────────────────────┐
                   │       │  rtt:<addr>-<port>  = [rtt_ms,…]  │ ← last 36,
                   │       │  (lpush + ltrim to rtt_count=36)  │   TTL 1 day
                   │       └───────────────────────────────────┘
                   ▼
        ┌──────────────────────────────────────────────────┐
        │                   REDIS  (live)                  │
        │   opendata · up · node:* · height · ip:* · …     │
        │   ping:* · rtt:*                                 │
        └─────┬───────────────────────┬────────────────────┘
              │                       │
   export.py  │                       │ alt-bitnodes ingest task
   every      │                       │ every 30 s:
   ~10 min    ▼                       │   SCAN rtt:* → INSERT OR IGNORE
        ┌────────────────────┐        ▼
        │ data/export/       │  ┌──────────────────────────┐
        │   <ts>.json        │  │ data/rtt.sqlite          │
        │ (full network      │  │   rtt_samples            │
        │  snapshot)         │  │   (PK addr,port,ts,rtt)  │
        └─────────┬──────────┘  │   30-day retention       │
                  │             └─────────────┬────────────┘
                  │                           │
                  └─────────────┬─────────────┘
                                ▼
                  ┌──────────────────────────────────┐
                  │   FastAPI  :8000                 │
                  │   - reads Redis (live state)     │
                  │   - reads data/export/*.json     │
                  │   - reads data/rtt.sqlite        │
                  │     (medians + time series)      │
                  └────────────────┬─────────────────┘
                                   │ HTTP/JSON
                                   ▼
                            Browser / curl


─────────────────────────────────────────────────────────────────────────────
TEXT LOGS  (separate channel, NOT product data — operational only)
─────────────────────────────────────────────────────────────────────────────
  bitnodes/log/crawl.f9beb4d9.log         ← crawler activity
  bitnodes/log/ping.f9beb4d9.log          ← ping activity
  bitnodes/log/cache_inv.f9beb4d9.log     ← pkt=N tx=N pong=N per pcap
  bitnodes/log/export.f9beb4d9.log        ← when snapshots are produced
  journalctl -u bitnodes / -u tcpdump-pcap / -u alt-bitnodes  (systemd)
```

### Stores

| Store | Type | Role | Persistence |
|---|---|---|---|
| Redis | In-memory KV | Live network state, recent RTTs | TTL 1-3 h, volatile |
| `data/pcap/*.pcap` | Binary | Transient buffer for `cache_inv` | Rotated, ~4 min |
| `data/export/*.json` | JSON | Full network snapshots history | Permanent |
| `data/rtt.sqlite` | SQLite | Per-node latency history | 30 days, configurable |
| `log/*.log` + journalctl | Text | Operational diagnostics | Not product data |

`tcpdump` does not produce text logs: it writes binary pcap files that are
`cache_inv`'s input. Text logs come from the Python processes and from
systemd.

### Lifecycle of a latency measurement

1. `ping.py` sends a Bitcoin `ping(nonce)` message to a peer and stores the
   send timestamp in Redis under `ping:<addr>-<port>:<nonce>`.
2. `tcpdump` (BPF filter on magic `f9beb4d9`) captures the corresponding
   `pong(nonce)` as it arrives on the NIC and writes it to a `.pcap` file.
3. `cache_inv.py` reads the oldest pcap, parses Bitcoin messages, and for
   each valid `pong` does an `rpushx` of the receive timestamp onto the same
   `ping:<addr>-<port>:<nonce>` key.
4. Once that list holds both timestamps, `cache_inv.cache_rtt()` computes
   `rtt_ms = pong_ts - ping_ts` and `lpush`es it onto `rtt:<addr>-<port>`,
   capped at the 36 most recent samples.
5. The dashboard's ingest task `SCAN`s `rtt:*` every 30 s and writes new
   samples into `data/rtt.sqlite`.
6. The API queries SQLite to compute window medians, per-node time series,
   and aggregated rankings.

### Main v1 endpoints

```
GET /api/v1/snapshots/                 list available snapshots
GET /api/v1/snapshots/latest/          most recent snapshot, with latency_ms
GET /api/v1/nodes/{addr}-{port}/       node detail
GET /api/v1/nodes/{addr}-{port}/latency/?hours=N    RTT time series
GET /api/v1/leaderboard/?limit=N       fastest nodes
GET /api/v1/rankings/countries/        per-country aggregate
GET /api/v1/rankings/asns/             per-ASN aggregate
GET /api/v1/rankings/user-agents/      per-user-agent aggregate
GET /api/v1/groups/by-ip/              IPs hosting more than one node
```

`latency_ms` is the median of the node's RTT samples within
`RTT_WINDOW_SECONDS` (1800 s by default), or `null` when no samples exist
in the window.

### Deployment

For AWS (single instance, Ubuntu 24.04 ARM64) see
[`deploy/README.md`](deploy/README.md): create the instance, run `install.sh`
(idempotent — installs redis, pyenv, clones both repos, drops the three
systemd units `bitnodes` / `tcpdump-pcap` / `alt-bitnodes`).

The dashboard listens on `127.0.0.1:8000` and is reached over an SSH tunnel:

```
ssh -L 8000:127.0.0.1:8000 ubuntu@<host>
```

### Specifications

Capabilities are versioned with OpenSpec under `openspec/`:

- `rtt-history` — RTT persistence in SQLite and ingest from Redis.
- `latency-api` — v1 endpoints with `latency_ms` and time series.
- `rankings-api` — leaderboard, rankings, and same-IP groups.
