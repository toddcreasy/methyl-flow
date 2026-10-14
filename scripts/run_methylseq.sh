#!/usr/bin/env bash
# Launch pinned nf-core/methylseq on the chosen compute.
#
#   scripts/run_methylseq.sh <params-file> [--compute local|slurm|aws] [--run-id <id>] [extra nextflow args]
#
# Each run gets a run ID (<params file name>_<YYYYMMDD-HHMMSS>) used as the Nextflow
# run name and the output folder: results/methylseq/<run ID>/. Pass --run-id to
# resume that run into the same folder.
#
# Compute defaults to local Docker (COMPUTE in .env overrides it).
#
# Examples:
#   scripts/run_methylseq.sh config/methylseq/test.yaml
#   scripts/run_methylseq.sh config/methylseq/gse95654.yaml
#   scripts/run_methylseq.sh config/methylseq/gse95654.yaml --compute aws
#   scripts/run_methylseq.sh config/methylseq/gse95654.yaml --run-id gse95654_20261014-150000

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

[[ $# -ge 1 ]] || usage
PARAMS_FILE="$1"; shift

if [[ -f "$ROOT/.env" ]]; then
    set -a; source "$ROOT/.env"; set +a
fi

COMPUTE="${COMPUTE:-local}"
RUN_ID=""
EXTRA=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --compute) COMPUTE="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        *) EXTRA+=("$1"); shift ;;
    esac
done

# 25.04.0 is the version methylseq 4.2.0's CI must pass on. Newer Nextflow
# rejects the 4.2.0 config: it includes conf/aws/batch/nextflow.config,
# which is missing from the release tag.
export NXF_VER=25.04.0
REPO=nf-core/methylseq
VERSION=4.2.0

[[ -f "$PARAMS_FILE" ]] || { echo "Params file not found: $PARAMS_FILE" >&2; exit 1; }

require() {
    for var in "$@"; do
        [[ -n "${!var:-}" ]] || { echo "$var must be set in .env for --compute $COMPUTE" >&2; exit 1; }
    done
}

RESULTS_BASE="$ROOT/results"
case "$COMPUTE" in
    local) ;;
    slurm) require SLURM_QUEUE ;;
    aws)
        require AWS_BATCH_QUEUE AWS_S3_WORKDIR AWS_S3_OUTDIR
        RESULTS_BASE="${AWS_S3_OUTDIR%/}"
        aws sts get-caller-identity >/dev/null || { echo "No valid AWS credentials. Run: aws sso login" >&2; exit 1; }
        ;;
    *) echo "Unknown compute: $COMPUTE (use local, slurm, or aws)" >&2; exit 1 ;;
esac

# A test params file selects the pipeline's bundled test profile for data and references.
PROFILE="$COMPUTE"
CONFIGS=(-c "$ROOT/config/methylseq/compute.config")
if [[ "$(basename "$PARAMS_FILE")" == test.yaml ]]; then
    PROFILE="test,$COMPUTE"
    # compute.config limits would otherwise override the test profile's small caps
    if [[ "$COMPUTE" != local ]]; then
        CONFIGS+=(-c "$ROOT/config/methylseq/test-limits.config")
    fi
fi

# Separate resume cache per compute, so -resume never reuses task results
# produced on a different executor (e.g. local work/ dirs during an AWS run).
export NXF_CACHE_DIR="$ROOT/.nextflow/cache-$COMPUTE"
# Keep nextflow.log and its rotated copies (.1, .2, ...) out of the repo root.
export NXF_LOG_FILE="$ROOT/logs/methylseq/nextflow.log"

# Run IDs double as Nextflow run names, which must be lowercase letters, digits, - or _
STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$RUN_ID" ]]; then
    STEM="$(basename "$PARAMS_FILE")"
    STEM="$(echo "${STEM%.*}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^[^a-z]+//; s/_+$//')"
    RUN_ID="${STEM:-run}_$STAMP"
    RUN_NAME="$RUN_ID"
    # Resume the latest methylseq session, so tasks with identical inputs
    # (e.g. a staged genome index) are reused across runs.
    SESSION_ID="$( (nextflow log 2>/dev/null || true) | awk -F'\t' -v cmd="nextflow run $REPO " 'index($7, cmd) {s = $6} END {gsub(/ /, "", s); print s}')"
    RESUME=()
    [[ -n "$SESSION_ID" ]] && RESUME=(-resume "$SESSION_ID")
else
    # -resume needs the session ID; it silently ignores an unknown run name
    SESSION_ID="$( (nextflow log 2>/dev/null || true) | awk -F'\t' -v n="$RUN_ID" '{gsub(/ +$/, "", $3)} $3 == n {gsub(/ /, "", $6); print $6; exit}')"
    [[ -n "$SESSION_ID" ]] || { echo "No $COMPUTE run named '$RUN_ID'. See: NXF_CACHE_DIR=$NXF_CACHE_DIR nextflow log" >&2; exit 1; }
    RUN_NAME="${RUN_ID}_r$STAMP"
    RESUME=(-resume "$SESSION_ID")
fi
OUTDIR="$RESULTS_BASE/methylseq/$RUN_ID"
echo "Run ID: $RUN_ID  (output: $OUTDIR)"

set -x
nextflow run "$REPO" \
    -r "$VERSION" \
    -name "$RUN_NAME" \
    -profile "$PROFILE" \
    "${CONFIGS[@]}" \
    -params-file "$PARAMS_FILE" \
    --outdir "$OUTDIR" \
    ${RESUME[@]+"${RESUME[@]}"} \
    ${EXTRA[@]+"${EXTRA[@]}"}
