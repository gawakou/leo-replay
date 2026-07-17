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
| v0.3.0 | Bidirectional replay and direction-specific profiles | Planned |
| v0.4.0 | OMM/TLE visibility synchronization and candidate handover display | Planned |
| v0.5.0 | Path switching and handover communication reproduction | Planned |
| v0.6.0 | TCP, QUIC and MPTCP comparison under identical measured scenarios | Planned |

v0.2.0 directly addresses the paper's remaining issues: short-duration fluctuations, event-unit replay, and the comparison between waveform-level and event-level reproduction.

OMM/TLE visualization, routing and satellite reception models should therefore be implemented as extensions of the measurement-driven replay model, not as an unrelated model-only simulator.
