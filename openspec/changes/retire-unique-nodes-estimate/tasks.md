## 1. Remove the computation

- [x] 1.1 Delete `queries/unique_nodes.py` and its export from
      `queries/__init__.py` (`load_unique_estimate`, `write_unique_estimate`)
- [x] 1.2 Remove the unique-estimate section from `collector.py` (import and
      the section call), leaving the other sections and their per-section
      failure isolation intact
- [x] 1.3 Remove `UNIQUE_STATS_FILE` from `queries/config.py`
- [x] 1.4 Delete `tests/test_unique_nodes.py`

## 2. Withdraw the endpoints

- [x] 2.1 Delete the legacy `GET /api/unique-nodes` route from `app.py`
- [x] 2.2 Replace `GET /api/v1/stats/unique-nodes/` with a 410 Gone whose
      body names the reason and points to `/api/v1/stats/window/`
- [x] 2.3 Drop the now-unused `load_unique_estimate` import from `app.py`
- [x] 2.4 Add a test asserting the v1 route answers 410 with the pointer,
      and that the legacy route is gone (404)

## 3. Remove the MCP tool

- [x] 3.1 Remove `get_unique_nodes_estimate` from `alt_bitnodes_mcp/tools.py`
      and its `load_unique_estimate` import
- [x] 3.2 Update `tests/test_mcp_tools.py` / `tests/test_mcp_latent.py` so
      they assert the tool is not registered
- [x] 3.3 Update the MCP docs/README tool listing if it names the tool

## 4. Update the dashboard

- [x] 4.1 Remove KPI band 2 from `templates/index.html` and its fetch of
      `/api/unique-nodes` in `static/app.js`, leaving bands 1 and 3 aligned
- [x] 4.2 Delete the `#unique` panel from `templates/research.html`
      (no replacement copy: the page is gated and has no audience)
- [x] 4.3 Remove section 3 (`renderComposition`, `loadUnique`) from
      `static/research.js` and its call site

## 5. Verify and deploy

- [x] 5.1 Run the full test suite; confirm no reference to the estimate
      remains (`grep -ri unique_nodes` over first-party sources)
- [x] 5.2 Load `/` and `/research?token=…` locally: two KPI bands, no
      composition section, no console errors
- [ ] 5.3 Deploy, then delete the stale `data/unique-nodes.json` on the host
- [ ] 5.4 Confirm the parked crawler stack is still parked after the deploy
      (`install.sh` honours `/etc/alt-bitnodes/parked-units` since 0983c13,
      but this deploy is the first one after the retirement — verify)

## 6. Close the loop outside the code

- [ ] 6.1 Sync `openspec/specs/` (retire `unique-nodes-estimate`, update
      `research-page` and `mcp-service`) and archive this change — after
      the deploy, per this project's convention of archiving on live
      verification
- [x] 6.2 Record in `docs/follow-ups.md` that the NLnet draft's T3
      deliverable and the archived `expose-latent-crawler-data` change cite
      a metric that no longer exists
- [x] 6.3 Decide whether the article and the BNOC post carry the retraction
      explicitly — decided yes (ifuensan, 2026-08-07). The Delving draft
      carries a full retraction section; the published hacknodes.com
      articles and the BNOC post are ifuensan's to amend, tracked in
      `docs/follow-ups.md`
