# GitHub update: v0.4.1

Suggested branch:

```text
feature/orbit-snapshot-acquisition-v0.4.1
```

Suggested commit:

```text
feat: add reproducible orbit snapshot acquisition for v0.4.1
```

Suggested pull request title:

```text
Add CelesTrak and Space-Track orbit snapshot acquisition for v0.4.1
```

Validation checklist:

- `leo-replay --version` reports 0.4.1.
- `make check` passes.
- Offline snapshot acquisition unit tests pass.
- CelesTrak one-object live smoke test passes.
- Space-Track authenticated smoke test is performed locally when credentials are available.
- Existing Docker bidirectional tests pass.
- No credentials or generated snapshots are staged.
