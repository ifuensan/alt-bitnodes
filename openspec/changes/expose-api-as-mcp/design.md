## Context

`alt-bitnodes` ya expone una API REST v1 (FastAPI / uvicorn en `127.0.0.1:8000`) detrás de nginx → CloudFront en `pesquisa.hacknodes.xyz`. La capa de datos se apoya en Redis (snapshots, leaderboard, RTT) y en helpers ya implementados en `app.py`. Queremos añadir una superficie MCP sin duplicar lógica de dominio ni tocar la API REST existente.

Restricciones:
- Una única EC2 (c7g.2xlarge) corre crawler + dashboard + nginx + Tor. El MCP debe ser otro proceso ligero en el mismo host, no una nueva instancia.
- El despliegue es por `git push → workflow → install.sh` (idempotente). Cualquier pieza nueva debe encajar en ese mecanismo.
- El edge ya impone `X-Origin-Auth` entre CloudFront y nginx. Eso protege contra acceso directo a la IP, pero NO autoriza al usuario MCP — necesitamos auth de aplicación encima.
- Python SDK oficial de MCP (`mcp`) soporta stdio y Streamable HTTP en el mismo paquete; FastMCP es la API ergonómica recomendada.

## Goals / Non-Goals

**Goals:**
- Exponer **tools** que envuelvan los endpoints v1 (`/api/v1/snapshot/`, `/nodes/leaderboard/`, `/nodes/{addr}/rtt/`, charts, latency).
- Exponer **resources** para snapshots (último + por timestamp) y leaderboard como recursos navegables.
- Exponer **prompts** preconstruidos para análisis típicos: salud de la red, comparación de snapshots, top latencias, distribución por país/ASN.
- Soportar `stdio` (uso local con Claude Desktop) y `Streamable HTTP` (uso remoto autenticado).
- Reutilizar la capa de datos de `app.py` (mismas funciones que tocan Redis) sin replicarlas.
- Despliegue automatizable (`install.sh` + systemd) e instrucciones de cliente claras en `deploy/README.md`.

**Non-Goals:**
- No reescribir la API REST ni romper rutas existentes.
- No introducir base de datos nueva — Redis sigue siendo la fuente.
- No multi-tenant: un único token bearer compartido para el transporte HTTP (es un dashboard de investigación, no SaaS).
- No exponer escrituras (todo es read-only sobre datos de la red). Sin "tools" que muten estado.
- No federar MCP servers ni componer con otros — alt-bitnodes es origen único.

## Decisions

### Decisión 1 — SDK: `mcp` (Python oficial) con FastMCP

Usar el paquete `mcp` (`pip install mcp`) con la API `FastMCP`. Decoradores `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` mapean directamente a las tres primitivas. La misma instancia se puede arrancar con `.run(transport="stdio")` o `.streamable_http_app()` (ASGI) para HTTP.

**Alternativas consideradas:**
- Implementar el protocolo MCP a mano sobre JSON-RPC: descartado, mantenimiento alto y sin valor adicional.
- `fastmcp` standalone (Anthropic-independent): innecesario, el SDK oficial ya lo incluye.

### Decisión 2 — Reutilizar `app.py` extrayendo un módulo `data/` compartido

Crear `data/queries.py` (o similar) con funciones puras que devuelven dicts/listas (`get_latest_snapshot()`, `get_leaderboard(limit)`, `get_node_rtt(addr, port, hours)`, etc.). Refactor mínimo: `app.py` y `mcp_server.py` importan de ahí. Evita acoplar el MCP a `FastAPI` y permite testear sin levantar HTTP.

**Alternativa**: que el MCP haga HTTP interno (`requests.get("http://127.0.0.1:8000/api/v1/...")`). Descartado: doble salto, latencia innecesaria, acopla al esquema de URL.

### Decisión 3 — Dos procesos systemd, no uno multi-modo

- `alt-bitnodes.service` — uvicorn (REST), sin cambios.
- `alt-bitnodes-mcp.service` — `python -m alt_bitnodes_mcp --http --host 127.0.0.1 --port 8001`.
- `stdio` no necesita systemd: lo arranca el cliente (Claude Desktop ejecuta el binario).

**Alternativa**: un único proceso uvicorn que monte la app MCP en `/mcp`. Descartado: mezcla ciclos de vida y dependencias, complica reinicios independientes y oculta errores cruzados.

### Decisión 4 — Transporte HTTP: Streamable HTTP en `/mcp/`, bearer + `X-Origin-Auth`

Configurar nginx con:

```
location /mcp/ {
    if ($http_x_origin_auth != "<secret>") { return 403; }
    proxy_pass http://127.0.0.1:8001/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;             # SSE streaming
    proxy_read_timeout 1h;
}
```

El servidor MCP valida `Authorization: Bearer <mcp-token>` antes de procesar la sesión. Token generado en `install.sh` la primera vez, guardado en `/etc/alt-bitnodes/mcp-token` (0600 root) y leído al arrancar.

CloudFront añade un cache behavior `/mcp/*` con cache **OFF**, métodos `GET, POST, OPTIONS, DELETE`, forward de `Authorization` y `Content-Type`.

**Alternativa**: OAuth/DCR per-cliente. Descartado por ahora — añade complejidad sin beneficio para un proyecto de investigación de un solo usuario. Documentado como follow-up en la propia tarea.

### Decisión 5 — Catálogo inicial de tools / resources / prompts

**Tools (read-only):**
- `get_latest_snapshot()` → metadata + count.
- `get_snapshot_by_timestamp(ts)` → snapshot concreto.
- `list_snapshots(limit=20)` → lista los más recientes.
- `get_leaderboard(limit=50, by="latency"|"uptime")`.
- `get_node_rtt(address, port, hours=24)`.
- `get_node_details(address, port)` → versión, services, country, ASN, last seen.
- `search_nodes(country=None, asn=None, version=None, network="ipv4"|"ipv6"|"onion"|"i2p")`.
- `get_chart_data(chart="reachable"|"by_country"|"by_version", window="24h"|"7d"|"30d")`.

**Resources:**
- `bitcoin://snapshot/latest` (JSON).
- `bitcoin://snapshot/{timestamp}` (JSON).
- `bitcoin://leaderboard/latency` (JSON, top 100).
- `bitcoin://leaderboard/uptime` (JSON, top 100).

**Prompts:**
- `analyze-network-health` — recoge último snapshot + leaderboard y pide análisis estructurado.
- `compare-snapshots(t1, t2)` — diff de count / distribución / nuevos / desaparecidos.
- `latency-report(country?)` — top latencias y outliers (con caveat de que la medida es desde Virginia).
- `network-distribution-summary` — % por país, ASN, versión, red (ipv4/ipv6/onion/i2p).

### Decisión 6 — Empaquetado: nuevo paquete `alt_bitnodes_mcp/`

Estructura propuesta:

```
alt_bitnodes_mcp/
  __init__.py
  __main__.py            # entrypoint CLI (--stdio | --http)
  server.py              # FastMCP instance + decoradores
  tools.py               # @mcp.tool wrappers que llaman a data/
  resources.py
  prompts.py
data/
  __init__.py
  queries.py             # funciones puras Redis → dict (compartidas con app.py)
```

`app.py` migra a importar de `data.queries` (refactor mínimo, sin cambiar la firma pública de los endpoints).

## Risks / Trade-offs

- [El bearer token compartido se filtra] → Rotación documentada (regenerar en `/etc/alt-bitnodes/mcp-token`, reiniciar servicio). En el futuro: OAuth si llega un segundo usuario.
- [Refactor `app.py` → `data.queries` rompe la API REST] → Cubrir con tests del happy path antes del refactor; despliegue gradual con feature-flag NO necesaria por el tamaño del cambio, pero sí smoke-test post-deploy del `/api/v1/snapshot/`.
- [SDK MCP joven, breaking changes] → Pinning estricto de versión en `requirements.txt`. Revisar release notes antes de cada bump.
- [SSE atravesando CloudFront] → Cache OFF + `proxy_buffering off` + read-timeout largo. Documentar que conexiones largas (>1h) se cortan; el cliente reconecta.
- [Tor saturándose si tools devuelven muchos nodos onion] → Las tools son consultas a Redis, no disparan crawl. No hay carga adicional sobre Tor.
- [Carga adicional sobre Redis] → MCP es read-only y los datos ya viven en Redis. Coste marginal. Si crece, añadir caché LRU local en `data/queries.py`.

## Migration Plan

1. Refactor `app.py` → `data/queries.py` con tests básicos.
2. Implementar `alt_bitnodes_mcp/` con tools/resources/prompts mínimos.
3. Soporte stdio funcionando localmente (`claude mcp add` desde el repo).
4. Añadir entrypoint HTTP + unit systemd, validar en EC2.
5. Configurar nginx `/mcp/` + cache behavior CloudFront + token generation en `install.sh`.
6. Documentar en `deploy/README.md` cómo conectarse (Claude Desktop JSON + `claude mcp add` HTTP).
7. Smoke-test desde Claude Desktop con stdio y desde Claude Code con HTTP.

**Rollback**: parar `alt-bitnodes-mcp.service` y eliminar `location /mcp/` de nginx. La API REST sigue intacta porque `data/queries.py` es código compartido pero el endpoint MCP es un proceso aparte.

## Open Questions

- ¿Path final del endpoint MCP: `/mcp/` o `/api/mcp/`? Propuesto `/mcp/` por claridad y por no implicar versión.
- ¿Exponer también prompts dinámicos (parametrizados con argumentos del usuario) o solo plantillas estáticas en v1? Propuesto: estáticos en v1, dinámicos en una iteración posterior.
- ¿Renderizado de resources: JSON crudo o también texto/Markdown legible? Propuesto: JSON crudo (los LLMs lo manejan bien); plantillas Markdown via prompts si hace falta.
