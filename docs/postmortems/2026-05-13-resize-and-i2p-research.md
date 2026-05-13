# 2026-05-13 — c7g.2xlarge resize, BMAD install, I2P research, UI rebrand

## Summary

Continuation of the 2026-05-12 session. By the end of the day before
we'd stabilised snapshots at ~1390 reachable nodes on a t4g.medium —
the previously measured CPU ceiling. This session breaks through that
ceiling and lays the architectural groundwork for adding I2P as a
fourth network ring.

Headline outcomes:

1. **Resized production EC2 from t4g.medium → c7g.2xlarge** (2 vCPU
   → 8 vCPU, 4 GB → 16 GB RAM). Snapshots jumped from ~1390 to
   **~3700–4000 reachable nodes** at `workers=1200`.
2. **Installed BMAD Method v6.6.0** (47 skills + 3 module bundles) into
   the repo to drive structured technical research and future
   product/spec work.
3. **Completed a 6-step technical research** on adding I2P node
   discovery + crawling, with an explicit architectural axis
   ("decompose the monolith"). 1290-line research artefact at
   `_bmad-output/planning-artifacts/research/`.
4. **UI rebrand**: `Bitnodes Dashboard` → `Pesquisa Dashboard`, plus a
   credits footer pointing at `@ifuensan` and the upstream
   `ayeowch/bitnodes`. CloudFront cache invalidated explicitly so the
   change is live in minutes, not in a day.

No production downtime beyond ~3 min during the stop/resize/start
cycle.

## Impact

| Metric | Before today | After today |
|---|---|---|
| Instance | t4g.medium (2 vCPU / 4 GB) | c7g.2xlarge (8 vCPU / 16 GB) |
| Crawl workers | 500 | 1200 |
| Ping workers | 200 | 600 |
| Snapshot reachable count | ~1390 (stable) | **~3700–4000 (stable)** |
| `open:*` simultaneous | ~1390 | **~3700** |
| Load average | ~2.7 | **~1.5** |
| Tor CPU | ~95% (saturated) | ~90% (not saturating the box) |
| Monthly compute cost | ~$24/mo | ~$196/mo |
| Public dashboard | `Bitnodes Dashboard` | **`Pesquisa Dashboard`** with credits |

The ~$170/mo cost increase is the trade for ~2.7× the snapshot
reachability and proper headroom for the I2P arm. Within the
research-project budget.

## Timeline (UTC)

| Time | Event |
|------|-------|
| 04:41 | User notices first post-resize-prep snapshots are still small (`socket_timeout=60` raised but ceiling not yet broken on 2 vCPU). |
| ~05:00 | Decide to resize to c7g.2xlarge (Graviton3). Stop instance, modify instance-type, start. EIP preserved. ~3 min downtime. |
| 05:10 | Push commit raising `crawl.workers` 500 → 1200, `ping.workers` 200 → 600 in `install.sh`. Workflow Deploy to EC2 fires; `git pull && install.sh` (the fix from yesterday) applies cleanly first time. |
| 05:12 | First post-resize snapshot files start landing. Ramp-up visible (~600 nodes). |
| 05:30 | First fully-converged snapshot: **3714 nodes**. |
| 05:50 | Second snapshot: **4011**. Confirmed stable. Load ~1.5; Tor CPU dropped from 95% to ~85% with room to spare. |
| 06:00 | Install BMAD Method (`npx bmad-method install -y --tools claude-code --modules bmm,bmb`). 47 new skills under `.claude/skills/bmad-*`. Gitignore updated to skip `_bmad/config.user.toml`. |
| 06:20 | Start `/bmad-technical-research` for "Bitcoin I2P node discovery and crawling — integration with alt-bitnodes". Scope confirmed at step 1; user adds an architectural axis ("decompose the monolith"). |
| 06:30–07:30 | Steps 2–6: technology stack, integration patterns, architectural patterns, implementation research, synthesis. ~16 parallel web searches across the steps. Direct audit of `ayeowch/bitnodes` master finds I2P plumbing exists but `crawl.py:222` explicitly skips dialing I2P peers. Effort estimate: ~205 LOC, ~2 working days for end-to-end I2P. |
| 07:35 | Commit + push the research file. Auto-deploy fires; no harmful effect (crawler restarts but no config change). |
| ~07:50 | UI rebrand: `templates/index.html` h1+title to "Pesquisa Dashboard", new `<footer>` with credits to `@ifuensan` and the upstream `ayeowch/bitnodes`, plus accent-coloured CSS rules. Commit, push, CloudFront invalidation on `/static/app.css`, `/static/app.js`, `/`. |

## What we tried, and what worked

### Vertical scale-up (t4g.medium → c7g.2xlarge)
- One CLI dance (`stop` → `modify-instance-attribute` → `start`),
  EIP preserved, services came up clean.
- **Worked.** Same install/config; only the underlying compute
  changed. The "CPU is the bottleneck" hypothesis from the previous
  postmortem was confirmed by the linear jump in `open:*` after the
  resize.

### Workers tuning on the new host (500 → 1200)
- Same install.sh `sed` block, value swapped, push.
- **Worked first try** — the `git pull && install.sh` fix from
  yesterday meant no manual re-apply on the EC2 was needed.

### BMAD install
- Non-interactive: `--tools claude-code --modules bmm,bmb -y
  --communication-language Spanish`.
- **Worked first try.** 47 skills appear in the `.claude/skills/`
  inventory and are available via the Skill tool. Three of the
  installed module skill directories (`bmm/`, `bmb/`, `core/`) live
  in `_bmad/` next to the install configs.

### Technical research workflow
- Followed `bmad-technical-research` SKILL.md template: scope
  confirmation → tech stack → integration → architecture →
  implementation → synthesis.
- **Worked as designed.** Each step has explicit `[C]` user gate, so
  there's no runaway content generation. Citations carried through
  to every claim. Final artefact reads as a real research doc, not
  filler.

### UI rebrand + CloudFront invalidation
- Single commit: HTML + CSS.
- Explicit `create-invalidation` on `/static/app.*` + `/` so users
  see the new title within minutes instead of waiting up to a day.
- **Worked.** `curl` against the public hostname returned the new
  title and footer within ~3 min of invalidation completing.

## What didn't work, and why

- **The `--no-restart` instinct on doc-only deploys was rejected**
  earlier (option C in yesterday's discussion). It still bites: every
  push, including the docs / BMAD / research commits today, restarts
  the crawler. The c7g.2xlarge ramps back to steady state in ~10 min,
  so the cost is bearable, but it remains the obvious next
  operational improvement once the architectural split lands.

## Lessons

1. **"Just resize first" is sometimes right.** Yesterday's
   investigation suspected CPU was the wall but didn't confirm.
   Today's resize confirmed it cleanly: 4× the vCPU → ~3× the snapshot
   count, exact linearity at our scale.
2. **Tor isn't the bottleneck on bigger boxes** (yet). With 8 vCPU
   absorbing handshake work, Tor's 92% CPU stops being load-bearing
   for the whole system. The 1-thread Tor process is still a
   theoretical ceiling but not the practical one today.
3. **Structured research has its place.** Investing 1–2 hours into a
   six-step research doc on I2P meant arriving at "~2 days of work,
   $48/mo extra, here are the 4 files to touch" rather than guessing.
   The architectural analysis (modular distributed monolith,
   role-split, Redis Streams) reused the same primitives we already
   run, which keeps the migration ratchet pointing in the right
   direction.
4. **Cache invalidation should be explicit** for cosmetic releases.
   The default 1-day TTL on `/static/*` is right for performance but
   wrong for "I want the title to update now". Costs ~$0 in
   invalidation fees within the free tier; do it whenever HTML/CSS
   ships.

## Addendum (later in the day): tcpdump was the snapshot-oscillation culprit

After the resize, snapshots still oscillated occasionally between
~600 and ~4000 nodes. We'd attributed this to `snapshot_delay` vs
sweep time but the pattern looked too random for a pure timing issue.

Hypothesis: the `tcpdump-pcap.service` running on the same host with
`-s 0` (full-packet capture) and producing ~100–200 MB/min of pcaps
was creating I/O and kernel softirq pressure that intermittently cut
handshakes mid-flight, draining `open:*` right when the master pegged
a snapshot.

Experimental A/B (some pushes contaminated the test, but the trend
was unambiguous):

| Phase | Snapshot counts (chronological) |
|---|---|
| tcpdump ON | 4168, 4165, 558, 688, 3846, 824 — oscillating |
| `systemctl stop tcpdump-pcap` at 09:28 | (post-restart ramp) |
| 22 min post-restart, tcpdump OFF | 3724, 3932, 4022, 4073, 4108 — **monotonic, no oscillation** |

`open:*` peaked at 4115. Load fell to ~1.4. Confirmed `tcpdump` was
the dominant cause of the oscillation, not `snapshot_delay`.

Operational decision: **`install.sh` now disables
`tcpdump-pcap.service` and `pcap-cleanup.timer` by default**. The cost
is that `cache_inv` has no pcaps to read, so RTT samples stop flowing
and the dashboard's `latency_ms` / leaderboard go null. Accepted as a
trade for snapshot stability.

Follow-up tracked in `docs/follow-ups.md`: replace the passive pcap
pipeline with active pings from `ping.py` / `cache_inv.py` so RTT
returns without bringing the sniffer back.

## Follow-ups

- Implement the I2P SAM client per the research file. Branch
  `feat/i2p-sam-crawl` on `ifuensan/bitnodes`. Estimated ~9h coding
  + ~4h infra. Next session.
- Add `install.sh --role` machinery once the I2P arm proves the
  split. Then extract Tor to its own VM (the postmortem's
  follow-up #1 from yesterday).
- Consider raising `workers` from 1200 to 1500 on c7g.2xlarge —
  haven't measured the new ceiling, only know that we haven't hit
  it.
- Tighten `deploy.yml` to skip deploy on doc-only changes (option B
  from yesterday's discussion), if the restart cost becomes
  annoying once the I2P branch is in flight.

## Final config (snapshot at end-of-day)

| Setting | Value | Notes |
|---|---|---|
| Instance | c7g.2xlarge (8 vCPU, 16 GB, Graviton3) | resized today |
| `crawl.workers` | 1200 | was 500 |
| `ping.workers` | 600 | was 200 |
| `crawl.socket_timeout` | 60 | restored from 30 |
| `crawl.onion_peers_sampling_rate` | 25 | unchanged |
| `crawl.snapshot_delay` | 900 | unchanged |
| `crawl.slaves` (run-bitnodes.sh) | 2 | unchanged |
| `ping.slaves` | 6 | unchanged |
| UI title | `Pesquisa Dashboard` | rebranded today |
| Public URL | `https://pesquisa.hacknodes.xyz` | unchanged |
| BMAD Method | v6.6.0 installed | new today |
