## Why

El RTT por nodo del dashboard depende hoy de un pipeline de captura pasiva: `tcpdump-pcap.service` graba pcaps → `cache_inv.py` los lee y extrae los `pong` → escribe `rtt:*` en Redis → el dashboard lo ingiere a SQLite. Ese sniffer es la causa raíz, confirmada en dos postmortems, de la oscilación de snapshots (la contención de I/O corta los handshakes del crawler). El cambio `fix-tcpdump-revival` corta el revival del sniffer, pero a costa de dejar el RTT a `null` — un parche, no una solución.

Investigando el crawler (`ifuensan/bitnodes`) se confirmó que `cache_inv` procesa los pcaps para extraer **dos** cosas: `pong` (→ `rtt:*`, que el dashboard sí usa) e `inv` (→ `inv:*`, propagación de bloques/tx, que **alt-bitnodes no expone en ningún endpoint**). Y la altura de bloque por nodo del snapshot no viene de aquí en absoluto — la escribe `crawl.py` del handshake `version`. Es decir: el único valor que el pipeline pcap aporta a alt-bitnodes es el RTT, y `ping.py` ya manda pings/pongs activamente — solo le falta registrar el RTT cuando llega el `pong`.

Sustituir la captura pasiva por registro activo en `ping.py` elimina el sniffer de la ecuación: snapshots estables **y** RTT, sin tcpdump. Y deja sin propósito todo el pipeline pcap, que se puede borrar — una simplificación grande y limpia, en la línea del "decompose the monolith" de la research de I2P.

## What Changes

**En el fork del crawler (`ifuensan/bitnodes`):**
- `ping.py` registra el RTT directamente: cuando llega el `pong` que casa con un `ping` enviado, calcula el RTT y escribe a `rtt:<addr>-<port>` en Redis (mismo formato de lista que `cache_inv` producía, con el mismo `ttl`/`rtt_count`), de modo que el dashboard no nota el cambio de productor.
- Se retira `cache_inv` de `run-bitnodes.sh` (las 3 instancias) y se eliminan del repo `cache_inv.py`, `pcap.py`, `start_pcap.sh` — sin productor de pcaps, no tienen función.

**En `alt-bitnodes`:**
- Se eliminan `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service` y `deploy/pcap-cleanup.timer`.
- `deploy/install.sh` deja de instalar y de sanear esas units (todo el bloque tcpdump/pcap desaparece).
- **BREAKING (operacional, no de API)**: alt-bitnodes deja de poder medir propagación de `inv`/bloques. Hoy no expone esa métrica en ningún endpoint, así que no hay impacto en consumidores — pero es una renuncia explícita: si en el futuro se quiere propagación de bloques (como bitnodes.io), habría que reintroducir un mecanismo.

## Capabilities

### New Capabilities
- `rtt-collection`: cómo se obtienen las muestras de RTT por nodo — registro activo en `ping.py` a partir del ciclo `ping`/`pong` del propio crawler, escritas a `rtt:*` en Redis, sin ningún componente de captura de red pasiva (tcpdump/pcap/cache_inv).

### Modified Capabilities
- `crawler-systemd-units`: el conjunto de units desplegadas deja de incluir `tcpdump-pcap.service` (y `pcap-cleanup`). El requisito introducido por `fix-tcpdump-revival` ("pcap capture is never a side effect... remains manually startable") se reemplaza por "el despliegue no incluye servicio de captura pcap".

## Impact

- **Repo `ifuensan/bitnodes`**: `ping.py` (lógica de registro de RTT), `run-bitnodes.sh` (quita las 3 líneas de `cache_inv`), borrado de `cache_inv.py` / `pcap.py` / `start_pcap.sh`, y posiblemente `conf/cache_inv.*.conf`. Estimación previa (follow-ups): "medium effort, requires careful time on the fork".
- **Repo `alt-bitnodes`**: borrado de `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service`, `deploy/pcap-cleanup.timer`; limpieza de `deploy/install.sh` (sección de units pcap y saneamiento tcpdump); ajustes de doc en `deploy/README.md`, `deploy/TUNING.md` y `docs/follow-ups.md` (cerrar el item "Replace pcap-based RTT with active pings").
- **Sin cambios en**: el contrato de `rtt:*` en Redis (mismo formato), `rtt-history` (la ingesta del dashboard es agnóstica al productor), `latency-api` (los endpoints siguen igual), el dashboard, el MCP server.
- **Dependencia de orden**: este cambio modifica una capability (`crawler-systemd-units`) introducida por `fix-tcpdump-revival`. `fix-tcpdump-revival` debe archivarse antes.
- **Despliegue**: cross-repo. Primero el fork (`ping.py` escribiendo `rtt:*`, retirada de `cache_inv`), confirmar que `rtt:*` se puebla; luego `alt-bitnodes` (borrado de units + `install.sh`). Verificar que `latency_ms` y el leaderboard vuelven a tener datos y que los snapshots siguen estables.
