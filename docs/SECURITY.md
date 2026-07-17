# Security and data handling

Do not commit:

- `config/experiment.env` or `config/batch-profile.env`
- SSH private keys or tokens
- shell history
- public/private IP inventories beyond anonymized examples
- Starlink terminal identifiers
- raw institutional network traces
- generated experiment directories

`tc/netem` changes live network behavior. Run dry-run checks first and keep an out-of-band recovery path.

Before making the repository public, review `git log --all -p` as well as the current tree; deleting a secret from the latest commit does not remove it from earlier commits.
