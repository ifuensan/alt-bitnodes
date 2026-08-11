## Why

b10c suggested that raising Tor's `MaxCircuitDirtiness` would cut handshake
churn. The manual makes the mechanism concrete: "Feel free to reuse a circuit
that was first used at most NUM seconds ago... **For hidden services, this
applies to the last time a circuit was used, not the first.**" For onion
circuits the 10-minute default is therefore an *idle* timer, and our crawl
revisits every onion every `snapshot_delay = 1800` — three times that window.
Every cycle finds every rendezvous circuit expired and repays a full onion
handshake: descriptor lookup, introduction circuit, rendezvous circuit. With
`UseEntryGuards 0` a new circuit usually also means a new OR connection and a
fresh TLS handshake to a random relay, which is where the measured ~1,000 new
TLS connections/min come from.

We cannot test that suggestion as things stand. Both `crawl.py:268` and
`ping.py:257` pick the Tor daemon with `random.choice(CONF["tor_proxies"])`
on every dial, so a revisit lands on the daemon holding the warm circuit with
probability 1/9. Any dirtiness increase would show ~11% of its true effect —
indistinguishable from noise, and we would bury a good idea for the wrong
reason.

Proxy affinity is worth having on its own merits, independent of the
experiment. Each Tor client keeps its own hidden-service descriptor cache, so
spreading one onion's dials across nine daemons means up to nine descriptor
fetches for the same service. Affinity divides that by the pool size.

## What Changes

- Onion dials select their Tor proxy by a **stable hash of the onion
  address** instead of at random, so a given `.onion` always goes through the
  same daemon and can reuse the circuit that is already open to it.
  `crawl.py` and `ping.py` SHALL use the same function, so the two processes
  feed the same daemon and share its circuits.
- The behaviour is controlled by a new crawler config key,
  `tor_proxy_affinity` (default on), so the arm can be switched off without a
  code rollback and so the change is itself measurable.
- Unchanged: `ipv4_proxies` / `ipv6_proxies` keep random selection (they
  exist to spread source addresses, not to reuse circuits), and I2P is
  untouched (SAM sessions are already one persistent session per process).
- The deployment gains the instrumentation needed to compare arms:
  `IPAccounting=yes` on the `tor@` template unit, a lowered `HeartbeatPeriod`
  so each daemon reports its own handshake counters, and an installer
  variable that gives a subset of the pool a different `MaxCircuitDirtiness`
  so the two arms can run side by side.
- A sampler script writes per-daemon egress and carried-connection counts to
  CSV, so the comparison is a data file rather than a memory of a terminal.

Not in scope: choosing the winning `MaxCircuitDirtiness` value. This change
makes the experiment possible and honest; the value it selects is a
follow-up, decided by the data.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `onion-crawling`: the requirement that the crawler spreads onion dials
  across the pool is replaced by one that assigns each onion to a daemon
  deterministically. The pool still exists and is still fully used — the
  spreading is now per-address rather than per-dial.
- `crawler-systemd-units`: the Tor units gain per-unit IP accounting, and the
  installer learns to write a per-instance `MaxCircuitDirtiness` for an
  A/B arm without breaking the byte-comparison that keeps deploys from
  restarting daemons needlessly.

## Impact

- **Code (fork `ifuensan/bitnodes`)**: `crawl.py`, `ping.py`, the two
  `conf/*.conf.default` files, and tests.
- **Code (this repo)**: `deploy/install.sh`, a new `tor@.service.d` drop-in,
  and `deploy/tor-experiment-sample.sh`.
- **Operational**: the first deploy after this lands rewrites every torrc
  (heartbeat + accounting) and therefore restarts the whole Tor pool. That
  costs a ramp — which is fine, because the experiment wants every daemon
  starting cold at the same moment anyway. It must not be done casually
  mid-run.
- **Cost**: the run itself is ~24h of crawler at AWS egress rates. Running it
  with `i2p = False` keeps it near $10 instead of $22, since i2pd is ~55% of
  egress and irrelevant to a Tor question.
- **Risk**: with affinity, a dead daemon blackholes its whole share of onions
  instead of losing 1/9 of dials. See design.md.
