# GitHub setup

## Recommended initial policy

Create an empty **private** repository named `leo-replay`. Do not add a README, `.gitignore`, or license in the GitHub creation screen because this directory already contains them.

## First registration

```bash
cd leo-replay
git init -b main
git config user.name "Your Name"
git config user.email "your-github-email"
git add .
git commit -m "chore: import organized LEO replay prototype"
git remote add origin git@github.com:YOUR_ACCOUNT/leo-replay.git
git push -u origin main
```

HTTPS remote alternative:

```bash
git remote add origin https://github.com/YOUR_ACCOUNT/leo-replay.git
```

## Day-to-day workflow

```bash
git switch -c feature/bidirectional-replay
# edit and test
make check
git add .
git commit -m "feat: add bidirectional replay skeleton"
git push -u origin feature/bidirectional-replay
```

Use issues for experiments and defects, and tags for reproducible research states, for example `v0.1.0` for this organized baseline.

## Before every push

```bash
make check
git status --short
git diff --cached
```
