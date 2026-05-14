## Why

El dashboard `alt-bitnodes` expone una API REST (v1) con datos de la red Bitcoin (snapshots, leaderboard, RTT, charts) que hoy solo consumen el frontend web y clientes HTTP convencionales. Convertir la API también en un servicio MCP permite que asistentes LLM (Claude Desktop, Claude Code, otros clientes MCP) consulten directamente el estado de la red, recuperen snapshots y ejecuten flujos de análisis sin escribir código intermedio. Es la palanca natural para pasar de "dashboard humano" a "fuente de datos consultable por agentes".

## What Changes

- Añadir un servidor MCP que expone los endpoints de `app.py` (v1) como **tools**, los snapshots y leaderboard como **resources**, y plantillas de análisis (`analyze-network-health`, `compare-snapshots`, etc.) como **prompts**.
- Soportar **dos transportes**: `stdio` (para Claude Desktop / clientes locales) y **Streamable HTTP** (para acceso remoto autenticado a través de CloudFront en `pesquisa.hacknodes.xyz`).
- Empaquetar el servidor MCP como un nuevo entrypoint Python independiente (`mcp_server.py` o módulo bajo `mcp/`) reutilizando la capa de datos de `app.py` (Redis, mismos parsers) sin duplicar lógica.
- Persistir despliegue en `deploy/install.sh` + nueva unit systemd `alt-bitnodes-mcp.service` (modo HTTP). Exponer el endpoint MCP HTTP detrás de nginx con un path dedicado (p. ej. `/mcp/`) y la misma defensa `X-Origin-Auth` que ya usa el origen.
- Añadir autenticación bearer en el transporte HTTP (token-based, persistido como secret en el host) — el stdio no la necesita por contexto local.
- Documentar uso desde Claude Desktop (config JSON de cliente) y desde Claude Code (mcp add) en `deploy/README.md`.
- **NO BREAKING**: la API REST v1 sigue intacta — MCP es una superficie adicional.

## Capabilities

### New Capabilities
- `mcp-service`: Servidor MCP que expone los datos de la red Bitcoin de alt-bitnodes como tools / resources / prompts, con transporte stdio y Streamable HTTP, reutilizando la capa de datos de la API REST v1.

### Modified Capabilities
<!-- Ninguna. Los specs existentes (latency-api, rankings-api, public-edge, rtt-history, dashboard-bar-charts) describen la API REST y el edge; el MCP es una superficie nueva paralela. Si en el futuro el MCP cambia algún requisito de public-edge (p. ej. nuevo path detrás de CloudFront) se añadirá un delta en ese momento. -->

## Impact

- **Código nuevo**: módulo `mcp/` (o `mcp_server.py`) con definiciones de tools/resources/prompts; reutiliza helpers existentes de `app.py`.
- **Dependencias**: añadir `mcp` (Python SDK oficial de Model Context Protocol) a `requirements.txt`.
- **Procesos**: nueva systemd unit `alt-bitnodes-mcp.service` (modo HTTP en localhost, p. ej. `127.0.0.1:8001`).
- **nginx**: nueva `location /mcp/` con proxy al puerto local del MCP server, validando `X-Origin-Auth` (ya existente) y exigiendo cabecera `Authorization: Bearer <token>` para el lado MCP.
- **CloudFront**: nuevo cache behavior para `/mcp/*` con cache OFF, métodos `POST` + `GET` (SSE), forwardeando `Authorization`. El secret `X-Origin-Auth` ya se inyecta a nivel de distribución.
- **Despliegue**: `deploy/install.sh` instala la nueva unit, genera el bearer token MCP si no existe, lo guarda en `/etc/alt-bitnodes/mcp-token` con permisos 0600.
- **Documentación**: `deploy/README.md` añade sección "Conectarse al MCP" con ejemplos de `claude mcp add` y JSON de Claude Desktop.
- **Sin impacto en**: API REST v1, frontend web, crawler/bitnodes, RTT pipeline, snapshots.
