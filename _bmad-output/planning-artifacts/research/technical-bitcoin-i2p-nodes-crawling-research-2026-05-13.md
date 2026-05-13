---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
status: 'complete'
research_type: 'technical'
research_topic: 'Bitcoin I2P node discovery and crawling — integration with alt-bitnodes'
research_goals: 'Entender cómo se anuncian/descubren los nodos I2P en la red Bitcoin y qué cambios necesita el stack actual (bitnodes + tor) para añadir crawl de I2P. Decidir si vale la pena integrarlo. Incluye dimensión arquitectural: descomponer el monolito actual en VMs especializadas.'
user_name: 'ifuensan'
date: '2026-05-13'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-05-13
**Author:** ifuensan
**Research Type:** technical

---

## Research Overview

### Confirmed scope (step 1)

Technical research on Bitcoin I2P node discovery + crawling, with an
explicit architectural axis: the current alt-bitnodes deploy is a single
EC2 (c7g.2xlarge) running crawler + Tor + Redis + FastAPI + nginx +
tcpdump in one box. That co-location has bitten us repeatedly:

- Tor pinned at 95% CPU degraded the dashboard.
- Every `install.sh` deploy restarts the crawler, even for doc changes.
- Any noisy component starves the others.

The research will cover, in this priority order:

1. **Distributed architecture options** for decomposing the monolith
   (minimal split, by-network-ring, by-component) — comparative against
   the current shape on isolation, total cost, IPC latency, ops effort.
2. **Bitcoin I2P protocol surface** — BIP155 (addrv2), `.b32.i2p`
   addresses, how nodes announce I2P endpoints in `addr`/`getaddr`.
3. **I2P daemon options** — i2pd vs java-i2p, SAM v3 vs HTTP tunnels,
   Python integration libs (`i2plib`, `txi2p`), upstream
   `ifuensan/bitnodes` support state (PRs, forks, capabilities).
4. **Sizing the new I2P VM** — CPU/RAM expectations for i2pd + crawl
   workers, AWS ARM compatibility, comparable workload to Tor.
5. **Cross-VM data plane** — shared Redis vs explicit queues
   (Redis pub/sub, NATS), latency budgets within an AZ.
6. **Cost & ops** — total cost vs single c7g.2xlarge, deploy plane
   (single install.sh with `--role` vs split repos), CI for multi-node.

### Methodology

- Web search for current docs and code references (cutoff May 2026).
- Multi-source verification on critical technical claims (BIPs, daemon
  docs, source code).
- Confidence markers when claims rest on a single source.
- Citations tied to each claim, collated at the end.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technology Stack Analysis

### I2P address gossiping in Bitcoin (BIP155 / `addrv2`)

Bitcoin Core has full I2P support since **v22.0 (Sept 2021)**. The
`addrv2` and `sendaddrv2` p2p messages (BIP155) carry I2P
`.b32.i2p` destinations in the same gossip flow as IPv4/IPv6/Tor
addresses. Nodes that announce `sendaddrv2` during the handshake will
both relay and accept I2P addresses, even if they themselves are not
I2P-reachable — so an I2P-only crawler can still receive a fairly
complete view of the I2P node set from clearnet peers, as long as those
peers speak addrv2.

- _Confidence: high (Bitcoin Core docs + multiple PR threads)._
- _Sources:_ [bitcoin/doc/i2p.md](https://github.com/bitcoin/bitcoin/blob/master/doc/i2p.md),
  [PR #19031 BIP155](https://github.com/bitcoin/bitcoin/pull/19031),
  [PR #19954 complete BIP155 + TORv3](https://github.com/bitcoin/bitcoin/pull/19954),
  [I2P launch blog post](https://geti2p.net/en/blog/post/2021/09/18/i2p-bitcoin).

### I2P daemon: `i2pd` (C++) vs Java I2P

For an embedded crawler use case the choice is clear-cut:

| Trait | `i2pd` (C++) | java-i2p |
|---|---|---|
| Runtime | native binary | JRE required |
| Memory | low (tens of MB) | hundreds of MB |
| CPU | optimised crypto, lower load | higher overhead |
| Bloat | router only, talk via SAM/I2CP | bundles torrents, email, UI |
| ARM64 support | first-class (Debian, Docker, source build) | possible but JVM ergonomics |

For a Graviton instance dedicated to crawl/ping over I2P, `i2pd` is the
sane default. It's the equivalent role to what `tor` plays today on
the existing host.

- _Confidence: high (i2pd wiki + I2P alternative-clients page agree)._
- _Sources:_ [PurpleI2P/i2pd](https://github.com/PurpleI2P/i2pd),
  [Differences i2pd vs Java I2P (i2pd wiki)](https://github.com/PurpleI2P/i2pd/wiki/Differences-between-i2pd-and-Java-I2P-router),
  [Alternative I2P clients (geti2p)](https://geti2p.net/en/about/alternative-clients).

### Python integration via SAM v3

`i2pd` (and java-i2p) expose a **SAM bridge** on `127.0.0.1:7656`
where applications open a socket, do a handshake, and issue
`SESSION CREATE` to obtain anonymous streaming sockets to/from
`.b32.i2p` destinations. SAM v3.3 also supports subsessions (multiple
streams on one session), useful for connection pools.

Mature Python options:

- **`i2plib`** — modern, asyncio-based, SAMv3 bindings. Best fit if we
  rewrite the I2P crawl module against asyncio.
- **`txi2p`** — Twisted-based, supports SAM and BOB. Mature but tied to
  Twisted, which clashes with the upstream `bitnodes` greenlets/gevent
  model.
- **`leaflet`** — minimal SAM library, plain sockets. Easiest to drop in
  next to the existing gevent crawler with the lowest dependency cost.
- **`i2p.socket`** — drop-in socket replacement; least invasive but
  potentially heavyweight wrapper.

Pragmatically, for a port of the existing `crawl.py`/`ping.py`, either
`leaflet` (sync sockets, fits gevent) or a thin SAM client we write
ourselves would integrate cleanly. `i2plib` would be the right pick if
we choose to split into a dedicated I2P-only crawler subprocess written
fresh.

- _Confidence: high for library list and protocol;
  medium for the integration-fit recommendation (depends on whether we
  split or extend)._ 
- _Sources:_ [i2plib (PyPI)](https://pypi.org/project/i2plib/),
  [str4d/txi2p](https://github.com/str4d/txi2p),
  [MuxZeroNet/leaflet](https://github.com/MuxZeroNet/leaflet),
  [SAM V3 spec](https://i2p.net/en/docs/api/samv3/),
  [I2P dev tutorial with Python/asyncio](https://geti2p.net/en/blog/post/2018/10/23/application-development-basics).

### Upstream `ayeowch/bitnodes` and I2P

Findings:

- The repo has a commit titled **"Add support for multiple networks"**,
  and the source includes references to I2P (e.g. an `I2P_SUFFIX`
  constant), suggesting the codebase already recognises I2P endpoints
  arriving via `addr`/`addrv2`.
- It is **not clear from a quick search whether `crawl.py` actually
  opens connections to I2P peers via SAM today**, or whether it just
  parses the addresses and lists them as known. Needs a code-level
  audit of the upstream and our fork (`ifuensan/bitnodes`,
  `fix/empty-include-asns` branch) before deciding scope.
- Active fork ecosystem: 315 forks, lots of room to find pre-existing
  I2P work that can be cherry-picked.

Action item for step 5 (implementation): clone `ayeowch/bitnodes`
locally and grep for `i2p`, `b32.i2p`, `sam`, `samv3` to map the
existing support and any TODOs.

- _Confidence: medium (commit titles + grep hits; full code audit
  pending)._
- _Sources:_ [ayeowch/bitnodes README](https://github.com/ayeowch/bitnodes),
  [Add support for multiple networks (commit)](https://github.com/ayeowch/bitnodes/commit/5e7202910d59ab910dd2291a8def9be0d3604827),
  [crawl.py upstream](https://github.com/ayeowch/bitnodes/blob/master/crawl.py),
  [Issue #64 "Is Bitnodes mirrored via Onion or I2P?"](https://github.com/ayeowch/bitnodes/issues/64).

### Cross-VM data plane (Redis)

If we split components across EC2 instances, the existing Redis can
serve as the shared substrate without re-architecting:

- **Same VPC, same AZ**: EC2→EC2 latency over a private IP is
  sub-millisecond. Redis pipelined ops will not become a bottleneck.
- **Cross-AZ** (e.g. crawler in AZ-A, data plane in AZ-B): adds 1–2 ms
  per RTT and a small egress cost; tolerable but worth avoiding if the
  hot path is chatty (it is).
- **Security**: ElastiCache and self-managed Redis both require SG
  rules that allow only the trusted instances on port 6379. No public
  exposure ever.
- **PrivateLink / cross-account**: adds ~400–500 µs; only matters if
  we ever want to expose Redis to another account.

Recommendation: keep self-managed Redis on the data-plane VM (cheap,
already running, no migration); put crawler VMs in the **same AZ** as
that VM; connect via security-group-locked private IPs. ElastiCache is
overkill for current scale ($24-48/mo for the smallest cache).

- _Confidence: high._
- _Sources:_ [ElastiCache VPC access patterns](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/elasticache-vpc-accessing.html),
  [Common troubleshooting / best practices](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/wwe-troubleshooting.html),
  [PrivateLink access pattern](https://medium.com/@programmerohit/accessing-aws-elasticache-redis-from-multiple-aws-accounts-via-aws-privatelink-8938891bec6c).

### Distributed crawler patterns

The well-trodden architecture for this class of crawler — applied to
both web and P2P-network crawlers, including `bitnodes` itself in its
multi-AZ deployments — is **master + worker pool + Redis broker**:

- Master holds the de-duplication set and address pool (Redis sets +
  bloom filter if needed).
- Workers pull jobs (addresses to dial), do the protocol-level work
  (handshake / ping / decode), write results back to Redis.
- Coordination via Redis lists / streams / pub-sub. No need for a
  heavier queue (Celery, NATS) until the worker count is in the
  hundreds.

For our case the same model applies; what changes is **per-network
specialisation**:

- Clearnet workers: pure TCP, no proxy.
- Tor workers: connect via local Tor SOCKS at `127.0.0.1:9050`.
- I2P workers: connect via local i2pd SAM bridge at `127.0.0.1:7656`.

That neatly motivates one VM per network ring (each with its own
sidecar daemon), with a shared Redis on a fourth VM — exactly the
"by-network-ring" option in step 1.

- _Confidence: high (well-established pattern, plus bitnodes provisioning
  wiki documents this shape)._
- _Sources:_ [bitnodes provisioning wiki](https://github.com/ayeowch/bitnodes/wiki/Provisioning-Bitcoin-Network-Crawler),
  [Distributed Web Crawling Made Easy (ZenRows)](https://www.zenrows.com/blog/distributed-web-crawling),
  [Redis architecture overview](https://medium.com/@alekhpandya/redis-architecture-explained-c2224274e2ae).

### Sizing the I2P VM

We have a real-world reference: Tor on the current c7g.2xlarge consumes
~95% of one core and ~16% of 16 GB RAM at sustained load. `i2pd` is
broadly comparable but tends to be:

- Lighter on CPU per circuit (optimised C++ crypto), but with more
  variability because I2P circuits are longer-lived and route through
  more hops.
- Lighter on memory (tens of MB router footprint vs. hundreds for Tor's
  cell pools, especially without onion-service hosting).
- More peer-dependent — I2P discovery via netDb requires keeping a
  warm view of the I2P floodfill nodes, which costs steady network +
  some disk.

For a workload of "this crawler's I2P arm only", a small ARM instance
should be sufficient:

- **`t4g.large` (2 vCPU, 8 GB, ~$48/mo)** as a starting point.
- Scale to **`c7g.large` (~$60/mo)** if we want compute predictability
  (no burst credits).

We almost certainly don't need an `xlarge` for the I2P workload alone,
because the workers driving it (a few hundred) are CPU-cheap when
they're mostly waiting on I2P RTT.

- _Confidence: medium-low (no I2P-on-AWS benchmark data found in
  search; numbers are extrapolated from Tor's known load + i2pd
  efficiency claims). Validate empirically once a VM is up._
- _Sources:_ [i2pd FAQ on resource use](https://docs.i2pd.website/en/latest/user-guide/FAQ/),
  ArchWiki I2P (general reference).

### Cost comparison (rough monthly, us-east-1)

| Option | Compute | Expected snapshot reach | Notes |
|---|---|---|---|
| Current: 1× c7g.2xlarge | $196 | clearnet + Tor, ~4k nodes | what we run now |
| Split: c7g.2xlarge (data+clearnet+Tor) + t4g.large (I2P) | $196 + $48 = $244 | + I2P arm | minimal disruption; one new VM |
| Split: 1× c7g.xlarge (data) + 3× c7g.large (clearnet, Tor, I2P) | $98 + 3×$60 = $278 | full ring split | maximum isolation; more moving parts |
| Frozen monolith resize-up: 1× c7g.4xlarge | $392 | best snapshot but still shared Tor problem | doesn't solve the architectural issue |

The minimal split (option 2) buys us I2P coverage and one degree of
fault isolation for ~$50/mo extra — the most rational first move.
Full ring-split is cleaner but only worth it if we plan to keep adding
networks (CJDNS, Yggdrasil…).

- _Confidence: high on the math, medium on the snapshot-reach prediction
  for the I2P arm (we'll know after the first 24h of running it)._

### Quality assessment / research gaps

- **Open question 1:** does `ayeowch/bitnodes` `crawl.py` already
  drive I2P connections via SAM, or just parse I2P addrs? Needs code
  audit in step 5.
- **Open question 2:** what's the actual reachable I2P node count on
  mainnet today? Search results don't surface a live number. We can
  estimate post-deployment by counting `.b32.i2p` entries in our own
  address pool.
- **Open question 3:** does `i2pd` ARM64 build cleanly on Ubuntu 24.04
  Graviton (apt package vs source)? Should be yes (it's in Debian
  unstable) but worth verifying.
- **Open question 4:** can we keep the dashboard pinned to the
  data-plane VM in a way that lets crawler VMs come and go without
  affecting `https://pesquisa.hacknodes.xyz`? Probably yes (CloudFront
  origin is the data-plane VM), but the install.sh deploy flow needs
  to grow a `--role` knob.

These flow into step 3 (Integration Patterns) and step 4 (Architectural
Patterns).

## Integration Patterns

This section answers: **given the components from step 2 (i2pd, the
crawler workers, Redis, the dashboard), how exactly do they plug
together — over what protocols, with what failure modes, and what
operational primitives wire the whole thing?**

### Application ↔ i2pd: SAM v3.1 over `127.0.0.1:7656`

The integration surface between the Python crawler and the I2P
daemon is **SAM v3** (Simple Anonymous Messaging), the same shape as
Tor's SOCKS but with richer session semantics.

- **Bridge endpoint**: by default `127.0.0.1:7656`, enabled in
  `i2pd.conf` under the `[sam]` section (`enabled = true`). Single
  config flag — no other tuning is strictly required to start.
- **Minimum protocol version**: **SAM 3.1**, the recommended floor.
  3.0 lacks modern signature types (EdDSA); 3.3 adds primary sessions
  + subsessions if we later want one socket per worker pool to share
  an I2P destination.
- **Per-connection flow**:
  1. TCP connect to `127.0.0.1:7656`.
  2. `HELLO VERSION MIN=3.1 MAX=3.3` → bridge acknowledges.
  3. `SESSION CREATE STYLE=STREAM ID=...` once per worker (or once
     per pool if using subsessions).
  4. `STREAM CONNECT ID=... DESTINATION=<b32.i2p>` to dial a peer.
  5. From there it's a normal TCP-like socket — write the Bitcoin
     `version` message just like to a clearnet peer.
- **Reseed**: i2pd needs ≥25 known routers in its netDb before it'll
  build tunnels. Fresh installs do this automatically from baked-in
  reseed servers — operational concern is "give it 1–2 min on first
  boot before pointing workers at it".
- **Tunnel length**: i2pd default is 5; we can drop to 2–3 for our
  crawler (we don't need maximum anonymity for outbound dials, we
  need throughput). Trade-off: less anonymity for the crawler
  identity (fine — it's not a hidden service).

The integration with the existing `bitnodes` crawler stays
**conceptually identical to Tor**: where today `crawl.py` uses
`socks.socksocket` against `127.0.0.1:9050`, the I2P variant opens a
plain socket against `127.0.0.1:7656` and speaks SAM before
delegating to the standard Bitcoin handshake.

- _Confidence: high (SAM v3 spec + i2pd docs agree)._ 
- _Sources:_ [SAM V3 (geti2p)](https://i2p.net/en/docs/api/samv3/),
  [i2pd configuration docs](https://docs.i2pd.website/en/latest/user-guide/configuration/),
  [PurpleI2P/i2pd repo](https://github.com/PurpleI2P/i2pd).

### Bitcoin handshake over an anonymous tunnel: timing budget

I2P circuits are higher-latency than Tor. The `version`/`verack`
handshake has hard timeouts on the Bitcoin Core side:

- **Bitcoin Core disconnects** if no `version` is received within
  ~20 min of TCP establishment.
- **The crawler's** `socket_timeout = 60` is what we use today (was
  30 during the Tor-saturation incident).
- I2P first-hop RTT is typically **200–800 ms** depending on tunnel
  composition; full request/response can hit several seconds.

Implication for our config: keep `socket_timeout = 60` on I2P workers
(same as we re-raised for Tor) and accept that throughput per worker
will be ~half that of clearnet. Sizing of `workers` for the I2P arm
should compensate: if Tor at 500 workers gets us ~3700 `open:*`, I2P
will probably need ~500 too for a comparable arm — but capped by what
i2pd can build in tunnels.

- _Confidence: medium — handshake limits are factual, the I2P RTT band
  is a generalisation that needs measurement on our actual peers._
- _Sources:_ [Bitcoin developer P2P reference](https://developer.bitcoin.org/reference/p2p_networking.html),
  [Bitcoin Core test/functional/p2p_timeouts.py](https://github.com/bitcoin/bitcoin/blob/master/test/functional/p2p_timeouts.py),
  [Bitcoin Networking tutorial](https://learnmeabitcoin.com/technical/networking/).

### Coordination plane: which Redis primitive for jobs?

Today the `ayeowch/bitnodes` family uses Redis **lists** (`LPUSH` /
`BRPOP`) and **sets** for the address pool, and that works fine on a
single host. Once we move to multi-VM, the failure modes change: a
worker VM can die mid-job, and a `BRPOP`'d address is lost forever
(no replay).

Comparison for the cross-VM case:

| Primitive | Persistence | Worker failure recovery | Replay | Use here |
|---|---|---|---|---|
| `LIST` (LPUSH/BRPOP) | message vanishes on pop | none | none | OK for single host, lossy across VMs |
| `PUBSUB` | fire-and-forget, no buffer | none | none | wrong tool entirely |
| `STREAMS` (XADD/XREADGROUP) | append-only, retained until trimmed | consumer groups + XACK | yes | **right tool for cross-VM workers** |

Recommendation: **migrate the cross-VM job queue to Redis Streams
with consumer groups** when (and only when) we actually split VMs.
On a single host the lists are fine, and the migration is local to
master + worker glue code.

- **One stream per network ring**: `crawl:clearnet`, `crawl:tor`,
  `crawl:i2p`. Workers in a given VM only consume from "their"
  stream.
- **`XADD` from the master** when a fresh address is discovered (or
  due for re-crawl).
- **`XREADGROUP > NOACK` is wrong** — we want `XACK` after the
  handshake completes so a crashed worker's jobs are reclaimed via
  `XAUTOCLAIM`.
- **Trim policy**: `XADD MAXLEN ~ 100000` keeps memory bounded.

- _Confidence: high._
- _Sources:_ [Redis Streams vs Pub/Sub (OneUptime)](https://oneuptime.com/blog/post/2026-01-21-redis-streams-vs-pubsub/view),
  [Redis Streams introduction (antirez)](https://antirez.com/news/114),
  [Redis as a message broker (Semaphore)](https://semaphore.io/blog/redis-message-broker).

### Network plane: VPC, security groups, and what each VM can talk to

We're already on AWS in a single VPC and AZ; we add VMs and keep
inter-VM traffic on private IPs. The clean primitive is
**security-group referencing**: a SG inbound rule whose "source" is
another SG (not a CIDR), so the rule auto-tracks instance membership.

Concrete shape:

```
SG: alt-bitnodes-data
  - inbound: TCP 6379 from SG=alt-bitnodes-crawler  (Redis)
  - inbound: TCP 80   from prefix-list CloudFront  (nginx, existing)
  - inbound: TCP 22   from your dev IP             (SSH)

SG: alt-bitnodes-crawler   (one per crawler VM, or shared)
  - inbound: TCP 22  from your dev IP              (SSH)
  - outbound: any                                  (default)
```

Properties:

- Crawler VMs cannot be reached **from anywhere except SSH from your
  IP**. They dial Redis on the data VM via the SG reference.
- The CloudFront-facing nginx stays exactly where it is (on the data
  VM). No edge config changes.
- Adding a new crawler VM = launching with `alt-bitnodes-crawler` SG.
  No SG edits needed.
- Same AZ keeps latency to Redis at <1 ms.

- _Confidence: high._
- _Sources:_ [Control traffic with security groups (VPC user guide)](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html),
  [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html),
  [Security group rules for different use cases (EC2)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html).

### Deploy plane: one `install.sh` with `--role`

The cleanest evolution of the current `install.sh` is a
**role-aware** installer:

```bash
sudo bash install.sh --role data
sudo bash install.sh --role clearnet
sudo bash install.sh --role tor
sudo bash install.sh --role i2p
```

Each role is a subset of the current monolithic install:

| Role | Installs | Configs | Systemd units |
|---|---|---|---|
| `data` | redis-server, sqlite3, nginx, the dashboard venv | nginx site, sites-available, origin-auth.env | `redis-server`, `alt-bitnodes`, `nginx`, `pcap-cleanup.timer` (optional) |
| `clearnet` | crawler venv, **no tor**, **no i2pd** | `crawl.conf` with `onion=False`, `i2p=False` | `bitnodes-clearnet.service` (variant of current `bitnodes.service`) |
| `tor` | crawler venv + tor | `crawl.conf` with `onion=True`, `tor_proxies=127.0.0.1:9050`, plus `REDIS_HOST=<data-vm-ip>` | `tor`, `bitnodes-tor.service` |
| `i2p` | crawler venv + i2pd | `crawl.conf` with `i2p=True`, `i2psam=127.0.0.1:7656`, plus `REDIS_HOST=<data-vm-ip>` | `i2pd`, `bitnodes-i2p.service` |

Implementation notes:

- The current `install.sh` `setup_crawler` block becomes shared
  across all worker roles; only the `setup_*_daemon` and per-role
  service file differ.
- The crawler reads `REDIS_HOST` from `/etc/alt-bitnodes/redis.env`
  (analogous to today's `origin-auth.env`).
- The CI workflow (`deploy.yml`) iterates over the VMs in the fleet
  (a list of EC2 instance IDs / SSH targets in repo secrets) and
  runs `install.sh --role X` for each.

- _Confidence: high (pattern is straightforward Bash; analogous to the
  RHEL system roles approach we found in search but lighter-weight)._ 
- _Sources:_ [systemd unit management with RHEL system roles](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/automating_system_administration_by_using_rhel_system_roles/managing-systemd-units-by-using-the-systemd-rhel-system-role_automating-system-administration-by-using-rhel-system-roles),
  [Creating a systemd service (Linuxize)](https://linuxize.com/post/how-to-create-a-systemd-service/).

### Packaging i2pd on Ubuntu 24.04 ARM64

Two viable channels:

- **PurpleI2P PPA** (recommended, current versions):
  ```bash
  sudo add-apt-repository ppa:purplei2p/i2pd
  sudo apt-get update
  sudo apt-get install i2pd
  ```
  ARM64 builds are part of Ubuntu's first-class ARM64 archive, so
  this works on Graviton.

- **i2pd's own apt repo** (`repo.i2pd.xyz`): also viable, slightly
  more curl-pipes-to-bash style.

Recommendation: **PurpleI2P PPA**. Same trust model as adding any
PPA, and version updates flow through `apt upgrade`.

- _Confidence: high._
- _Sources:_ [i2pd install guide (read the docs)](https://docs.i2pd.website/en/latest/user-guide/install/),
  [LinuxForDevices i2pd tutorial](https://www.linuxfordevices.com/tutorials/installing-i2pd-on-linux),
  [Ubuntu 24.04 ARM64 support note](https://ubuntu.com/blog/ubuntu-pro-now-available-on-aws-graviton-instances).

### Cross-integration analysis

The patterns above are mutually reinforcing rather than independent
picks:

- SAM v3 / Tor-SOCKS analogy ↔ role split: keeps each VM's crawler
  identical except for the local proxy address.
- Redis Streams ↔ role split: makes worker failure tolerable, which
  is what justifies running workers on separate VMs in the first
  place.
- SG referencing ↔ role split: the data VM doesn't care which IPs
  the crawler VMs end up with; it just trusts whatever's tagged with
  the right SG.
- `install.sh --role` ↔ existing CI: minimal delta on the deploy
  side — we keep the `git pull && install.sh` shape, just gain a
  flag.

### Quality assessment / gaps

- We haven't measured anything yet on a real i2pd-on-Graviton —
  numbers above are extrapolations.
- We haven't audited whether the upstream `bitnodes` `crawl.py`'s I2P
  path actually opens SAM sessions or just lists addresses. Step 5.
- We haven't decided whether to use SAM 3.1 single-session-per-worker
  or 3.3 subsessions. Both work; 3.1 is simpler to start.
- We don't yet have a concrete `crawl:tor` / `crawl:i2p` stream key
  design — that's an implementation detail for the actual code
  change, not the architecture decision.

## Architectural Patterns

This is the moment to pick an actual shape. Steps 2 and 3 surfaced
options; step 4 commits to one with rationale, plus a few principles
that tell future-us how to grow it.

### What we are NOT building

Important framing first, because the easy mistake here is to
over-engineer:

- **Not microservices.** Our team is one person plus an AI agent. The
  2026 industry consensus is firm: the productivity benefits of
  microservices appear at **≥10–15 developers**; below that, the
  coordination + observability overhead outweighs the gains. We have
  no need for independent deploy autonomy of "the crawler service"
  from "the dashboard service".
- **Not serverless.** Long-lived TCP connections (Bitcoin handshake,
  pings, I2P tunnels) don't map onto Lambda. The 15-minute Lambda
  timeout alone disqualifies it for our worker model.
- **Not a distributed monolith.** Co-deploying every component on
  every push (what we have today) is exactly the anti-pattern: we
  pay distributed-system costs (Tor saturation affects dashboard)
  without the benefit (independent deploy). Step 3's role-based
  install starts to break this.

What we want is the **modular distributed monolith** for the data
plane plus a **sidecar-daemon-per-network-ring** worker fleet. In
plain English: one box owns the long-lived state and the dashboard,
the rest are interchangeable workers grouped by which anonymity
daemon they need next to them.

- _Sources for framing:_ [Microservices vs Monoliths 2026 (JCG)](https://www.javacodegeeks.com/2025/12/microservices-vs-monoliths-in-2026-when-each-architecture-wins.html),
  [Modular Monoliths Win (byteiota)](https://byteiota.com/microservices-too-expensive-modular-monoliths-win-2026/),
  [Microservices Pattern: Sidecar (microservices.io)](https://microservices.io/patterns/deployment/sidecar.html).

### Recommended target architecture: "modular split, ring-aware workers"

```
                       ┌──────────────────────────────┐
   Public clients ──▶  │  CloudFront (TLS, cache)     │
                       └─────────────┬────────────────┘
                                     │ HTTPS
                                     ▼
        ┌──────────────────────────────────────────┐
        │  VM-data  (c7g.large or .xlarge)         │
        │  ────────────────────────────────────    │
        │  nginx  ──▶  uvicorn (FastAPI dashboard) │
        │  redis-server                            │
        │  sqlite (rtt history)                    │
        │  export.py / resolve.py / seeder.py      │  ◀── role=data
        │  CloudWatch agent                        │
        └─▲────────────────────────────────────▲───┘
          │ Redis 6379 (private IP, SG-ref)    │
   ┌──────┴──────┐  ┌──────────────┐  ┌────────┴──────────┐
   │ VM-clearnet │  │ VM-tor       │  │ VM-i2p            │
   │ ─────────── │  │ ──────────── │  │ ─────────────     │
   │ crawl.py    │  │ crawl.py     │  │ crawl.py          │
   │ ping.py     │  │ ping.py      │  │ ping.py           │
   │ (no proxy)  │  │ tor sidecar  │  │ i2pd sidecar      │
   │             │  │ :9050        │  │ :7656 (SAM)       │
   └─────────────┘  └──────────────┘  └───────────────────┘
       role=clearnet    role=tor          role=i2p
```

Properties:

- **One shared data plane** (`VM-data`). It's the "monolith" of the
  whole system, owns persistent state and the public face. **Pet**.
- **Three worker VMs**, one per network ring. Each one runs the same
  Python code with a different sidecar daemon and different
  `crawl.conf`. **Cattle**: throw them away, recreate from AMI.
- **No service mesh, no API gateway, no Kubernetes.** systemd on each
  VM. CloudFront in front. Redis private over the VPC.
- **Communication is Redis Streams**, not HTTP between services.
  Workers `XREADGROUP` jobs, do the dial, `XACK`. There is no
  "worker A calling worker B" — they only talk to the data plane.

This is **not** "the optimal end-state for arbitrary scale". It's the
**right shape for one operator on one cloud**, where each piece can
later be detached if it needs to.

### Failure isolation: what gets contained, what doesn't

| Failure | Impact under monolith (today) | Impact under split (proposed) |
|---|---|---|
| Tor goes haywire | Dashboard slow, crawler stalls | Only `VM-tor` affected |
| Crawler config bug | Dashboard 500s while units restart | Crawler arm offline, dashboard fine |
| OOM on a worker | Whole box reboots | One VM reboots; others keep crawling |
| nginx upgrade | Dashboard down ~10s | Same (nginx still lives on `VM-data`) |
| Redis goes down | Everything dies | Everything dies (still a single point of failure) |

The split fixes the most painful failures we saw today (Tor saturation
hurting the dashboard, deploy restarting the crawler unnecessarily)
without introducing the heavy complexity of running Redis itself in
HA. If Redis HA becomes a need later, ElastiCache Multi-AZ swaps in
without redesigning the workers.

### Cattle/pets reasoning, applied

- **`VM-data` is a pet.** It holds sqlite (RTT history), Redis state,
  the dashboard process, ACM secrets. Snapshot the EBS volume on a
  schedule; restore is manual and rare. Resize it (we just did) when
  CPU/memory pressure shows up.
- **`VM-*` workers are cattle.** Identical AMI, `install.sh --role`
  to configure on boot, no persistent state on local disk that isn't
  reproducible from Redis or the repo. Killing one and launching
  another should leave no trace beyond a short crawl gap.

A practical consequence: terminating a worker VM should be a
one-liner (`aws ec2 terminate-instances ...`) without operational
ceremony. Recreating one should be the same plus `install.sh` flag.
If both aren't true, we're treating cattle like pets and we'll
suffer for it.

- _Sources:_ [Cattle vs Pets (Hava)](https://www.hava.io/blog/cattle-vs-pets-devops-explained),
  [Pets vs Cattle (Cloudscaling history)](https://cloudscaling.com/blog/cloud-computing/the-history-of-pets-vs-cattle/).

### Sidecar daemon, formalised

Each worker VM uses the sidecar pattern in its simplest form: one
extra long-running process on the **same host** providing a local API
on `127.0.0.1`:

- `tor` ← workers reach Bitcoin peers via `127.0.0.1:9050` (SOCKS5)
- `i2pd` ← workers reach Bitcoin peers via `127.0.0.1:7656` (SAM v3)
- (`VM-clearnet` has no sidecar; the worker connects directly)

The sidecar lives in the **same systemd cgroup boundary** as the
worker (same VM, separate units), so:

- Restarting the daemon doesn't restart the worker (and vice versa).
- The daemon binds to `127.0.0.1` only — no external attack surface.
- Resource accounting per ring is direct (`systemd-cgtop`).

This shape kept the dashboard running today even when Tor was at 95%
CPU. We just need to move the worker into its own VM so that the
"on the same host" property stops sharing CPU with `nginx` + uvicorn.

### Event-driven through Redis Streams: communication topology

```
Master (on VM-data):
  - export.py: snapshot dump every 900s
  - resolve.py: enriches new IPs with GeoIP/ASN
  - seeder.py: populates address pool from DNS seeds + addrv2 gossip
  - publishes:
      XADD crawl:clearnet * addr=<ip:port>
      XADD crawl:tor      * addr=<onion:port>
      XADD crawl:i2p      * addr=<b32:port>

Workers (per VM):
  - XREADGROUP GROUP cg-<ring>-N <consumer-id> COUNT 10 BLOCK 1000 ...
  - dial, handshake, ping
  - HSET node:<addr> ...
  - XACK crawl:<ring> cg-<ring>-N <id>
  - periodic XAUTOCLAIM min-idle-time=300000 to reclaim dead-worker jobs
```

This is a **work-stealing** pattern: any consumer in the group can
pick up a job; a janitor coroutine in each worker
`XAUTOCLAIM`s pending entries that have been idle >5 min from a
dead/slow peer.

The master is not a single process — it's a couple of long-lived
Python scripts (export, resolve, seeder) that already exist in
`bitnodes`. Each one acts as a producer on its own keys; none of them
need to know about the worker fleet's shape.

- _Sources:_ [XAUTOCLAIM docs](https://redis.io/docs/latest/commands/xautoclaim/),
  [Streams Consumer Group Patterns (antirez)](https://redis.antirez.com/fundamental/streams-consumer-patterns.html),
  [Redis Streams (Redis docs)](https://redis.io/docs/latest/develop/data-types/streams/).

### Observability across the fleet

The current setup already has the CloudWatch agent installed on the
single VM (commit `e4c09e5`). Extending it to a multi-VM fleet:

**Option A — keep CloudWatch (recommended for our scale)**

- Install the agent on every VM (already automated in `install.sh`).
- Push `cpu`, `mem`, `disk`, plus a couple of custom metrics
  (`open_sockets`, `reachable_count`) from a tiny sidecar that
  scrapes Redis once a minute.
- A single dashboard in CloudWatch with per-VM rows.
- **Cost**: pennies per VM-month at our metric volume.

**Option B — Amazon Managed Prometheus + Grafana**

- More flexible querying (PromQL, alerts).
- At our scale (~4 VMs, low-cardinality metrics): **$80+/month** for
  the managed service per the AWS calculator, which is multiples of
  the VM cost itself.
- Right answer if we ever go into the dozens of VMs or want
  histogram-style metrics. Not right today.

Pick A. Reassess at the point where the dashboard has too many
panels for CloudWatch to render comfortably, not before.

- _Sources:_ [Amazon Managed Service for Prometheus pricing](https://aws.amazon.com/prometheus/pricing/),
  [Prometheus vs CloudWatch (InfraCloud)](https://www.infracloud.io/blogs/prometheus-vs-cloudwatch/),
  [Switching CloudWatch agent → ADOT cost analysis (Medium)](https://medium.com/@karuthevar22/reducing-aws-costs-by-switching-from-cloudwatch-agent-to-adot-with-amazon-managed-prometheus-and-7b7cc42d677f).

### Migration path

Not "rip out the monolith and rebuild" — incremental, with the system
serving traffic the whole time.

1. **Step A — Add the I2P arm only** (lowest-risk path to the
   research goal).
   - New VM `VM-i2p` (t4g.large), `install.sh --role i2p`.
   - i2pd via PurpleI2P PPA. SAM bridge enabled.
   - Workers point at `127.0.0.1:7656` for proxy, at the existing
     EC2 private IP for Redis.
   - SG `alt-bitnodes-crawler` referenced from `alt-bitnodes-data:6379`.
   - The current monolith **keeps doing clearnet + Tor** unchanged.
   - Net result: I2P coverage starts appearing in snapshots; current
     numbers don't move.
2. **Step B — Extract Tor to its own VM** (medium-risk; biggest payoff
   for fault isolation).
   - New VM `VM-tor`. `install.sh --role tor`.
   - Stop `bitnodes.service` on the data VM. The data VM stops
     restarting the crawler on every deploy.
3. **Step C — Extract clearnet** (lowest payoff; only if data VM is
   still over-subscribed).
   - Mirror of step B. Data VM becomes purely "control plane +
     dashboard".

Order matters: step A is the one tied to this research; step B is the
one that actually solves the "everything restarts on every push"
operational pain. Doing A first proves the role-split machinery on a
small, low-risk component before relying on it for the Tor arm.

### Quality assessment / risks of this architecture

- **Single VPC, single AZ**: simple but no HA. Acceptable: this is a
  research project, not a 99.99% SLA. Multi-AZ Redis is a future
  step.
- **Redis SPOF**: the whole system stops if Redis crashes. Mitigation
  for now is RDB snapshots + a documented restore procedure on
  `VM-data`. Future: ElastiCache Multi-AZ if availability matters.
- **Operator burden of 4 VMs**: more SSH tabs, more `systemctl
  status` to check. Mitigated by a CloudWatch dashboard and a
  `make status` script that SSHes everyone in parallel.
- **`install.sh --role` increases script complexity**: the role
  matrix doubles the surface area to test. Mitigate by adding a
  `--dry-run` flag and one smoke test per role in CI.

### Quality assessment / what's solid

- Each architectural decision maps back to an observed problem from
  earlier in this conversation (Tor saturation, deploy-restarts-the-
  crawler, snapshot oscillation). The proposal is not theoretical.
- The shape is reversible: collapsing back to a monolith means
  re-running `install.sh` (without `--role`) on the original VM. No
  one-way doors.
- The cost delta is moderate ($244–278/mo for the split vs $196 for
  current monolith), well within the experimental budget for a
  research project of this scope.

## Implementation Research

This step does the concrete code audit promised in step 2's open
questions, then turns it into a buildable plan.

### Direct audit of `ayeowch/bitnodes` master

Clone, grep, and read. Findings, with line numbers:

**`protocol.py`** — I2P is a first-class network:

```python
NETWORK_I2P = 5                                       # line 198
NETWORK_PORT_LENGTHS = { ..., NETWORK_I2P: 32, ... }  # line 206
I2P_SUFFIX = ".b32.i2p"                               # line 213

def addr_to_i2p(addr):                                # lines 290–294
    # base32(SHA256(...)) + .b32.i2p
    return b32encode(addr).decode().replace("=", "").lower() + I2P_SUFFIX

# In deserialize_network_address(), line 743–744:
elif network_id == NETWORK_I2P:
    i2p = addr_to_i2p(addr)
```

`addrv2` payloads from peers are fully parsed into `.b32.i2p`
addresses and bubbled up through the returned dict (`"i2p": <addr>`).

**`crawl.py`** — I2P is recognised but explicitly skipped:

```python
# line 220–222, in set_pending():
# I2P and CJDNS peers are cached but not crawled.
if address.endswith(I2P_SUFFIX):
    continue

# line 563, comment in is_excluded():
# - Include I2P address                              # they're included in exports
# line 579:
if address.endswith(I2P_SUFFIX):
    return False                                     # not excluded from snapshot

# connect() at line 232, handles IPv4 / IPv6 / onion. NO i2p branch.
```

So the upstream's posture today is: **"discover and report I2P, but
don't actively dial them"**. Snapshots will list I2P addresses
gleaned from gossip, but with no `version`/`verack` data because the
crawler never connects.

**`conf/crawl.conf.default`** — has `onion`, `tor_proxies`,
`onion_peers_sampling_rate`, but **no `i2p` or `i2psam`** keys.

**`utils.py` / `connect()` proxy selection** — currently switches on
suffix:

```python
if address.endswith(ONION_SUFFIX) and CONF["onion"]:
    proxy = random.choice(CONF["tor_proxies"])
```

There is no analogous block for I2P. The connection always falls
through to a regular `gevent.socket.socket` for IPv4/IPv6.

**Conclusion**: the I2P plumbing exists down to the wire-format
parser. The missing piece is the **active SAM-v3 connect path**.
Roughly 50–150 lines of focused code.

- _Source: direct read of `ayeowch/bitnodes` master at commit fetched
  today._
- _Sources for cross-reference:_ [crawl.py (master)](https://github.com/ayeowch/bitnodes/blob/master/crawl.py),
  [crawl.conf.default](https://github.com/ayeowch/bitnodes/blob/master/conf/crawl.conf.default).

### Required code changes (concrete)

#### 1. `protocol.py` — already complete

No changes needed. `addr_to_i2p()`, `NETWORK_I2P`, and `I2P_SUFFIX`
are wired in.

#### 2. `conf/crawl.conf.default` — add config keys

```ini
# Crawl I2P peers (requires running i2pd SAM bridge).
i2p = False

# I2P SAM v3 bridge endpoint(s). Comma-separated for HA later.
i2p_proxies = 127.0.0.1:7656

# Per-circuit timeout for I2P (longer than clearnet due to tunnel RTT).
i2p_socket_timeout = 60

# Sampling rate for I2P peers (analogous to onion_peers_sampling_rate).
i2p_peers_sampling_rate = 100
```

Wire `CONF["i2p"]`, `CONF["i2p_proxies"]`, `CONF["i2p_socket_timeout"]`,
`CONF["i2p_peers_sampling_rate"]` in the existing config loader.

#### 3. `crawl.py:set_pending()` — gate the skip on config

```python
# Before:
if address.endswith(I2P_SUFFIX):
    continue

# After:
if address.endswith(I2P_SUFFIX):
    if not CONF.get("i2p"):
        continue
    # Apply sampling, analogous to onion_peers_sampling_rate
    if random.randint(0, 99) >= CONF["i2p_peers_sampling_rate"]:
        continue
```

#### 4. `crawl.py:connect()` — add I2P branch

Insert a new `address_type = "i2p"` branch alongside `onion`/`ipv4`/
`ipv6`, and dial through a SAM client:

```python
if address.endswith(ONION_SUFFIX):
    address_type = "onion"
    ...
elif address.endswith(I2P_SUFFIX):
    address_type = "i2p"
    # Pacing similar to onion: spread connections over a window
    gevent.sleep(random.uniform(0.0, 2.0) * 60 / CONF["workers"])
elif "." in address:
    address_type = "ipv4"
else:
    address_type = "ipv6"

# Proxy selection
if address_type == "onion" and CONF["onion"]:
    proxy = random.choice(CONF["tor_proxies"])
elif address_type == "i2p" and CONF["i2p"]:
    sam_endpoint = random.choice(CONF["i2p_proxies"])
    sock = sam_stream_connect(sam_endpoint, destination=address)
    # Skip the normal socks5 / direct dial path below
    return sock
```

The `sam_stream_connect()` helper is the new piece — see #5.

#### 5. New module: `sam.py` (~80 LOC)

Two options:

**Option A — vendor `leaflet`** ([MuxZeroNet/leaflet](https://github.com/MuxZeroNet/leaflet)):
synchronous, plain-socket-based, plays well with gevent's monkey-
patching. Pull as a vendored dep or `pip install leaflet`. About 200
LOC total, no async.

**Option B — write our own** (Recommended for surface-area control).
The SAM v3.1 protocol is simple enough that the client we need fits
in ~80 lines:

```python
def sam_stream_connect(endpoint, destination, timeout=60):
    """
    Open a SAM v3.1 stream to destination.b32.i2p via i2pd at endpoint.
    Returns a regular socket already connected to the I2P peer.
    """
    host, port = endpoint.split(":")
    s = gevent.socket.create_connection((host, int(port)), timeout)
    _sam_send(s, "HELLO VERSION MIN=3.1 MAX=3.3")
    _sam_expect(s, "HELLO REPLY RESULT=OK")

    nick = f"bitnodes-{uuid.uuid4().hex[:8]}"
    _sam_send(s,
        f"SESSION CREATE STYLE=STREAM ID={nick} DESTINATION=TRANSIENT")
    _sam_expect(s, "SESSION STATUS RESULT=OK")

    _sam_send(s,
        f"STREAM CONNECT ID={nick} DESTINATION={destination} SILENT=false")
    _sam_expect(s, "STREAM STATUS RESULT=OK")

    # From here, normal byte stream to the I2P peer.
    return s
```

Pros of writing it ourselves: we know exactly what's on the wire, it
doesn't drag in dependencies (i2plib pulls asyncio's whole module
tree), and it shares the gevent socket model the rest of the crawler
already uses.

Reference implementation worth reading first: the **Bitcoin Core
I2P client** ([PR #20685](https://github.com/bitcoin/bitcoin/pull/20685)),
which is the canonical, production-grade SAM-v3 client for crawling
Bitcoin nodes. Our Python port is essentially a translation of that
C++ class with gevent sockets.

- _Sources:_ [SAM V3 spec](https://i2p.net/en/docs/api/samv3/),
  [MuxZeroNet/leaflet](https://github.com/MuxZeroNet/leaflet),
  [l-n-s/i2plib](https://github.com/l-n-s/i2plib),
  [PR #20685 Bitcoin Core I2P SAM](https://github.com/bitcoin/bitcoin/pull/20685).

#### 6. `ping.py` — same treatment

`ping.py` shares the same `connect()` shape as `crawl.py`. Apply the
identical branch (or refactor into a shared helper). The latency
recorded for I2P peers should be tagged as such in Redis (`network`
field) so the dashboard can distinguish I2P RTT from clearnet RTT —
they're not comparable.

#### 7. Snapshot/export — already works

`is_excluded()` already returns `False` for I2P addresses (the
comment "Include I2P address" is intentional), and `export.py` uses
`is_excluded()` to filter the snapshot. **Once the dialler is
working, I2P peers will start appearing in the JSON snapshots
automatically with their version/services/height fields populated.**

That's the payoff: we won't need to touch the export pipeline at all.

### Effort estimate

| Task | LOC | Hours |
|---|---|---|
| New `sam.py` helper | ~80 | 3–4 |
| `crawl.py` integration | ~30 | 1 |
| `ping.py` integration | ~30 | 1 |
| Config loader updates | ~15 | 0.5 |
| Unit tests for `sam.py` (against a real i2pd) | ~50 | 2 |
| End-to-end test from `VM-i2p` to a known I2P peer | — | 1 |
| **Total** | **~205** | **~9 hours** |

Plus infra work: standing up `VM-i2p`, `install.sh --role i2p`,
Redis SG-ref, smoke tests. Probably another 3–4 hours including
debugging.

So a realistic single-engineer estimate: **~2 working days for I2P
support end-to-end**, with the architecture migration to "VM split
mode" piggy-backing on it.

### Where to do the work: fork or upstream PR?

You already maintain `ifuensan/bitnodes` (branch
`fix/empty-include-asns`). Sane path:

1. **Branch off your fork** (`feat/i2p-sam-crawl`).
2. **Implement and validate on `VM-i2p`** in production for ≥1 week.
3. **Open an upstream PR** to `ayeowch/bitnodes` once the code is
   battle-tested. The 2022 issue #64 confirms the maintainer is
   receptive in principle; landing it requires real-world data
   showing it works without destabilising clearnet/Tor crawling.
4. While the PR is open: pin `ifuensan/bitnodes@feat/i2p-sam-crawl`
   in `install.sh` (analogous to today's `fix/empty-include-asns`).

This sequencing mirrors what we already do with the
`fix/empty-include-asns` branch: ship from our fork, propose upstream
later.

### Testing strategy

- **Unit tests** with a stubbed SAM bridge over a local socket (no
  real I2P needed; tests just verify our state machine reads/writes
  the right SAM lines).
- **Integration test** against a real i2pd on `VM-i2p`, dialing a
  known-good public I2P Bitcoin peer. Smoke-test in CI by spinning
  up a temporary EC2 spot instance is overkill; doing it once per
  release on `VM-i2p` itself is enough.
- **Production validation**: monitor `crawl:i2p` stream throughput
  and the I2P node count in snapshots for the first 24h after
  enabling. Expected steady state at workers=500: a few hundred
  reachable I2P peers (the entire reachable I2P set on mainnet is
  small).

### Adoption / migration sequencing

The implementation plan slots cleanly into step 4's migration path:

1. **Code**: feature-branch on `ifuensan/bitnodes`, write SAM client,
   add config keys, wire connect path. Local tests pass.
2. **Infra**: launch `VM-i2p` with `install.sh --role i2p`, point at
   `VM-data`'s Redis. SG-ref configured.
3. **Soft launch**: deploy with `i2p = True` but
   `i2p_peers_sampling_rate = 25` so we don't hammer i2pd on first
   day. Watch metrics.
4. **Full launch**: lift sampling to 100. Verify snapshots include
   I2P entries with populated version/services.
5. **Documentation**: update `deploy/TUNING.md` with i2pd-specific
   knobs. Add a "Networks" section to `deploy/README.md`.
6. **Upstream PR**: open against `ayeowch/bitnodes` referencing
   real production metrics from week 1.

### Quality assessment / what could still go wrong

- **i2pd reseed delay**: first boot of `VM-i2p` won't have netDb
  populated. Workers might log lots of `STREAM STATUS
  RESULT=PEER_NOT_FOUND` for 5–10 min. Solution: hold off
  `bitnodes-i2p.service` start until `i2pd` reports `>=25 known
  routers` (a `systemd` `ExecStartPre` script that curls i2pd's
  status page).
- **Sybil exposure**: connecting to many I2P peers from a single
  destination is fingerprint-able. Mitigation: SAM v3.3 subsessions
  rotated periodically, or just accept it as "this is a public
  crawler".
- **`gevent.socket` + `STREAM CONNECT` blocking semantics**: SAM's
  `STREAM CONNECT` may block on the SAM socket for the full
  handshake. Confirm `gevent.socket.create_connection` monkey-patches
  cleanly so we don't block the whole greenlet pool. If it does, the
  fix is to use SAM in non-blocking mode (`SILENT=true` returns
  control faster) and poll.
- **i2pd memory on small instance**: `t4g.large` (8 GB) should be
  plenty, but measure on day 1.

### Quality assessment / what's de-risked

- Wire-format support is already done in upstream.
- SAM v3 is a stable, well-documented protocol — over 15 years old.
- Bitcoin Core's reference implementation gives us a complete
  blueprint of the connect logic.
- The change is **opt-in** (`i2p = False` by default); risk to
  existing clearnet/Tor crawling is essentially zero.

## Synthesis & Executive Summary

### The one-paragraph version

Adding I2P coverage to alt-bitnodes is **viable, modest in effort
(~2 working days), and architecturally aligned** with a split we
should be doing anyway. The upstream `ayeowch/bitnodes` already
parses I2P addresses but explicitly skips them in the crawl loop;
making it actually dial requires ~205 lines: a tiny SAM v3.1 client,
a config gate, and a branch in `connect()`. The right place to put
the new workload is a **dedicated `VM-i2p` (t4g.large)** with i2pd as
a sidecar, sharing Redis with the existing data plane, governed by a
new `install.sh --role i2p`. This unlocks I2P coverage, validates the
role-based split machinery on a low-risk component, and sets up the
larger architectural goal of extracting Tor (and later clearnet)
onto their own VMs. Total monthly cost goes from $196 to ~$244.

### Why it's worth doing

| Dimension | Argument |
|---|---|
| Coverage | Bitcoin Core has supported I2P since v22.0; the I2P node count is small but non-trivial and entirely missing from our snapshots today. |
| Architectural | A new VM for an opt-in network arm is the cheapest possible smoke-test of the role-split machinery we will need to fix the bigger Tor-on-the-same-host problem. |
| Operational | Today every deploy restarts the crawler because everything lives on one box. Splitting is a one-way improvement. |
| Effort | ~2 days for end-to-end I2P; the architectural refactor (`install.sh --role`) ships with it for free. |
| Reversible | Default is `i2p = False`; rolling back is `--role i2p` VM terminated and one config flag flipped. |

### Why it's not crucial

| Counter-argument | Response |
|---|---|
| "Only ~3% of nodes are on I2P." | True, but we have no way to know the actual count until we run. And the architectural payoff justifies the work even if the I2P arm itself yields modestly. |
| "$48/mo extra is real money." | $1.60/day. Within research-project budget. Comparable to a takeaway coffee. |
| "More VMs = more ops." | True, but CloudWatch already covers it; `install.sh --role` automates the per-VM setup; cattle-not-pets means no per-VM hand-holding. |

### Recommended sequence

Numbered in **strict order**; each step is gated by the previous one
working in production.

1. **Implement SAM v3.1 client on a branch of `ifuensan/bitnodes`.**
   ~80 LOC of `sam.py` + ~60 LOC of `connect()` integration. Unit
   tests against a local mock SAM bridge.
2. **Add `i2p`/`i2p_proxies`/`i2p_peers_sampling_rate` to
   `crawl.conf.default`.** Default off everywhere.
3. **In `alt-bitnodes`: add `install.sh --role` machinery.**
   Roles: `data` (current monolith minus crawler daemons), `tor`,
   `i2p`, `clearnet`. Maintains backward compatibility: no `--role`
   = current monolithic behaviour.
4. **Launch `VM-i2p` (t4g.large, same AZ, ARM Ubuntu 24.04, EIP not
   required since this VM doesn't terminate edge traffic).**
   `install.sh --role i2p`. i2pd via PurpleI2P PPA.
5. **Security-group reference**: open Redis port 6379 on the data VM
   from the crawler-fleet SG.
6. **Soft launch**: `i2p = True`, `i2p_peers_sampling_rate = 25` for
   first 24h. Watch CloudWatch for i2pd CPU/mem.
7. **Verify**: snapshots start including I2P entries with populated
   `version`/`services`/`height` fields.
8. **Full launch**: sampling = 100. Publish numbers.
9. **Open upstream PR** to `ayeowch/bitnodes` with real production
   metrics from week 1. Pin our fork branch in `install.sh` in the
   meantime.
10. **Later, separately**: extract Tor to `VM-tor` (the big-payoff
    step the I2P work paid for).

### Success criteria

These are the metrics we'll judge against after 7 days in production:

| Metric | Target |
|---|---|
| I2P entries in each snapshot JSON | ≥50 (gives ~1% of total visible) |
| I2P entries with `version` populated | ≥80% of dialled I2P peers |
| `VM-i2p` CPU sustained | <70% (room to grow workers) |
| `VM-i2p` memory | <60% (i2pd + Python + buffers) |
| Crawl interval impact on the data VM | none (the data VM no longer restarts on every deploy of crawler code) |
| Dashboard availability | ≥99.9% (CloudFront + caching means edge stays up even during VM-i2p churn) |

If any of these miss meaningfully, the conclusion to draw is "the
isolation is leaking" — investigate Redis contention or shared
network. None of them depend on absolute I2P count, which is outside
our control.

### Risks ranked

1. **Highest: i2pd `STREAM CONNECT` blocking semantics in gevent.**
   Mitigation: prototype the SAM client behind a feature flag first;
   measure with one worker before scaling.
2. **Medium: i2pd reseed delay** could leave us logging errors for
   5–10 min at first boot. Mitigation: `systemd ExecStartPre` that
   waits for ≥25 known routers.
3. **Medium: Redis SPOF**, made more painful by adding a VM that
   depends on it. Mitigation: schedule `BGSAVE` + EBS snapshot.
   ElastiCache Multi-AZ is the eventual fix, but not now.
4. **Low: i2pd ARM64 packaging surprises.** Mitigation: validate on
   the VM before merging the `--role i2p` PR.
5. **Low: cost overrun.** $48/mo extra is well-bounded; the only
   surprise vector is bandwidth, which is small for crawl traffic.

### What this research did NOT do

Acknowledging the boundaries so future work picks them up cleanly:

- Did not benchmark i2pd on Graviton — that's day-1-of-implementation
  work.
- Did not audit `seeder.py` or `resolve.py` for I2P assumptions —
  spot-checks suggest they're fine but a full read pass is warranted
  before flipping `i2p = True` in production.
- Did not design the actual `crawl:i2p` Redis Stream schema —
  implementation detail.
- Did not evaluate whether to publish a public I2P-reachable mirror
  of `pesquisa.hacknodes.xyz` (would require operating a hidden
  service, separate concern from crawling).
- Did not explore CJDNS or Yggdrasil — both are smaller still and
  follow the same SAM-style pattern; left for a follow-up if I2P
  goes well.

### Immediate next action

If you say "go": branch `feat/i2p-sam-crawl` on `ifuensan/bitnodes`,
draft `sam.py` against the spec, write the unit tests with a
stubbed SAM bridge, and commit. That gets us to step 1 of the
sequence in roughly 4 hours of focused work, before any AWS spend.

The rest of the plan (VM provisioning, role split, deploy) does not
need to be done first — implementing the SAM client is the only
piece that's gated by code, and it's also the riskiest.

### Citations index

All numbered claims and decisions above cite at least one URL
inline in earlier sections. Top references, grouped:

**Protocol / Bitcoin Core**

- [Bitcoin Core docs — `i2p.md`](https://github.com/bitcoin/bitcoin/blob/master/doc/i2p.md)
- [PR #19031 — BIP155 ADDRv2](https://github.com/bitcoin/bitcoin/pull/19031)
- [PR #19954 — Complete BIP155](https://github.com/bitcoin/bitcoin/pull/19954)
- [PR #20685 — Bitcoin Core I2P SAM client (reference impl)](https://github.com/bitcoin/bitcoin/pull/20685)
- [Bitcoin developer P2P reference](https://developer.bitcoin.org/reference/p2p_networking.html)
- [I2P launch on Bitcoin Core blog (geti2p)](https://geti2p.net/en/blog/post/2021/09/18/i2p-bitcoin)

**I2P daemon and SAM**

- [SAM V3 spec (geti2p)](https://i2p.net/en/docs/api/samv3/)
- [i2pd configuration docs](https://docs.i2pd.website/en/latest/user-guide/configuration/)
- [i2pd install guide](https://docs.i2pd.website/en/latest/user-guide/install/)
- [PurpleI2P/i2pd (GitHub)](https://github.com/PurpleI2P/i2pd)
- [Differences i2pd vs Java I2P](https://github.com/PurpleI2P/i2pd/wiki/Differences-between-i2pd-and-Java-I2P-router)
- [Alternative I2P clients](https://geti2p.net/en/about/alternative-clients)

**Python libraries**

- [i2plib (PyPI)](https://pypi.org/project/i2plib/) /
  [GitHub](https://github.com/l-n-s/i2plib)
- [MuxZeroNet/leaflet](https://github.com/MuxZeroNet/leaflet)
- [str4d/txi2p](https://github.com/str4d/txi2p)
- [I2P + Python asyncio tutorial](https://geti2p.net/en/blog/post/2018/10/23/application-development-basics)

**Upstream `bitnodes` (audited locally + cross-ref)**

- [ayeowch/bitnodes](https://github.com/ayeowch/bitnodes)
- [crawl.py master](https://github.com/ayeowch/bitnodes/blob/master/crawl.py)
- [Add support for multiple networks (commit)](https://github.com/ayeowch/bitnodes/commit/5e7202910d59ab910dd2291a8def9be0d3604827)
- [Issue #64 — Bitnodes mirrored via Onion or I2P?](https://github.com/ayeowch/bitnodes/issues/64)
- [Bitnodes provisioning wiki](https://github.com/ayeowch/bitnodes/wiki/Provisioning-Bitcoin-Network-Crawler)

**Architecture, Redis, AWS**

- [Monolith vs Microservices in 2026 (JCG)](https://www.javacodegeeks.com/2025/12/microservices-vs-monoliths-in-2026-when-each-architecture-wins.html)
- [Modular Monoliths Win 2026 (byteiota)](https://byteiota.com/microservices-too-expensive-modular-monoliths-win-2026/)
- [Microservices Pattern: Sidecar](https://microservices.io/patterns/deployment/sidecar.html)
- [Redis Streams (docs)](https://redis.io/docs/latest/develop/data-types/streams/)
- [XAUTOCLAIM (docs)](https://redis.io/docs/latest/commands/xautoclaim/)
- [Streams Consumer Group Patterns (antirez)](https://redis.antirez.com/fundamental/streams-consumer-patterns.html)
- [Cattle vs Pets (Hava)](https://www.hava.io/blog/cattle-vs-pets-devops-explained)
- [Security group rules (VPC user guide)](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
- [ElastiCache VPC access patterns](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/elasticache-vpc-accessing.html)
- [Prometheus vs CloudWatch (InfraCloud)](https://www.infracloud.io/blogs/prometheus-vs-cloudwatch/)
- [Amazon Managed Service for Prometheus pricing](https://aws.amazon.com/prometheus/pricing/)

---

_End of research document. Generated through BMad
`bmad-technical-research` workflow, 2026-05-13._
