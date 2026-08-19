#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="docker"
REPETITIONS=30
OUTPUT_ROOT="${REPOSITORY_ROOT}/evaluation-results"

usage() {
    cat <<'EOF'
Usage: experiments/run_repeated_lab.sh [options]

Options:
  --backend docker|netns   Lab backend (default: docker)
  --repetitions N          Number of repeated runs (default: 30)
  --output DIR             Output root (default: evaluation-results)
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)
            BACKEND="$2"
            shift 2
            ;;
        --repetitions)
            REPETITIONS="$2"
            shift 2
            ;;
        --output)
            OUTPUT_ROOT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "${BACKEND}" != "docker" && "${BACKEND}" != "netns" ]]; then
    printf 'unsupported backend: %s\n' "${BACKEND}" >&2
    exit 2
fi
if ! [[ "${REPETITIONS}" =~ ^[1-9][0-9]*$ ]]; then
    printf 'repetitions must be a positive integer: %s\n' "${REPETITIONS}" >&2
    exit 2
fi

if [[ "${OUTPUT_ROOT}" != /* ]]; then
    OUTPUT_ROOT="${REPOSITORY_ROOT}/${OUTPUT_ROOT}"
fi
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESULT_DIR="${OUTPUT_ROOT}/${BACKEND}-${TIMESTAMP}"
mkdir -p "${RESULT_DIR}"

if [[ "${BACKEND}" == "docker" ]]; then
    LAB_DIR="${REPOSITORY_ROOT}/labs/docker-bidirectional"
    FIXED_CMD=(bash "${LAB_DIR}/run-fixed-condition-test.sh")
    PROFILE_CMD=(bash "${LAB_DIR}/run-profile-test.sh")
    CLEANUP_CMD=(bash "${LAB_DIR}/cleanup.sh")
else
    LAB_DIR="${REPOSITORY_ROOT}/labs/netns-bidirectional"
    FIXED_CMD=(sudo bash "${LAB_DIR}/run-fixed-condition-test.sh")
    PROFILE_CMD=(sudo bash "${LAB_DIR}/run-profile-test.sh")
    CLEANUP_CMD=(sudo bash "${LAB_DIR}/cleanup.sh")
fi
ARTIFACT_DIR="${LAB_DIR}/artifacts"

cleanup() {
    "${CLEANUP_CMD[@]}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

{
    printf 'collected_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'backend=%s\n' "${BACKEND}"
    printf 'repetitions=%s\n' "${REPETITIONS}"
    printf 'git_commit=%s\n' "$(git -C "${REPOSITORY_ROOT}" rev-parse HEAD 2>/dev/null || printf unknown)"
    printf 'uname=%s\n' "$(uname -a)"
    printf 'python=%s\n' "$(python3 --version 2>&1)"
} > "${RESULT_DIR}/environment.txt"

for ((run = 1; run <= REPETITIONS; run++)); do
    RUN_DIR="$(printf '%s/run-%03d' "${RESULT_DIR}" "${run}")"
    mkdir -p "${RUN_DIR}"
    printf '[%03d/%03d] fixed-condition\n' "${run}" "${REPETITIONS}"
    "${FIXED_CMD[@]}"
    cp "${ARTIFACT_DIR}/fixed-summary.json" "${RUN_DIR}/fixed-summary.json"

    printf '[%03d/%03d] directional-profile\n' "${run}" "${REPETITIONS}"
    "${PROFILE_CMD[@]}"
    cp "${ARTIFACT_DIR}/profile-summary.json" "${RUN_DIR}/profile-summary.json"
    cp "${ARTIFACT_DIR}/profile-execution.jsonl" "${RUN_DIR}/profile-execution.jsonl"
done

PYTHONPATH="${REPOSITORY_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 "${REPOSITORY_ROOT}/experiments/summarize_lab_runs.py" \
    --input "${RESULT_DIR}" \
    --output "${RESULT_DIR}/summary.json" \
    > "${RESULT_DIR}/summary.stdout.json"

PYTHONPATH="${REPOSITORY_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m leo_replay.evaluation_manifest create "${RESULT_DIR}" \
    > /dev/null

printf 'Evaluation finished: %s\n' "${RESULT_DIR}"
printf 'Summary: %s\n' "${RESULT_DIR}/summary.json"
printf 'Integrity manifest: %s\n' "${RESULT_DIR}/evaluation-manifest.json"
