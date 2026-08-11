## 1. Proxy affinity in the fork (`ifuensan/bitnodes`)

- [x] 1.1 Add a shared stable-hash proxy chooser (sha256 of the address
      reduced mod pool size) usable from both `crawl.py` and `ping.py`
- [x] 1.2 Use it for onion dials in `crawl.py`, gated on `tor_proxy_affinity`
- [x] 1.3 Use it for onion dials in `ping.py`, gated on the same key
- [x] 1.4 Add `tor_proxy_affinity = True` to `conf/crawl.conf.default` and
      `conf/ping.conf.default`, with a comment stating why affinity exists
- [x] 1.5 Tests: same address → same proxy across processes (no
      `PYTHONHASHSEED` dependence), distinct addresses spread over the pool,
      `crawl` and `ping` agree on the same address, and the flag disables it

## 2. Measurement scaffolding (this repo)

- [x] 2.1 `IPAccounting=yes` drop-in for the `tor@` template unit — written
      inline by `install.sh`, not copied from the repo: `setup_tor_pool` runs
      before `setup_dashboard` clones it, so a fresh install would abort
- [x] 2.2 `install.sh`: `HeartbeatPeriod 900` for every instance, and
      `TOR_DIRTINESS_ARM` / `TOR_DIRTINESS_VALUE` writing
      `MaxCircuitDirtiness` only for the named instances, preserving the
      per-instance byte comparison that avoids needless restarts
- [x] 2.3 `install.sh`: set `tor_proxy_affinity` in the generated crawler
      confs via `ensure_conf_key`
- [x] 2.4 `deploy/tor-experiment-sample.sh`: append one CSV row per minute
      per instance — timestamp, instance, `IPEgressBytes`, established
      connections on its SocksPort — plus the current snapshot's onion count

## 3. Run the experiment

- [ ] 3.1 Deploy deliberately (this restarts the whole Tor pool) with the
      split already in place, `i2p = False`, and the sampler running
- [ ] 3.2 Let it run ~24h; confirm both arms reach their plateau
- [ ] 3.3 Compare post-plateau egress **per carried connection** per arm,
      handshake counters from the heartbeat lines, and check the global onion
      count did not drop
- [ ] 3.4 Watch Tor memory and whether `MaxClientCircuitsPending 512` starts
      limiting the treated arm

## 4. Close the loop

- [ ] 4.1 Record the numbers in `docs/follow-ups.md` (or a postmortem-style
      note if the result is surprising enough to deserve one)
- [ ] 4.2 Decide the end state: keep a longer `MaxCircuitDirtiness`, or tune
      the revisit cadence below the dirtiness window instead
- [ ] 4.3 Reply to b10c in the BNOC thread with the measurement — the lead
      came from there
- [ ] 4.4 Note in `docs/follow-ups.md` the latent `hash()` non-determinism in
      the onion/I2P sampling rate (inert at rate 100, wrong if ever lowered)
- [ ] 4.5 Sync specs and archive this change
