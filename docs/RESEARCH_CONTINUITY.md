# Research continuity

The current paper establishes the following line:

```text
continuous Starlink measurement
→ common-timeline profile generation
→ tc/netem replay
→ measured/replayed comparison
```

The repository preserves that axis. New functions should be added in this order:

1. Stabilize the current profile replay and establish regression tests.
2. Compare time-series replay with event-based replay.
3. Improve short-duration event reproduction and bidirectional replay.
4. Synchronize detected events with OMM/TLE-derived visibility information.
5. Add path-switch and handover models.
6. Use the same replay conditions to compare TCP, QUIC, and MPTCP controls.

OMM/TLE visualization, routing, and satellite reception models should therefore be implemented as extensions of the measurement-driven replay model, not as an unrelated model-only simulator.
