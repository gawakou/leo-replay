\
#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="leo-replay-$(date +%Y%m%d-%H%M%S)"
OUT="${ROOT}/../${NAME}.tar.gz"
tar -C "${ROOT}/.." \
  --exclude='.git' --exclude='.venv' --exclude='experiments' \
  --exclude='*/config/experiment.env' --exclude='*/config/batch-profile.env' \
  -czf "${OUT}" "$(basename "${ROOT}")"
echo "${OUT}"
