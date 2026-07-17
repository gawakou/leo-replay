# Research continuity

The current paper establishes the following line:

```text
continuous Starlink measurement
→ common-timeline profile generation
→ tc/netem replay
→ measured/replayed comparison
```

The repository preserves that axis. The implementation roadmap is:

| Version | Research step | Status |
|---|---|---|
| v0.1.0 | Time-series profile generation and replay baseline | Completed |
| v0.2.0 | Formalized event profile, event replay, timing and event-window evaluation | Completed |
| v0.3.0 | Bidirectional replay and direction-specific profiles | Completed |
| v0.4.0 | OMM/TLE visibility synchronization and candidate handover display | Planned |
| v0.5.0 | Path switching and handover communication reproduction | Planned |
| v0.6.0 | TCP, QUIC and MPTCP comparison under identical measured scenarios | Planned |

v0.2.0 addressed short-duration fluctuations and event-unit replay. v0.3.0 addresses the paper's explicit single-root-netem and one-way-control limitation. It also separates measured legacy path values from derived directional conditions by recording the directionalization policy.

The next version should add OMM/TLE time synchronization as explanatory context for measured and replayed events. It should not claim that a visible-satellite candidate is the actually connected satellite unless an independent observation supports that conclusion.
