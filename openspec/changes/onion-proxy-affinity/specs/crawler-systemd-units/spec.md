## ADDED Requirements

### Requirement: Tor instances account for their own egress

The installer SHALL install a drop-in for the `tor@` template unit enabling
`IPAccounting=yes`, so every pool instance exposes its own cumulative
`IPEgressBytes` and `IPIngressBytes` via `systemctl show`. Per-instance
accounting is what makes an A/B comparison between daemons possible without
sampling; the sampling method used previously (paired `ss -tinp` snapshots)
loses connections that begin and end between samples, which under this
workload is most of them.

#### Scenario: A pool instance reports its egress
- **WHEN** `systemctl show tor@bitnodes1 -p IPEgressBytes` is run on a
  deployed host
- **THEN** it returns a monotonically increasing byte count for that instance
  alone

### Requirement: The installer can give part of the pool a different circuit lifetime

`install.sh` SHALL support a `TOR_DIRTINESS_ARM` variable naming the pool
instances that receive a non-default `MaxCircuitDirtiness`, so two circuit
lifetimes can run side by side in one pool. Instances outside the arm keep
Tor's default. The generated torrc SHALL remain byte-comparable per instance,
preserving the existing rule that a deploy restarts a Tor instance only when
its own configuration actually changed. All instances SHALL receive a
`HeartbeatPeriod` short enough for per-instance handshake counters to be read
from the journal during an experiment.

#### Scenario: Half the pool runs a longer circuit lifetime
- **WHEN** `TOR_DIRTINESS_ARM` names instances 1-4 with a value of 3600
- **THEN** those instances' torrc contain `MaxCircuitDirtiness 3600` and the
  remaining instances contain no `MaxCircuitDirtiness` line

#### Scenario: Re-running the installer does not restart unchanged instances
- **WHEN** `install.sh` runs twice with the same `TOR_DIRTINESS_ARM`
- **THEN** no Tor instance is restarted by the second run
