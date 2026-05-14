## 1. Refactor capa de datos

- [x] 1.1 Crear paquete `queries/` con funciones puras (sin FastAPI): `list_snapshots`, `load_snapshot`, `snapshot_meta`, `snapshot_stats`, `node_status`, `parse_node_id`, `opendata_index`, `leaderboard`, `rankings_by_*`, `groups_by_ip`, `samples_for`, `median_rtt_for`, `medians_in_window`, `ingest_once`, `retention_pass` (`data/` no se puede usar, ya es runtime gitignored)
- [x] 1.2 Migrar `app.py` para que sus endpoints v1 deleguen en `queries/` (firmas y payloads idénticos, 22 rutas verificadas tras el refactor)
- [x] 1.3 Tests mínimos de `queries/` → diferido a `docs/follow-ups.md` ("Unit tests for the `queries/` data layer"): el repo no tiene infra de tests aún; se planifica como cambio aparte
- [x] 1.4 Smoke-test local: `curl` a endpoints v1 (snapshots, snapshots/latest, snapshots/{ts}, nodes/{id}, nodes/leaderboard, rankings/countries, groups/by-ip) → todos 200 / 400 / 404 esperados. **Bonus**: descubierto y corregido bug de orden de rutas pre-existente (`/nodes/leaderboard/` swalloweado por `/nodes/{node_id}/`)

## 2. Dependencias y empaquetado

- [x] 2.1 `mcp==1.27.1` añadido a `requirements.txt`. Bumpeado `fastapi` 0.115.0 → 0.136.1 para resolver conflicto con `starlette==1.0.0` que arrastra el SDK MCP
- [x] 2.2 Paquete `alt_bitnodes_mcp/` creado con `__init__.py`, `__main__.py`, `server.py`, `tools.py`, `resources.py`, `prompts.py`
- [x] 2.3 CLI con `--stdio` y `--http --host --port`, log-level configurable

## 3. Servidor MCP — tools

- [x] 3.1 `FastMCP("alt-bitnodes")` instanciado en `server.py` con registro modular
- [x] 3.2 Tools de snapshot: `get_latest_snapshot`, `get_snapshot_by_timestamp`, `list_snapshots`
- [x] 3.3 Tools de nodo: `get_leaderboard`, `get_node_rtt`, `get_node_details`
- [x] 3.4 Tools de búsqueda/charts: `search_nodes`, `get_chart_data` (+ extras `get_ip_groups`, `get_ip_group_detail`, `get_rankings`, `parse_node_id_str` — 12 tools en total)
- [x] 3.5 Inputs validados con `Literal[...]` y rangos; errores devueltos como dict `{"error": "..."}`

## 4. Servidor MCP — resources y prompts

- [x] 4.1 Resources `bitcoin://snapshot/latest` y template `bitcoin://snapshot/{timestamp}`
- [x] 4.2 Resources `bitcoin://leaderboard/latency` y `bitcoin://leaderboard/uptime`
- [x] 4.3 Prompt `analyze-network-health` con datos embebidos (stats + top-10 latencia)
- [x] 4.4 Prompts `compare-snapshots`, `latency-report`, `network-distribution-summary`

## 5. Autenticación HTTP

- [x] 5.1 `alt_bitnodes_mcp/auth.py::load_token()` lee el token de `MCP_TOKEN_PATH` (default `/etc/alt-bitnodes/mcp-token`) al arrancar
- [x] 5.2 `BearerAuthMiddleware` rechaza con 401 sin/bad token; comparación constant-time vía `hmac.compare_digest`. `--no-auth` permite saltarse en local (bloqueado si `MCP_REQUIRE_AUTH=1`). Verificado E2E con `initialize` MCP
- [x] 5.3 Modo stdio no monta middleware (auth solo se aplica en la rama HTTP)

## 6. Despliegue — install.sh y systemd

- [x] 6.1 `bootstrap_mcp_token()` genera `/etc/alt-bitnodes/mcp-token` (32 bytes urandom base64url, sin newline) si no existe; chown root:`${INSTALL_USER}`, chmod 0640 (legible por la unit, no por otros usuarios)
- [x] 6.2 `deploy/alt-bitnodes-mcp.service` creado con ExecStart `python -m alt_bitnodes_mcp --http --host 127.0.0.1 --port 8001`, `MCP_TOKEN_PATH`, `MCP_REQUIRE_AUTH=1`, hardening (NoNewPrivileges, ProtectSystem, etc.)
- [x] 6.3 `install_systemd_units` instala la unit, aplica sed de placeholders, daemon-reload, enable + restart `alt-bitnodes-mcp.service` junto al resto
- [x] 6.4 Idempotente: el token solo se genera si `! -f` (re-runs lo respetan); systemctl enable/restart son seguros en re-runs

## 7. Edge — nginx y CloudFront

- [x] 7.1 `location /mcp/` en `deploy/nginx/alt-bitnodes.conf.template`: `proxy_pass http://127.0.0.1:8001/mcp/`, `proxy_buffering off`, `proxy_read_timeout 1h`, `proxy_send_timeout 1h`, `Connection ""` (HTTP/1.1 keep-alive para SSE), gate `X-Origin-Auth` heredado del bloque `server`, `limit_req zone=api burst=20`
- [x] 7.2 `/mcp/*` cache behavior en `deploy/cloudformation/edge.yaml`: managed `CachingDisabled`, métodos completos `[GET,HEAD,OPTIONS,PUT,POST,PATCH,DELETE]`, managed `AllViewerExceptHostHeader` (forwardea Authorization), `Compress: false`
- [x] 7.3 CloudFormation update via change-set `add-mcp-behavior-...` → único cambio `Modify Distribution → DistributionConfig`. `UPDATE_COMPLETE` en ~10 min
- [x] 7.4 Invalidación CloudFront no necesaria: el cache behavior `/mcp/*` lleva `CachingDisabled` desde el día 1, no había nada para invalidar

## 8. Documentación

- [x] 8.1 Sección "MCP service" en `deploy/README.md` con inventario (12 tools / 4 resources / 4 prompts), `claude mcp add --transport http ...` (HTTP) y JSON Claude Desktop (stdio)
- [x] 8.2 "Rotating the bearer token": `sudo rm /etc/alt-bitnodes/mcp-token && bash install.sh`; cómo leerlo desde EC2 con `sudo cat`
- [x] 8.3 "Caveats": read-only, RTT desde Virginia, SSE 1h, un único token compartido

## 9. Validación end-to-end

- [x] 9.1 Smoke-test HTTP desde Claude Code: server registrado en `.claude.json`. Validado end-to-end por CloudFront — tools `get_latest_snapshot`, `list_snapshots`, `get_rankings` + resource `bitcoin://leaderboard/latency` devuelven datos reales
- [x] 9.2 MCP via CloudFront: `https://pesquisa.hacknodes.xyz/mcp/` con bearer válido → HTTP/2 200 con SSE `event: message data: {...protocolVersion, capabilities, serverInfo: alt-bitnodes 1.27.1}`
- [x] 9.3 Auth/edge:
  - 401 sin Authorization (CloudFront).
  - 401 bearer incorrecto (CloudFront, con `WWW-Authenticate: Bearer realm="alt-bitnodes-mcp"`).
  - 403 sin `X-Origin-Auth` desde dentro del EC2 (nginx).
  - Golpe directo a IP pública del origen desde fuera: bloqueado por la SG (CloudFront prefix-list); curl timeout, defensa primaria intacta.
- [x] 9.4 REST v1 intacta: `/api/v1/snapshots/latest/` 200, `/api/v1/nodes/leaderboard/?limit=3` 200, mismas firmas
- [x] 9.5 Prompt `analyze-network-health` ejecutado desde Claude Code (`/alt-bitnodes:analyze_network_health`) — el cliente expandió el prompt con snapshot + leaderboard reales embebidos
