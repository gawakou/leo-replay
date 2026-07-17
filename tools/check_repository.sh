#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
python3 -m compileall -q src scripts dashboard tests
bash -n scripts/orchestration/run_experiment.sh
bash -n scripts/orchestration/run_batch_profile.sh
pytest
if grep -RInE --exclude-dir=.git --exclude-dir=legacy --exclude-dir=tests --exclude-dir=tools --exclude='*.md' \
  '(/home/ogawa|192\.168\.1\.2|192\.168\.2\.2|debug=True)' .; then
  echo '[ERROR] environment-specific value found outside legacy/docs' >&2
  exit 1
fi
echo '[OK] repository checks passed'
