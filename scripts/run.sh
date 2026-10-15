#!/usr/bin/env bash
# Launch a pinned pipeline on the chosen compute.
#
#   scripts/run.sh <pipeline> <params-file> [--compute aws|local|slurm] [--run-id <id>] [--resume <session-id>] [extra nextflow args]
#
# Pipelines: methylseq (nf-core/methylseq 4.2.0), fetch_sra (pipelines/fetch_sra).
# Each run gets a run ID (<params file name>_<YYYYMMDD-HHMMSS>) used as the Nextflow
# run name and the output folder: <results>/<pipeline>/<run ID>/.
#
# Compute defaults to AWS (COMPUTE in .env overrides it). On AWS the Nextflow head
# process runs as a Batch job, so this script only uploads config and submits.
#
# Examples:
#   scripts/run.sh fetch_sra config/fetch_sra/gse95654.yaml
#   scripts/run.sh methylseq config/methylseq/gse95654.yaml
#   scripts/run.sh methylseq config/methylseq/test.yaml
#   scripts/run.sh methylseq config/methylseq/gse95654.yaml --resume <session-id>

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() { sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

[[ $# -ge 2 ]] || usage
PIPELINE="$1"; PARAMS_FILE="$2"; shift 2

if [[ -f "$ROOT/.env" ]]; then
    set -a; source "$ROOT/.env"; set +a
fi

COMPUTE="${COMPUTE:-aws}"
RUN_ID=""
SESSION=""
EXTRA=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --compute) COMPUTE="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        --resume) SESSION="$2"; shift 2 ;;
        *) EXTRA+=("$1"); shift ;;
    esac
done

# 25.04.0 is the version methylseq 4.2.0's CI must pass on. Newer Nextflow
# rejects the 4.2.0 config: it includes conf/aws/batch/nextflow.config,
# which is missing from the release tag. The AWS head job image is pinned to match.
export NXF_VER=25.04.0

case "$PIPELINE" in
    methylseq) REPO=nf-core/methylseq; REVISION=(-r 4.2.0) ;;
    # This repo's own pipeline, run from its folder at the checked-out commit
    fetch_sra) REPO=pipelines/fetch_sra; REVISION=() ;;
    *) echo "Unknown pipeline: $PIPELINE (use methylseq or fetch_sra)" >&2; exit 1 ;;
esac

[[ -f "$PARAMS_FILE" ]] || { echo "Params file not found: $PARAMS_FILE" >&2; exit 1; }
PARAMS_FILE="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1]))' "$PARAMS_FILE")"

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
        require BATCH_QUEUE AWS_HEAD_QUEUE AWS_HEAD_JOB_DEFINITION AWS_S3_WORKDIR AWS_S3_OUTDIR AWS_S3_RUNDIR
        RESULTS_BASE="${AWS_S3_OUTDIR%/}"
        aws sts get-caller-identity >/dev/null || { echo "No valid AWS credentials. Run: aws sso login" >&2; exit 1; }
        ;;
    *) echo "Unknown compute: $COMPUTE (use aws, local, or slurm)" >&2; exit 1 ;;
esac

# A test params file selects the pipeline's bundled test profile for data and references.
PROFILE="$COMPUTE"
CONFIGS=(-c config/compute.config)
if [[ "$(basename "$PARAMS_FILE")" == test.yaml ]]; then
    PROFILE="test,$COMPUTE"
    # compute.config limits would otherwise override the test profile's small caps
    if [[ "$COMPUTE" != local ]]; then
        CONFIGS+=(-c config/test-limits.config)
    fi
fi

# Run IDs double as Nextflow run names, which must be lowercase letters, digits, - or _
STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$RUN_ID" ]]; then
    STEM="$(basename "$PARAMS_FILE")"
    STEM="$(echo "${STEM%.*}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^[^a-z]+//; s/_+$//')"
    RUN_ID="${PIPELINE}_${STEM:-run}_$STAMP"
    RUN_NAME="$RUN_ID"
else
    RUN_NAME="${RUN_ID}_r$STAMP"
fi
OUTDIR="$RESULTS_BASE/$PIPELINE/$RUN_ID"

RESUME=()
[[ -n "$SESSION" ]] && RESUME=(-resume "$SESSION")

# Stream the run to Seqera Platform when a token is set. Locally Nextflow reads it from
# TOWER_ACCESS_TOKEN in .env; on AWS the head job gets it from Secrets Manager.
TOWER=()
[[ -n "${TOWER_ACCESS_TOKEN:-}" ]] && TOWER=(-with-tower)

NF_ARGS=(
    run "$REPO" ${REVISION[@]+"${REVISION[@]}"}
    -name "$RUN_NAME"
    -profile "$PROFILE"
    "${CONFIGS[@]}"
    -params-file "$PARAMS_FILE"
    --outdir "$OUTDIR"
    ${TOWER[@]+"${TOWER[@]}"}
    ${RESUME[@]+"${RESUME[@]}"}
    ${EXTRA[@]+"${EXTRA[@]}"}
)

mkdir -p "$ROOT/logs/$PIPELINE"
echo "Run ID: $RUN_ID  (output: $OUTDIR)"

if [[ "$COMPUTE" != aws ]]; then
    # Separate resume cache per compute, so -resume never reuses results from another executor
    export NXF_CACHE_DIR="$ROOT/.nextflow/cache-$COMPUTE"
    export NXF_LOG_FILE="$ROOT/logs/$PIPELINE/nextflow.log"
    # Console output goes to the terminal and to logs/<pipeline>/<run name>.console.log
    exec > >(tee -a "$ROOT/logs/$PIPELINE/$RUN_NAME.console.log") 2>&1
    set -x
    nextflow "${NF_ARGS[@]}"
    exit
fi

# --- AWS: upload config and pipelines, then submit the head job ----------------------
BUNDLE="${AWS_S3_RUNDIR%/}/$RUN_NAME"
FILES=()
while IFS= read -r f; do FILES+=("$f"); done < <(find config pipelines -type f -not -name ".*" | sort)
for f in "${FILES[@]}"; do
    aws s3 cp "$f" "$BUNDLE/$f" --only-show-errors
done

# The head script runs in the nextflow/nextflow image. Its entrypoint wraps arguments in
# single quotes, so the script is passed base64-encoded to keep quoting out of the way.
HEAD_SCRIPT="set -euo pipefail
mkdir -p /run-head && cd /run-head
$(for f in "${FILES[@]}"; do printf 'mkdir -p %q && nextflow fs cp %q %q\n' "$(dirname "$f")" "$BUNDLE/$f" "$f"; done)
rc=0; nextflow $(printf '%q ' "${NF_ARGS[@]}") || rc=\$?
nextflow fs cp .nextflow.log $(printf '%q' "$BUNDLE/nextflow.log") || true
exit \$rc"
HEAD_B64="$(printf '%s' "$HEAD_SCRIPT" | base64 | tr -d '\n')"

OVERRIDES="$(HEAD_B64="$HEAD_B64" python3 -c '
import json, os
env = {k: os.environ[k] for k in (
    "AWS_REGION", "BATCH_QUEUE", "AWS_S3_WORKDIR", "BATCH_CLI_PATH",
    "AWS_MAX_CPUS", "AWS_MAX_MEMORY") if os.environ.get(k)}
env["NXF_CLOUDCACHE_PATH"] = os.environ["AWS_S3_RUNDIR"].rstrip("/") + "/cache"
# A fresh head container has no local run history; resume from the cloud cache instead
env["NXF_IGNORE_RESUME_HISTORY"] = "true"
print(json.dumps({
    "command": ["bash", "-c", "echo " + os.environ["HEAD_B64"] + " | base64 -d | bash"],
    "environment": [{"name": k, "value": v} for k, v in env.items()],
}))')"

JOB_ID="$(aws batch submit-job \
    --job-name "$RUN_NAME" \
    --job-queue "$AWS_HEAD_QUEUE" \
    --job-definition "$AWS_HEAD_JOB_DEFINITION" \
    --container-overrides "$OVERRIDES" \
    --tags "project=methyl-flow,pipeline=$PIPELINE,run=$RUN_NAME" \
    --propagate-tags \
    --query jobId --output text)"

cat <<EOF | tee "$ROOT/logs/$PIPELINE/$RUN_NAME.submit.log"
Submitted head job $JOB_ID ($RUN_NAME) to $AWS_HEAD_QUEUE
Config bundle: $BUNDLE/
Watch: Seqera Platform (https://cloud.seqera.io) if the token secret is set, or
  aws batch describe-jobs --jobs $JOB_ID --query 'jobs[0].[status,statusReason]' --output text
  aws logs tail /aws/batch/job --follow --log-stream-name-prefix methyl-flow-nextflow-head
EOF
