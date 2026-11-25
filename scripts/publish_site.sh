#!/usr/bin/env bash
# Build the public results site and publish it to the site bucket behind CloudFront.
#
#   scripts/publish_site.sh [--dry-run]
#
# The site is the results hub (scripts/make_hub.py), the figures in docs/images/, the reports in
# docs/reports/gse95654_20m/, docs/architecture.svg, and thumbnail.png: a 1200x630 screenshot of
# the hub's top, for link previews. --dry-run builds it and lists every file without uploading.
#
# Source links (GitHub, walkthrough, software list) are added only while the repo is public, so a
# site published from a private repo has no dead links.
#
# The pages this repo generates (the hub and the QC (quality control) and DMR (differentially
# methylated region) reports) get a release footer: license, source, the version in
# pyproject.toml, and this run's date (src/methyl_flow/site_footer.py). The Nextflow, MultiQC, and
# IGV (Integrative Genomics Viewer) reports are third-party HTML and are copied as they are.
#
# Needs AWS credentials, infra/terraform/site applied and initialized (terraform init), the GitHub
# CLI, and Google Chrome for the thumbnail (CHROME overrides the macOS path).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[[ -x "$CHROME" ]] || { echo "Chrome not found at $CHROME (set CHROME)" >&2; exit 1; }

output() { terraform -chdir=infra/terraform/site output -raw "$1"; }
BUCKET="$(output site_bucket_name)"
DISTRIBUTION="$(output distribution_id)"
URL="$(output site_url)"

SITE="$(mktemp -d)"
trap 'rm -r "$SITE"' EXIT
mkdir -p "$SITE/images" "$SITE/reports"
REPO_ARGS=()
if [[ "$(gh repo view --json visibility -q .visibility)" == PUBLIC ]]; then
    REPO_ARGS=(--repo-url "$(gh repo view --json url -q .url)")
fi
uv run python scripts/make_hub.py --base-url "$URL" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --out "$SITE/index.html"
cp docs/images/*.png "$SITE/images/"
cp docs/reports/gse95654_20m/*.html "$SITE/reports/"
cp docs/architecture.svg "$SITE/"
RELEASED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run python -m methyl_flow.site_footer --released-at "$RELEASED_AT" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} \
    "$SITE/index.html" "$SITE/reports/qc_report.html" "$SITE/reports/dmr_report.html"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1200,630 \
    --screenshot="$SITE/thumbnail.png" "file://$SITE/index.html" 2>/dev/null

echo "Site for $URL (bucket $BUCKET), source links: ${REPO_ARGS[1]:-none, repo is private}"
(cd "$SITE" && find . -type f | sed 's|^\./||' | sort | while read -r f; do
    printf '  %-45s %8s\n' "$f" "$(du -h "$f" | cut -f1)"
done)

if $DRY_RUN; then
    mkdir -p "$ROOT/logs" && cp "$SITE/thumbnail.png" "$ROOT/logs/site-thumbnail.png"
    echo "Dry run: nothing uploaded. Thumbnail copied to logs/site-thumbnail.png."
    exit 0
fi

# --delete removes anything in the bucket that is no longer part of the site
aws s3 sync "$SITE" "s3://$BUCKET" --delete --only-show-errors
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION" --paths '/*' \
    --query Invalidation.Id --output text >/dev/null
echo "Published: $URL"
