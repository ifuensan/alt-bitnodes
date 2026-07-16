# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**alt-bitnodes** — public dashboard + REST API + MCP server for the Bitcoin
P2P network, live at https://pesquisa.hacknodes.xyz. A revival of the defunct
bitnodes.io: the upstream crawler (`ifuensan/bitnodes` fork of
`ayeowch/bitnodes`, deployed separately on the same host) discovers reachable
nodes and writes JSON snapshots; this repo serves them.

## Architecture

Three consumers share one pure data layer:

- `queries/` — data layer. No FastAPI/HTTP coupling; returns plain
  dicts/lists and raises standard exceptions (`FileNotFoundError`,
  `ValueError`, `NoSnapshotsError`, `SnapshotMissingError`). HTTP translation
  happens in the callers. Reads two sources:
  - snapshot JSON files in `BITNODES_EXPORT_DIR` (rows of 15 fields, see
    `queries/config.py:FIELDS`)
  - Redis (`REDIS_URL`) for live node state (`opendata` zset, `height:*` keys)
- `app.py` — FastAPI app (port 8000 behind nginx + CloudFront). Legacy
  `/api/*` endpoints feed the dashboard frontend; `/api/v1/*` is the public,
  bitnodes.io-compatible surface (note trailing slashes on v1 routes).
- `alt_bitnodes_mcp/` — MCP server (port 8001, Streamable HTTP, bearer-token
  auth via `MCP_TOKEN_PATH`/`MCP_REQUIRE_AUTH`) exposing the same data as
  tools/resources/prompts.
- `templates/index.html` + `static/` — dashboard frontend (vanilla JS,
  Observable Plot, "OSINT terminal" design system — see
  `openspec/specs/dashboard-design-system/`).

Caching is deliberate and layered: `lru_cache` on snapshot loads, a TTL dict
cache on the Redis `opendata` index, and incremental accumulation in
`known_addresses_set()`. Tests must clear these between cases (see
`tests/conftest.py`).

## Commands

```bash
venv/bin/pip install -r requirements.txt -r requirements-dev.txt  # deps
venv/bin/uvicorn app:app --reload            # run API + dashboard locally
venv/bin/python -m alt_bitnodes_mcp --http   # run MCP server locally
venv/bin/pytest                              # run tests (tests/)
```

`BITNODES_EXPORT_DIR` must point at a directory of `<unix-ts>.json` snapshot
files (default in `queries/config.py` is a local dev path). Redis is optional
for local work — Redis-backed queries degrade to empty results.

## Deploy

Push to `main` → GitHub Actions (`.github/workflows/deploy.yml`) SSHes into
the EC2 host, hard-resets to origin/main, runs `sudo bash deploy/install.sh`,
then smoke-tests port 8000. Doc-only pushes (md, `openspec/`, `docs/`,
`_bmad*`, `.claude/`) skip deploy. `deploy/` holds the systemd units
(placeholders `__USER__`, `__DASHBOARD_DIR__`, `__EXPORT_DIR__` are
substituted by `install.sh`), nginx config, and CloudFormation for the
CloudFront edge. Ops incidents are written up in `docs/postmortems/`.

## Workflow conventions

- Changes go through **OpenSpec**: propose → implement → archive into
  `openspec/changes/archive/`, keeping `openspec/specs/` in sync. Small fixes
  can go direct, but anything touching behaviour/specs should follow the flow.
- `docs/follow-ups.md` is the backlog for non-blocking work.
- SonarQube analyses first-party sources only (`sonar-project.properties`).
- `_bmad/`, `_bmad-output/` are agent-tooling artefacts, not product code —
  don't count them as part of the app.
