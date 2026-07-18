# Add I2P crawling (fourth network ring)

## Why

The observatory now covers IPv4 (complete, ~6.5k), IPv6 (ramping since
2026-07-17), and onion (~5k) — but zero I2P, the last network Bitcoin nodes
reach each other on. The crawler fork just gained an active SAM v3 dial path
(`ifuensan/bitnodes@feat/i2p-sam-crawl`, minimum-viable same-host variant of
the May research); what remains is deploying it: an i2pd router on the host
and the config to switch the feature on.

## What Changes

- `install.sh` installs `i2pd` from the PurpleI2P PPA, enables the service,
  and warns (without failing the deploy) if the SAM bridge doesn't come up.
- `install.sh` gains an idempotent `ensure_conf_key` helper to set-or-append
  crawler conf keys — the existing `.f9beb4d9.conf` files on the host predate
  the new `i2p*` keys, so plain seds would not match.
- Crawl conf gets `i2p = True`, `i2p_proxies = 127.0.0.1:7656`,
  `i2p_peers_sampling_rate = 100`; ping conf gets `i2p = True` and the proxy.
- `CRAWLER_BRANCH` switches from `fix/empty-include-asns` to
  `feat/i2p-sam-crawl` (which contains it).

## Capabilities

### New Capabilities
- `i2p-crawling`: the deployment's contract for `.b32.i2p` node coverage —
  i2pd router provisioned with SAM on localhost, crawler branch with the SAM
  dial path, conf keys enabling full-sampling I2P crawl, graceful degradation
  when the bridge is down.

### Modified Capabilities

<!-- none -->

## Impact

- `deploy/install.sh` only; crawler code changes live in the fork.
- Production: one new apt repo (PPA) + `i2pd` service (~50–150 MB RAM).
- Expected yield is modest (reachable I2P set is a few hundred nodes); the
  value is ring completeness, the Delving Bitcoin write-up, and maturing the
  branch toward an upstream PR (ayeowch/bitnodes#64).
- Degradation path: if i2pd/SAM is down, I2P dials fail as ordinary
  connection errors (logged debug) — clearnet/Tor crawling unaffected.
