#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
if [[ ! -d .git ]]; then git init -b main; fi
git status --short
cat <<'EOF'
Next steps:
  git config user.name "Your Name"
  git config user.email "your-github-email"
  git add .
  git commit -m "chore: import organized LEO replay prototype"
  git remote add origin git@github.com:YOUR_ACCOUNT/leo-replay.git
  git push -u origin main
EOF
