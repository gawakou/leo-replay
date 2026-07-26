# GitHub update: v0.4.2

Recommended branch:

```text
feature/historical-element-selection-v0.4.2
```

Recommended commit:

```text
feat: add causal and retrospective element selection for v0.4.2
```

Pull request title:

```text
Add causal and retrospective historical element selection for v0.4.2
```

Validation checklist:

- `leo-replay --version` reports `0.4.2`.
- `make check` passes.
- `leo-replay orbit select-elements --help` succeeds.
- causal mode excludes records created after the observation cutoff.
- retrospective mode chooses the minimum epoch-distance record.
- compare mode records propagated position differences and sub-satellite coordinates.
- verified v0.4.1 snapshot directories are accepted.
- Docker fixed-condition and profile replay tests still pass.
