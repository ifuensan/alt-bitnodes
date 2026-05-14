## Context

Pipeline de RTT actual (verificado en el crawler `ifuensan/bitnodes`, 2026-05-14):

```
tcpdump-pcap.service ──▶ pcaps ──▶ cache_inv.py ×3 ──┬──▶ rtt:<addr>-<port>  (Redis list)
  (run-tcpdump.sh,                  (lee pong+inv      │      │
   tcpdump -G30 -W8)                 de pcap.py)        │      └──▶ dashboard ingest → SQLite → latency-api  ✓ USADO
                                                        └──▶ inv:1:* / inv:2:*  (propagación tx/bloque)     ✗ alt-bitnodes no lo expone
crawl.py ──▶ height:<addr>-<port>-<services> ──▶ export.py ──▶ snapshot.height                              ✓ independiente del pcap
```

Hallazgos clave de la exploración:
- `rtt:*` lo escribe **solo** `cache_inv.py:201` (`rtt_key = f"rtt:{node}"`), de los `pong` extraídos de pcaps.
- `cache_inv` también escribe `inv:*` (propagación) — ningún endpoint de `alt-bitnodes` lo consume.
- `height:*` lo escribe `crawl.py` del `version` handshake; `export.py` lo lee para el snapshot. No toca el pcap.
- `ping.py` del crawler **ya** envía `ping` y recibe `pong` (el follow-up lo describía: "already sends pings; needs to also record the RTT timestamp when the matching pong arrives").
- `cache_inv` no puede separarse de los pcaps: si se mantuviera por los `inv`, seguiría necesitando tcpdump. Eliminar el sniffer **obliga** a eliminar cache_inv.

`rtt-history` (spec del dashboard) describe la ingesta de `rtt:*` de forma **agnóstica al productor** — su Purpose dice "sourced from the upstream `rtt:*` Redis lists". Cambiar quién escribe `rtt:*` es transparente para el dashboard si se respeta el formato.

## Goals / Non-Goals

**Goals:**
- `ping.py` escribe `rtt:<addr>-<port>` directamente, con el mismo formato de lista, `ttl` y `rtt_count` que `cache_inv` usaba — el dashboard no nota el cambio.
- Eliminar del todo el pipeline pcap: `tcpdump-pcap.service`, `run-tcpdump.sh`, `cache_inv.py`, `pcap.py`, `start_pcap.sh`, `pcap-cleanup.*`.
- Snapshots estables (sin sniffer) **y** RTT con datos — resolver la tensión que `fix-tcpdump-revival` dejaba abierta.
- Cerrar el follow-up "Replace pcap-based RTT with active pings".

**Non-Goals:**
- No cambiar el contrato de `rtt:*` en Redis ni la ingesta del dashboard (`rtt-history`, `latency-api` quedan intactos).
- No reintroducir ni reemplazar la propagación de `inv`/bloques — es una renuncia explícita (alt-bitnodes no la expone hoy).
- No tocar el dashboard (`app.py`, `queries/`), el MCP server, ni `crawl.py`/`export.py` (la height sigue igual).
- No abordar las RTT multi-localización (sigue en el backlog, es otra cosa).

## Decisions

### Decisión 1 — `ping.py` registra el RTT en el ciclo ping/pong que ya ejecuta

`ping.py` ya manda `ping` con un nonce y recibe el `pong` correspondiente. El cambio: al emparejar el `pong` con su `ping`, calcular `rtt = now - ping_sent_ts` y hacer el equivalente de lo que hacía `cache_inv.cache_rtt()`:

```
rtt_key = f"rtt:{addr}-{port}"
redis.lpush(rtt_key, rtt_ms)
redis.ltrim(rtt_key, 0, rtt_count - 1)
redis.expire(rtt_key, ttl)
```

Los parámetros `rtt_count` y `ttl` se toman de la config de `ping.py` (o se portan los de `cache_inv.*.conf`). El dashboard ingiere `rtt:*` igual que hoy.

**Alternativa considerada**: un proceso nuevo dedicado al RTT. Descartado — `ping.py` ya tiene el socket abierto y el ciclo ping/pong; añadir el registro es marginal. Un proceso aparte duplicaría conexiones a los mismos peers.

**Alternativa considerada**: registrar el RTT en `crawl.py` (que ya hace el handshake). Descartado — `crawl.py` hace una conexión efímera por nodo; `ping.py` es el que mantiene el ciclo periódico, que es la semántica correcta de "RTT a lo largo del tiempo".

### Decisión 2 — Eliminar cache_inv y todo el pipeline pcap, no solo desactivarlo

Una vez `ping.py` produce `rtt:*`, `cache_inv` solo aportaría `inv:*` (no usado). Y `cache_inv` no funciona sin pcaps. Por tanto se elimina el conjunto entero:

- Fork `ifuensan/bitnodes`: `cache_inv.py`, `pcap.py`, `start_pcap.sh`, las 3 líneas de `cache_inv` en `run-bitnodes.sh`, y `conf/cache_inv.*.conf*`.
- `alt-bitnodes`: `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service`, `deploy/pcap-cleanup.timer`, y su instalación/saneamiento en `deploy/install.sh`.

**Alternativa considerada**: dejar cache_inv "por si acaso" la propagación de `inv` se quiere algún día. Descartado — código muerto que necesita tcpdump vivo para no romperse, justo lo que queremos eliminar. Si la propagación se necesita en el futuro, será un cambio propio con su propio diseño (probablemente activo, no pcap).

### Decisión 3 — Orden de despliegue: fork primero, alt-bitnodes después

```
1. Fork ifuensan/bitnodes:
   a. ping.py escribe rtt:*  ──┐
   b. quitar cache_inv de      │ desplegar, confirmar que rtt:* se puebla
      run-bitnodes.sh          │ con el crawler aún capaz de leer pcaps viejos
   c. borrar cache_inv.py/     │ (no hay regresión: el dashboard ve rtt:* de ping.py)
      pcap.py/start_pcap.sh  ──┘
2. alt-bitnodes:
   d. borrar units pcap + limpiar install.sh
   e. deploy → install.sh deja de instalar/sanear nada de pcap
3. Verificar: latency_ms y leaderboard con datos; snapshots estables.
```

Hacer el fork primero garantiza que `rtt:*` nunca se queda sin productor: en el momento en que `cache_inv` se retira, `ping.py` ya está escribiendo.

### Decisión 4 — Relación con `fix-tcpdump-revival`

`fix-tcpdump-revival` quita el `Wants=tcpdump-pcap.service` de `bitnodes.service` (hotfix, tcpdump deja de revivir, RTT a `null`). `active-ping-rtt` lo asume hecho y va más allá: borra la unit del todo y devuelve el RTT. El delta de `crawler-systemd-units` de este cambio **reemplaza** los requisitos que `fix-tcpdump-revival` introdujo (ya no hay "pcap capture service" que orquestar). Por eso `fix-tcpdump-revival` debe archivarse antes de archivar este.

## Risks / Trade-offs

- [El emparejamiento ping/pong en `ping.py` mide algo distinto a lo que medía cache_inv] → cache_inv medía el `pong` observado en el cable; `ping.py` mide el round-trip del nonce que él mismo envió. Es **más correcto** como "RTT" (es literalmente un round-trip), pero los números pueden no ser idénticos a los históricos. Aceptable — y se documenta. El caveat "RTT desde Virginia" sigue aplicando igual.
- [Trabajo en el fork, con cuidado] → El follow-up ya lo marcaba "medium effort, careful time on the fork". `ping.py` es código del crawler upstream con su propio estilo gevent; el cambio debe respetarlo.
- [Pérdida de la capacidad de medir propagación de `inv`] → Renuncia explícita y consciente; nadie la consume hoy.
- [Pcaps acumulados en disco tras el borrado] → `data/pcap/f9beb4d9/` queda con ~250 MB de pcaps muertos. La tarea de despliegue incluye limpiarlo a mano una vez.
- [Orden cross-repo mal ejecutado deja `rtt:*` sin productor] → Mitigado por la Decisión 3 (fork primero, verificar, luego alt-bitnodes).

## Migration Plan

1. **Fork** `ifuensan/bitnodes`, rama dedicada:
   - `ping.py`: registrar RTT en `rtt:<addr>-<port>` al emparejar pong.
   - `run-bitnodes.sh`: quitar las 3 líneas de `cache_inv`.
   - Borrar `cache_inv.py`, `pcap.py`, `start_pcap.sh`, `conf/cache_inv.*`.
   - Desplegar el fork; confirmar en Redis que `rtt:*` se puebla desde `ping.py`.
2. **alt-bitnodes**:
   - Borrar `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service`, `deploy/pcap-cleanup.timer`.
   - `deploy/install.sh`: quitar la instalación de esas units y todo el bloque de saneamiento tcpdump.
   - Actualizar `deploy/README.md`, `deploy/TUNING.md`; cerrar el item de `docs/follow-ups.md`.
   - Commit + push; el workflow corre `install.sh` sin nada de pcap.
3. Limpiar `~/bitnodes/data/pcap/` en el EC2 una vez.
4. Verificar: `latency_ms` no-null en `/api/v1/snapshots/latest/`, leaderboard con filas, snapshots estables ~4000+, `journalctl` sin `tcpdump-pcap`.

**Rollback**: revertir ambos repos. El pipeline pcap vuelve. Más costoso que un rollback normal por ser cross-repo y por borrados — conviene tag/branch antes.

## Open Questions

- ¿`rtt_count` y `ttl`: se portan literalmente de `conf/cache_inv.*.conf` o se redefinen en la config de `ping.py`? Propuesto: portar los valores actuales para no cambiar la ventana de datos del dashboard.
- ¿El emparejamiento ping/pong en `ping.py` ya guarda el timestamp de envío del `ping`, o hay que añadirlo? A confirmar al abrir `ping.py` en el fork — afecta el tamaño real del cambio.
- ¿Se borra también `pcap-cleanup.*` o se deja? Propuesto: borrar — es parte del pipeline pcap, sin pcaps no tiene función.
