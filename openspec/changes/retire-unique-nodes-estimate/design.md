## Context

The 1/N estimate spans the whole stack: a computation module, a collector
section, a persisted JSON cache, two REST endpoints, an MCP tool, a KPI band
on the main page and a chart section on `/research`. Removing it is
mechanical, but two decisions are not obvious — what a withdrawn public
endpoint should answer, and how much of the reasoning to leave visible — and
both matter more than the deletion itself, because the project's credibility
rests on stating methodology precisely enough to be contested.

Constraint from the current state: the crawler is parked, so `peer:*` gossip
is absent, every address falls back to N = 1, and the served estimate equals
the raw reachable count. The defect is invisible in production right now and
would reappear the moment the crawler resumes. There is no rush created by
live wrong numbers, and no reason to wait either.

## Goals / Non-Goals

**Goals:**

- Stop publishing a deduplicated node count anywhere: page, REST, MCP.
- Leave the explanation where a data consumer meets it (the withdrawn
  endpoint's response), so the retraction reads as method rather than as a
  feature quietly disappearing.
- Keep the honest neighbouring metrics untouched (reachable now, windowed
  unique counts, propagation, services).
- Keep the main page as it is meant to be: a few basic, public charts over
  data that stands up.

**Non-Goals:**

- Rescuing the metric with a different weighting. The target quantity is not
  observable; no weighting fixes that.
- Self-announcement capture (distinguishing a node's own address from
  relayed gossip, and detecting nodes that leak an address from another
  network). Genuinely interesting, needs crawler-side work, belongs in its
  own change.
- Any new dashboard copy, chart or panel. The project's purpose is to make
  the crawler's data available and to recount how it was built, not to
  maintain metrics; a retraction should subtract work, not add it.
- Removing the crawler's `peer:*` keys. They are the crawler's addr-gossip
  cache and serve the crawl itself; only our interpretation of them was
  wrong.

## Decisions

**Withdraw the v1 endpoint with 410 Gone, not 404.**
`GET /api/v1/stats/unique-nodes/` is part of the public, bitnodes.io-adjacent
surface; a client that integrated it deserves to learn the route was
withdrawn rather than mistyped. 410 with a short body naming the reason and
the windowed alternative turns an integration break into a readable message.
Alternatives considered: keep serving with a louder caveat (rejected — a
caveat does not make a wrong number right, and machines do not read
caveats); silent 404 (rejected — indistinguishable from a typo); redirect to
the windowed endpoint (rejected — the payloads are not
interchangeable, so a redirect would hand callers a different metric under
the old name). The legacy `GET /api/unique-nodes` is internal to our own
frontend and is deleted outright.

**Delete the module rather than deprecate it.**
`queries/unique_nodes.py` has no other caller and no salvageable core: the
bug is the choice of input, not the arithmetic. Keeping it as dead code
invites a future reader to re-enable it. Its docstring already cited the
method as documented elsewhere, which is precisely how a plausible-looking
mistake survives review; the reasoning now lives in the spec's REMOVED
block and in this change.

**The explanation goes on the data surface, not on a page.**
This project publishes data and an account of how it was built; the charts
are a convenience, and `/research` is a token-gated workbench with no
audience to address. So the explanation lives in the 410 body, where a data
consumer actually meets the absence, and in the write-ups, where the story
belongs. Writing a methodology note into a gated page would be explaining
something to nobody. The three facts stated are: addresses are not machines;
a multi-network node contributes one address per network; the cross-network
link is not observable. No future replacement is promised, because promising
one implies the problem is effort rather than physics.

**Two KPI bands, not a placeholder.**
Band 2 disappears rather than showing a permanent em-dash: an empty slot
reads as breakage and invites "when is this coming back?".

## Risks / Trade-offs

- **A public v1 endpoint disappears without a deprecation window** → the
  numbers it returned were wrong, so a window would prolong the harm; 410
  with an explanatory body is the mitigation, and the change is noted in
  the article and in the BNOC post rather than only in a commit.
- **The retraction may read as the metric having been sloppy** → it was, and
  saying so plainly is worth more than the metric was. The postmortem-style
  candour is the same asset the rest of the project trades on.
- **Nothing replaces it, so "how many machines?" stays unanswered** →
  correct, and the 410 body says so. The windowed counts answer a
  different, answerable question.
- **`peer:*` stays in Redis and could tempt a future reinterpretation** →
  the spec's REMOVED block records exactly what those keys contain and why
  they cannot support a dedup claim.

## Migration Plan

1. Land the code removal and the frontend changes together, so no build
   serves a page calling an endpoint that no longer exists.
2. Deploy normally. The dashboard and MCP restart on every deploy; the
   crawler is parked and unaffected.
3. Delete the stale `data/unique-nodes.json` on the host after deploy; the
   collector no longer writes it.
4. Update the outside references that cite the metric: the NLnet draft's T3
   deliverable and the archived `expose-latent-crawler-data` change, tracked
   in `docs/follow-ups.md`.

Rollback: revert the commit. Nothing persists that would need undoing beyond
restoring the deleted JSON, which the collector would rewrite.

## Open Questions

- Whether the article and the BNOC post should carry the retraction
  explicitly. Leaning yes: "we published a metric, it was wrong, here is
  why" is a stronger credential than never having shipped it.
