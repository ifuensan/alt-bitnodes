## Context

Cadena de RTT actual en `alt-bitnodes` (verificada en código, 2026-05-14):

```
deploy/tcpdump-pcap.service ─▶ pcaps ─▶ cache_inv.py (fork) ─▶ rtt:* (Redis)
                                                                  │
  app.py _ingest_loop ──▶ queries/rtt.py ingest_once ──▶ data/rtt.sqlite
                                                                  │
  ┌───────────────────────────────────────────────────────────────┤
  ▼                          ▼                    ▼                ▼
queries/leaderboard.py    queries/nodes.py   queries/snapshots.py  queries/rtt.py
  leaderboard()             node_status        snapshot_stats        samples_for
  rankings_by_* (median)    (latency_ms)       (median_latency_ms)   (rtt series)
  group_by_ip_detail
  ▼                          ▼                    ▼                ▼
app.py /nodes/leaderboard/   /nodes/{id}/      /api/.../stats     /nodes/{id}/rtt/
MCP get_leaderboard          get_node_details  get_chart_data     get_node_rtt
MCP resources leaderboard/*  ─                 ─                  ─
frontend "Fastest nodes"     ─                 KPI median-latency ─
```

El hotfix `fix-tcpdump-revival` ya rompió `Wants=tcpdump-pcap.service` en `bitnodes.service`: el sniffer no revive y `rtt:*` no se puebla, así que **hoy `latency_ms` ya es `null` en producción**. Este cambio no altera comportamiento observable de runtime — solo borra el código muerto que sostenía esa funcionalidad.

Decisión de alcance (mesa redonda BMAD, 2026-05-14): **borrado total de RTT**, no solo del podio. El usuario confirmó que la vista de latencia no tiene uso real y que el dato solo aparecía en el top-20. Conservar `queries/rtt.py` "inerte" sería deuda muerta que arrastra un schema SQLite, un loop de ingesta y ramas de código en cinco módulos.

## Goals / Non-Goals

**Goals:**
- Eliminar el subsistema pcap del deploy de `alt-bitnodes` (4 units + lógica de `install.sh`).
- Eliminar toda la cadena de RTT/latencia del dashboard: capa de datos, API v1, MCP, frontend.
- Dejar el árbol de código sin referencias colgantes a RTT — sin imports muertos, sin campos `null` fantasma, sin endpoints vacíos.
- Cerrar los follow-ups de RTT.

**Non-Goals:**
- No tocar el fork `ifuensan/bitnodes` (ni `ping.py`, ni `cache_inv.py`, ni `run-bitnodes.sh`). Que `cache_inv` siga escribiendo `rtt:*` sin lectores es inocuo.
- No reconstruir RTT por ningún otro medio (active ping, multi-región, etc.). Si algún día se quiere, será un cambio propio con su diseño.
- No tocar `crawl.py`/`export.py`: la height de bloque del snapshot nunca dependió del pcap.
- No cambiar el resto de la API v1 ni del MCP (snapshots, addresses, rankings sin RTT, groups, search, charts).

## Decisions

### Decisión 1 — Borrado total, no desactivación

Se elimina `queries/rtt.py` entero y todas sus referencias, en vez de dejarlo "apagado por flag". Razón: un módulo inerte sigue siendo superficie de mantenimiento (schema SQLite, loop asyncio, imports) y un lector futuro no sabría si es código vivo. El `git revert` es el plan de recuperación si alguna vez hace falta.

**Alternativa considerada**: dejar la capa de datos y la API, borrar solo el frontend. Descartada en la mesa redonda — el usuario eligió explícitamente "borrado total".

### Decisión 2 — Los rankings sobreviven, sin la columna de RTT

`rankings_by_country/asn/user_agent` y `groups/by-ip` siguen siendo útiles (cuentan nodos por país/ASN/UA, agrupan IPs). Solo pierden el campo derivado del RTT (`median_rtt_ms`, `latency_ms`). `_group_ranking` se simplifica: ya no recibe `medians` ni calcula medianas.

### Decisión 3 — `snapshot_stats` pierde `median_latency_ms` y el parámetro `medians_now`

`snapshot_stats(timestamp, medians_now=...)` se vuelve `snapshot_stats(timestamp)`. Los tres llamadores (`app.py` x2, `tools.py get_chart_data`) se ajustan. El comentario que justificaba pasar `medians_now` desde fuera "para no crear dependencia cíclica con queries.rtt" deja de aplicar — `queries.rtt` ya no existe.

### Decisión 4 — Endpoints v1 eliminados, no deprecados

`/api/v1/nodes/leaderboard/` y `/api/v1/nodes/{node_id}/rtt/` se borran directamente. No hay consumidores externos conocidos (es un dashboard de uso personal) y un endpoint deprecado que devuelve 404 o vacío es peor que su ausencia. El comentario sobre el orden de registro de rutas (`/nodes/leaderboard/` antes que `/nodes/{node_id}/`) desaparece con el endpoint.

### Decisión 5 — Una sola fase, un solo repo

A diferencia de `active-ping-rtt` (que era cross-repo y necesitaba secuenciar fork → alt-bitnodes), esto es todo borrado dentro de `alt-bitnodes`. Un commit, un push, el workflow corre `install.sh`. La limpieza de `data/rtt.sqlite` y `data/pcap/` en el EC2 es un paso manual único post-deploy.

## Risks / Trade-offs

- [Referencia colgante tras el borrado] → El riesgo principal de un cambio de borrado: un import o llamada que se queda huérfano y rompe el arranque. Mitigación: tras editar, `python -c "import app"` y `python -c "import alt_bitnodes_mcp.server"` deben pasar; arrancar el server en local y comprobar `/` y `/docs`.
- [Pérdida de paridad bitnodes.io en `latency_ms`] → Renuncia explícita. La API v1 sigue siendo compatible en todo lo demás (snapshots, nodes, addresses, rankings, groups).
- [`cache_inv` sigue vivo en el fork escribiendo `rtt:*`] → Inocuo: claves Redis con TTL que nadie lee. No justifica tocar el fork.
- [Specs maestras que se eliminan] → `latency-api` y `rtt-history` se borran de `openspec/specs/` al sincronizar. Es correcto: las capabilities dejan de existir.

## Migration Plan

1. **Borrado del subsistema pcap**: eliminar las 4 units de `deploy/`, limpiar `install.sh`.
2. **Borrado de la capa de datos**: eliminar `queries/rtt.py`, ajustar `queries/leaderboard.py`, `nodes.py`, `snapshots.py`, `config.py`, `__init__.py`.
3. **Borrado en API/MCP/frontend**: ajustar `app.py`, `alt_bitnodes_mcp/{tools,resources,prompts}.py`, `templates/index.html`, `static/app.js`.
4. **Verificación local**: imports OK, server arranca, `/` y `/docs` OK, sin rutas de RTT en el OpenAPI.
5. **Docs**: `deploy/README.md`, `deploy/TUNING.md`, `docs/follow-ups.md`, `README.md`.
6. **Deploy**: commit + push; el workflow corre `install.sh` sin pcap.
7. **Limpieza en EC2** (una vez): borrar `data/rtt.sqlite` y `~/bitnodes/data/pcap/`.
8. **Verificación en producción**: `journalctl` sin `tcpdump-pcap`, sin proceso `tcpdump`; dashboard sin sección de latencia; `/api/v1/snapshots/latest/` y `/api/v1/rankings/*` responden 200 sin campos de RTT; snapshots estables.

**Rollback**: `git revert` del commit + redeploy. Restaura units, código y specs.

## Open Questions

Ninguna. El alcance quedó cerrado en la mesa redonda BMAD del 2026-05-14: borrado total de RTT, sin tocar el fork.
