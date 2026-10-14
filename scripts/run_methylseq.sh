#!/usr/bin/env bash
# Run nf-core/methylseq with pinned pipeline and Nextflow versions.
# Usage: scripts/run_methylseq.sh <run-profile> <params-file>
#   e.g. scripts/run_methylseq.sh test config/methylseq/test.yaml
set -euo pipefail

# 25.04.0 is the version methylseq 4.2.0's CI must pass on. Newer Nextflow
# rejects the 4.2.0 config: it includes conf/aws/batch/nextflow.config,
# which is missing from the release tag.
export NXF_VER=25.04.0
PIPELINE_VERSION=4.2.0

# emulate_amd64 runs the standard x86_64 containers on Apple Silicon;
# it is a no-op on x86_64 hosts.
nextflow run nf-core/methylseq \
  -r "$PIPELINE_VERSION" \
  -profile "$1,docker,emulate_amd64" \
  -params-file "$2"
