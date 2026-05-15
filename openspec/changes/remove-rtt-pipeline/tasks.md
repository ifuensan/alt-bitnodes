## 1. Borrar el subsistema pcap del deploy

- [x] 1.1 Borrar `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service`, `deploy/pcap-cleanup.timer`
- [x] 1.2 `deploy/install.sh`: quitar la instalación de esas units (`install -m ... pcap/tcpdump ...`), el sed de placeholders sobre ellas y todo el bloque de saneamiento `stop`/`disable`/`pkill` de tcpdump (también quitado el paquete `tcpdump` de `apt-get install`, y el comentario de `bitnodes.service` que aún hablaba de `tcpdump-pcap.service`)
- [x] 1.3 Confirmar con `grep -ri 'tcpdump\|pcap' deploy/` que `install.sh` y el resto de `deploy/` ya no referencian el pipeline (solo quedan refs en `README.md` y `TUNING.md`, cubiertas en §7)

## 2. Borrar la capa de datos de RTT

- [x] 2.1 Borrar `queries/rtt.py`
- [x] 2.2 `queries/config.py`: quitar `RTT_DB_PATH`, `RTT_WINDOW_SECONDS`, `RTT_RETENTION_DAYS`
- [x] 2.3 `queries/__init__.py`: quitar los imports/exports de `queries.rtt` (`rtt_db`, `samples_for`, `median_rtt_for`, `medians_in_window`, `ingest_once`, `retention_pass`) y los de config de RTT
- [x] 2.4 `queries/leaderboard.py`: eliminar `leaderboard()`; en `_group_ranking` y `rankings_by_*` quitar `medians`/`median_rtt_ms`; en `group_by_ip_detail` quitar `latency_ms`; quitar el import de `medians_in_window`
- [x] 2.5 `queries/nodes.py`: quitar el import de `median_rtt_for` y el campo de RTT de los arrays `data` de `node_status`
- [x] 2.6 `queries/snapshots.py`: `snapshot_stats` pierde el parámetro `medians_now` y la clave `median_latency_ms`

## 3. Borrar RTT de la API v1 (app.py)

- [x] 3.1 Quitar el loop de ingesta: `_ingest_loop`, `_ingest_state`, `_start_rtt_ingest`, `_rtt_ingest_task`, las constantes `RTT_INGEST_*`
- [x] 3.2 Eliminar los endpoints `/api/v1/nodes/leaderboard/` (`v1_leaderboard`) y `/api/v1/nodes/{node_id}/rtt/` (`v1_node_rtt`), con su comentario de orden de rutas
- [x] 3.3 `_v1_snapshot_payload`: quitar `medians` y el elemento `medians.get(...)` del array de cada nodo
- [x] 3.4 `snapshot_stats_endpoint` / `latest_stats`: dejar de calcular y pasar `medians_now`
- [x] 3.5 Limpiar el bloque de imports de `queries` (quitar `ingest_once`, `leaderboard`, `median_rtt_for`, `medians_in_window`, `retention_pass`, `rtt_db`, `samples_for`) y la línea `from queries.rtt import has_samples`

## 4. Borrar RTT del MCP

- [x] 4.1 `alt_bitnodes_mcp/tools.py`: eliminar las tools `get_leaderboard` y `get_node_rtt`; en `_snapshot_payload` quitar `medians`; en `get_chart_data` dejar de pasar `medians_now`; limpiar imports (`leaderboard`, `medians_in_window`, `samples_for`, `has_samples`)
- [x] 4.2 `alt_bitnodes_mcp/resources.py`: eliminar las resources `bitcoin://leaderboard/latency` y `bitcoin://leaderboard/uptime`; limpiar el import de `leaderboard`
- [x] 4.3 `alt_bitnodes_mcp/prompts.py`: eliminar el prompt `latency_report`; en `analyze_network_health` quitar `top_10_by_latency` y el caveat de Virginia; limpiar el import de `leaderboard`

## 5. Borrar RTT del frontend

- [x] 5.1 `templates/index.html`: quitar el KPI `kpi-latency` ("Median latency") y toda la sección `<h2>Fastest nodes</h2>` con su tabla `#leaderboard-table`
- [x] 5.2 `static/app.js`: eliminar `loadLeaderboard()` y su llamada, y la línea que escribe `kpi-latency`

## 6. Verificación local

- [x] 6.1 `python -c "import app"` y `python -c "import alt_bitnodes_mcp.server"` sin errores
- [x] 6.2 Arrancar el server en local: `/` → 200, `/docs` → 200, `/openapi.json` con 16 paths y **0** que contengan `rtt` o `leaderboard`. `/api/v1/nodes/leaderboard/` → 400 (cae en `/nodes/{node_id}/` y falla por id inválido — la ruta dedicada ya no existe)
- [x] 6.3 `grep -ri 'rtt\|latency\|leaderboard'` — solo `from queries.leaderboard import …` en `queries/__init__.py` (el módulo cambió de propósito pero conservamos el nombre del fichero por disciplina de cambio mínimo)

## 7. Documentación

- [x] 7.1 `deploy/README.md`: borrada la sección entera "RTT history & latency endpoints"; sustituida por un mini smoke test de la API; lista de tools/resources/prompts del MCP actualizada (10/2/3); eliminada la env var `RTT_DB_PATH` del ejemplo de Claude Desktop; eliminado el caveat "RTT is Virginia-anchored"
- [x] 7.2 `deploy/TUNING.md`: la "Cause 2 — tcpdump-pcap.service" sustituida por nota histórica que apunta a `remove-rtt-pipeline`; corregido el texto de `ping.workers` ("medir RTT" → "probar liveness")
- [x] 7.3 `docs/follow-ups.md`: eliminadas las secciones "Replace pcap-based RTT with active pings" y "Multi-location RTT probes"; ajustada la idea de tests para no mencionar RTT
- [x] 7.4 `README.md` (bilingüe): reescrito por completo — diagrama sin tcpdump/cache_inv/pcap/rtt.sqlite, tabla de almacenes solo con Redis + export JSON, lista de endpoints sin leaderboard/rtt/latency_ms, sección de especificaciones sin `rtt-history` ni `latency-api`

## 8. Despliegue y verificación en producción

- [ ] 8.1 Commit + push (el workflow corre `install.sh` sin nada de pcap)
- [ ] 8.2 Limpiar en el EC2 (una vez): `data/rtt.sqlite` y `~/bitnodes/data/pcap/`
- [ ] 8.3 Verificar: `journalctl` sin `tcpdump-pcap`, sin proceso `tcpdump`, `systemctl status tcpdump-pcap` → not-found
- [ ] 8.4 Verificar: el dashboard carga sin KPI de latencia ni sección "Fastest nodes"
- [ ] 8.5 Verificar: `/api/v1/snapshots/latest/` y `/api/v1/rankings/*` responden 200 sin campos de RTT; `/api/v1/nodes/leaderboard/` y `/api/v1/nodes/{id}/rtt/` responden 404
- [ ] 8.6 Verificar: snapshots estables ~4000+ sin oscilación durante ≥30 min
