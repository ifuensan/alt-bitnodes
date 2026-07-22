# 2026-07-22 — cron greenlet death froze the crawler pipeline for 21.5h

## Summary

The dashboard served a frozen snapshot from 2026-07-21 13:54 UTC until
2026-07-22 11:22 UTC. No process crashed and systemd saw nothing wrong:
the failure was a single dead greenlet inside a healthy-looking process.

Root cause chain:

1. `restart()` in the crawler's `crawl.py` built **one Redis MULTI
   transaction with ~123k commands** (DELETE every `node:*` /
   `crawl:cidr:*` key, then re-seed `pending`) — a multi-MB payload
   written in a single socket send.
2. Under full crawl load (~22k open TCP sockets, 11k of them to Redis),
   that send stalled until TCP retransmissions gave up:
   `TimeoutError [Errno 110]` after ~16 min (`tcp_retries2`). A fresh
   process on an idle-ish box runs the same 200k-command transaction in
   1.5s — the stall only reproduces inside the loaded crawler process.
3. The uncaught `redis.exceptions.TimeoutError` **killed the cron
   greenlet** (2026-07-21 14:39:21Z). Nobody supervises greenlets:
   `gevent.joinall(workers)` happily keeps waiting on the remaining
   1,199.
4. cron had just set `crawl:master:state = "starting"` and died before
   restoring `"running"`, so **all 1,200 crawl workers paused politely
   forever** (`sleep(1)` loop). No crawl snapshots → ping master,
   resolve, export and seeder all starved silently downstream.

## Impact

- Public API/dashboard served a 21.5h-old snapshot (last: 12,212 nodes;
  IPv4 6,694 / IPv6 777 / I2P 4,741 / onion 0).
- No monitoring fired: every process was alive, every systemd unit
  green, port 8000 healthy. Only the data was stale.

## Diagnosis technique (worth remembering)

- py-spy showed only the gevent hub ("idle") — OS-thread tools can't see
  greenlets.
- **gdb + `PyRun_SimpleString` injection** into the live process dumped
  all 1,200 greenlet stacks (`gc.get_objects()` → `greenlet.gr_frame` →
  `traceback.print_stack`), which revealed: no cron greenlet existed,
  and every worker was waiting on `crawl:master:state`.
- The fatal traceback was in `crawl.f9beb4d9.master.out.1` — rotated by
  the brand-new logrotate config, which is why the live `.out` looked
  empty. (Rotation itself was innocent: `copytruncate`, `*.out` only.)

## Fix

Two-part, avoiding a service restart (which would have dropped ~4.8k
ramped I2P connections):

1. **Hot-patch**: injected `hotfix_restart.py` into the running master
   via gdb — monkeypatched `restart()` with a batched version (5k-command
   non-transactional pipelines, 3 retries) and spawned a supervised
   `cron_forever` loop. The batched restart finished in **8 seconds**;
   the pipeline resumed end-to-end within 2 minutes (first fresh export
   snapshot 1784719316, 11,603 rows).
2. **Durable**: same change committed to the fork on the server
   (`ifuensan/bitnodes`, branch `feat/i2p-sam-crawl`, commit `ce86094`),
   so the next crawler restart runs the fixed code. Note this bumps the
   crawler fingerprint — the next dashboard deploy will restart the
   crawler (expected I2P/onion re-ramp).

A first, naive revival attempt (respawn cron unchanged + manually set
`state = running`) died identically 16 min later — confirming the giant
transaction, not a transient glitch, was the cause.

## Open questions / follow-ups

- **Onion is at 0** and has been since the 2026-07-20 17:03 restart:
  it never re-ramped (17 → 21 → 0), while I2P re-ramped to ~4.8k in
  hours. Tor daemon logs show a circuit-timeout storm (e.g. 247k
  timed-out vs 212 completed circuits on one guard). Needs its own
  investigation — likely crawler onion-dial pressure vs. per-daemon
  circuit-build capacity; 9 daemons are configured and reachable, and
  manual onion dials through them currently fail.
- The exact kernel mechanism of the loopback send stall (ETIMEDOUT on
  lo with 8.4M cumulative listen-queue drops on the box) was not pinned
  down; the batched-write fix sidesteps the entire class.
- Consider alerting on export snapshot age (e.g. systemd timer checking
  the newest file in `BITNODES_EXPORT_DIR` is < 1h old) so a silent
  pipeline freeze pages instead of hiding for a day.
