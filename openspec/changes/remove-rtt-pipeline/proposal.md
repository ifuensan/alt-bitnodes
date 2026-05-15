## Why

El RTT por nodo nació de un pipeline de captura pasiva: `tcpdump-pcap.service` graba pcaps → `cache_inv.py` extrae los `pong` → escribe `rtt:*` en Redis → el dashboard lo ingiere a SQLite → lo sirven `latency-api`, `rankings-api`, el leaderboard del frontend y el MCP. Ese sniffer fue la causa raíz, confirmada en dos postmortems, de la oscilación de snapshots. El hotfix `fix-tcpdump-revival` cortó el revival del sniffer dejando el RTT a `null` — un parche que dejaba la pregunta abierta: ¿qué hacemos con el RTT?

La propuesta original (`active-ping-rtt`) era reconstruir la medición dentro del fork del crawler (`ping.py`). Una mesa redonda BMAD la descartó con un dato decisivo del propio usuario: **la vista de latencia la usa solo él, sin ninguna utilidad real, y el dato se consume únicamente en el podio "Fastest nodes"**. Reconstruir RTT en el fork significaría mantener un fork divergente (impuesto recurrente de rebase contra upstream) para alimentar una métrica de valor nulo — y que además, medida desde una única sonda en us-east-1, nunca midió "nodo rápido" sino "cercanía a Virginia".

Conclusión: no reconstruir, **eliminar**. Quitar el subsistema pcap *y* toda la cadena de RTT del dashboard. Menos código, menos servicios systemd, menos superficie de incidentes, y el fork `ifuensan/bitnodes` se queda sin tocar.

## What Changes

**Subsistema pcap (deploy):**
- Se eliminan `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service`, `deploy/pcap-cleanup.timer`.
- `deploy/install.sh` deja de instalar y de sanear esas units — todo el bloque tcpdump/pcap desaparece.

**Capa de datos del dashboard:**
- Se elimina `queries/rtt.py` entero (store SQLite + ingesta Redis).
- `queries/leaderboard.py`: se elimina `leaderboard()`; los `rankings_by_*` y `group_by_ip_detail` dejan de incluir RTT.
- `queries/nodes.py`, `queries/snapshots.py`, `queries/config.py`, `queries/__init__.py`: se quitan los campos y helpers de RTT.

**API v1 y app.py:**
- Se eliminan los endpoints `/api/v1/nodes/leaderboard/` y `/api/v1/nodes/{node_id}/rtt/`.
- Se elimina el loop de ingesta de RTT y su evento de arranque.
- `latency_ms` desaparece de los payloads de snapshot y de nodo; `median_latency_ms` de las stats; `median_rtt_ms` de los rankings.

**MCP:**
- Se eliminan las tools `get_leaderboard` y `get_node_rtt`, las resources `bitcoin://leaderboard/latency` y `bitcoin://leaderboard/uptime`, y el prompt `latency-report`. `get_rankings` y `analyze_network_health` dejan de incluir RTT.

**Frontend:**
- Se eliminan el KPI "Median latency" y la sección "Fastest nodes" con su tabla (`templates/index.html`, `static/app.js`).

**Docs:** `deploy/README.md`, `deploy/TUNING.md`, `docs/follow-ups.md`, `README.md`.

**BREAKING (API pública)**: `/api/v1/nodes/leaderboard/` y `/api/v1/nodes/{node_id}/rtt/` desaparecen; `latency_ms` deja de aparecer en los payloads v1 y `median_rtt_ms` en los rankings. La API v1 deja de tener paridad con bitnodes.io en el campo de latencia — renuncia explícita y consciente.

**Fuera de alcance**: el fork `ifuensan/bitnodes` no se toca. `cache_inv.py` seguirá corriendo allí escribiendo `rtt:*` a Redis, pero como nada lo lee es inocuo; limpiarlo del fork sería un cambio propio si algún día interesa.

## Capabilities

### Modified Capabilities
- `crawler-systemd-units`: el conjunto de units desplegadas deja de incluir `tcpdump-pcap.service` y `pcap-cleanup.*`; `install.sh` deja de instalarlas o sanearlas. Reemplaza los requisitos de "pcap capture is never a side effect" / "disabling survives deploys" que introdujo `fix-tcpdump-revival` por "el despliegue no incluye ningún componente de captura pcap".
- `rankings-api`: los rankings por país/ASN/user-agent dejan de incluir `median_rtt_ms`; el detalle por IP deja de incluir `latency_ms`; se elimina el requisito del leaderboard de nodos más rápidos.
- `mcp-service`: el servidor MCP deja de exponer tools/resources/prompts de RTT y latencia.

### Removed Capabilities
- `latency-api`: se elimina por completo — sin store de RTT no hay `latency_ms` en payloads ni endpoint de serie temporal.
- `rtt-history`: se elimina por completo — sin productor de `rtt:*` consumido no hay nada que ingerir ni persistir.

## Impact

- **Repo `alt-bitnodes`**: borrado de 4 ficheros en `deploy/`, limpieza de `deploy/install.sh`; borrado de `queries/rtt.py`; ediciones en `queries/leaderboard.py`, `queries/nodes.py`, `queries/snapshots.py`, `queries/config.py`, `queries/__init__.py`, `app.py`, `alt_bitnodes_mcp/{tools,resources,prompts}.py`, `templates/index.html`, `static/app.js`; docs.
- **Sin cambios en**: el crawler / fork `ifuensan/bitnodes`, `crawl.py`/`export.py` (la height del snapshot nunca dependió del pcap), el resto de la API v1 y del MCP.
- **Dependencia de orden**: este cambio modifica la capability `crawler-systemd-units` que introdujo `fix-tcpdump-revival`. `fix-tcpdump-revival` ya está archivado, así que la dependencia está satisfecha.
- **Despliegue**: un solo repo, una sola fase. Commit + push → el workflow corre `install.sh` sin nada de pcap. Limpiar `data/rtt.sqlite` y `data/pcap/` en el EC2 una vez.
- **Rollback**: `git revert` del commit. Reversible y barato — todo el borrado vive en un commit.
