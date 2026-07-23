# Tasks: expose-latent-crawler-data

## 1. Data layer — queries/

- [x] 1.1 `queries/services_breakdown.py`: named-flag constants, bitmask
      decoder, latest-snapshot breakdown (total + per network class,
      `other` bucket with raw masks), unit tests over synthetic rows
- [x] 1.2 `queries/unique_nodes.py`: peer-gossip network-class inference,
      1/N weighting, composition histogram, persistence helpers
      (write/load JSON), unit tests incl. missing/empty `peer:*` cases
- [x] 1.3 `queries/block_propagation.py`: binv zset reader, hot-block
      skip (30 min), per-class percentiles + ECDF computation, per-block
      JSON persistence with 30-day pruning, aggregate-over-recent-blocks
      reader, unit tests with a fake Redis zset fixture
- [x] 1.4 Daily services adoption series: archive sampler (1/day, 90-day
      backfill cap), series JSON write/load, tests for missing days

## 2. Collector — timer entrypoint

- [x] 2.1 Single collector entrypoint running the three sections
      (propagation, services series, unique estimate) with independent
      try/except per section and structured logging
- [x] 2.2 `deploy/`: `alt-bitnodes-collector.service` + `.timer`
      (10 min, niced), placeholder substitution in `install.sh`, wired
      into the deploy fingerprint
- [ ] 2.3 Verify on prod: JSON files appear, Redis load acceptable
      (read-only SCAN/ZRANGE), prune works

## 3. API — app.py

- [x] 3.1 Legacy endpoints `GET /api/propagation`, `GET /api/services`,
      `GET /api/unique-nodes` shaped for the charts; empty-state = 200
- [x] 3.2 v1 endpoints `GET /api/v1/stats/propagation/`,
      `GET /api/v1/stats/services/`, `GET /api/v1/stats/unique-nodes/`
      (trailing slashes, windowed-stats precedent); `method`/definition
      fields included
- [x] 3.3 Endpoint tests via fastapi.testclient with fixture JSON

## 4. Dashboard — templates/static

- [x] 4.1 Main page: three-band KPI matrix (now / 1/N estimate / window,
      aligned TOTAL-CLEARNET-TOR-I2P columns, em-dash empty state for
      band 2) replacing the current KPI tiles + windowed line
- [x] 4.2 Main page: compact services strip (BIP324 / compact filters /
      pruned percentages, numbers only) linking to /research
- [x] 4.3 `/research` page: route + template + header nav tabs on both
      pages (active state, design-system styling)
- [x] 4.4 Research page — propagation section: ECDF step-line chart
      (log x, per-class colors from tokens) + recent-blocks dense table +
      per-block drill-down + first-heard caption
- [x] 4.5 Research page — services section: per-flag adoption bars
      (grouped per-network variant) + daily small-multiple lines,
      tooltips with bit values
- [x] 4.6 Research page — unique-nodes section: stacked N-composition bar
      + 1/N method description (deep-link target from band 2)
- [ ] 4.7 Lazy, independent section rendering on /research; verify both
      themes on both pages; CloudFront invalidation incl. new route

## 5. MCP — alt_bitnodes_mcp

- [x] 5.1 Tools `get_block_propagation`, `get_services_breakdown`,
      `get_unique_nodes_estimate` wrapping the query functions;
      empty-state notes
- [x] 5.2 MCP tool tests mirroring the v1 endpoint fixtures

## 6. Close out

- [x] 6.1 Update README/API docs with the three new endpoints and
      definitions (first-heard propagation, 1/N method limitation)
- [ ] 6.2 Full test run + deploy + smoke-test endpoints on prod
- [ ] 6.3 Archive the change into `openspec/changes/archive/` and sync
      `openspec/specs/`

### Review Findings (bmad-code-review 2026-07-23)

- [x] [Review][Decision] Serie diaria: ¿muestrear del export dir (código actual) o del archivo GFS (letra del spec)?
- [x] [Review][Patch] Aislamiento por bloque en collect_propagation + excepciones de _height_estimate [queries/block_propagation.py:127]
- [x] [Review][Patch] Agregado como mediana real de ECDFs (no pooled sesgado) + label del eje y [queries/block_propagation.py:164, static/research.js]
- [x] [Review][Patch] Semántica BIP159: "PRUNED" = LIMITED sin NETWORK, métrica derivada [queries/services.py, static/app.js]
- [ ] [Review][Patch] Collector exit 1 cuando fallan las tres secciones [collector.py:49]
- [ ] [Review][Patch] TimeoutStartSec + Wants=network-online.target en la unit [deploy/alt-bitnodes-collector.service]
- [x] [Review][Patch] Robustez de parseo: JSONDecodeError en snapshot corrupto (×3 sitios), gossip JSON escalar, validación de shape en loaders y entries de serie [queries/services.py, queries/unique_nodes.py, queries/block_propagation.py]
- [ ] [Review][Patch] Podar .json.tmp huérfanos [queries/block_propagation.py:146]
- [ ] [Review][Patch] Normalizar hash a lowercase en load_block [queries/block_propagation.py:228]
- [ ] [Review][Patch] `other` siempre último en barras de adopción [static/research.js]
- [ ] [Review][Patch] Variante por red en %, tooltips con bit value [static/research.js]
- [ ] [Review][Patch] Sumas por banda cuadran exactas con el total tras redondeo + test [queries/unique_nodes.py:91]
- [ ] [Review][Patch] Tabla de bloques con p50/p90 por clase incl. IPv6 [templates/research.html, static/research.js]
- [ ] [Review][Patch] Composición en % con categorías cero visibles [static/research.js]
- [ ] [Review][Patch] lru_cache en services_breakdown + clear en conftest [queries/services.py]
- [ ] [Review][Patch] console.error en catches silenciosos del frontend [static/app.js]
- [ ] [Review][Patch] Imports muertos en test_api_latent [tests/test_api_latent.py]
- [ ] [Review][Patch] Sincronizar artefactos con lo implementado: nav 3 entradas, strip en side cluster, height_estimate, color mapping propio, x-domain auto, nombre de unit collector [openspec specs/design]
- [x] [Review][Defer] Crecimiento sin límite de la serie diaria (~40KB/año) — deferred, coste trivial
- [x] [Review][Defer] Re-parseo de ~4.3k ficheros por corrida a retención completa — deferred, optimización
- [x] [Review][Defer] /api/v1/stats/window sin trailing slash — deferred, pre-existente
