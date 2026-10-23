"""Draw docs/architecture.svg: where runs execute, how data flows, and the quality checks.

Each box has a hover note and links to its docs or source when the SVG is opened in a browser.
GitHub shows it as a plain image.

Run: uv run python scripts/make_diagrams.py [--out docs]
"""

import argparse
import html
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, default=Path("docs"))
OUT = parser.parse_args().out
STYLE = {
    "analysis": ("#F1ECFB", "#7A57C9", ""),
    "compute": ("#FFF4E5", "#E0862B", ""),
    "data": ("#E7F3EC", "#2F8F5B", ""),
    "ops": ("#EEF1F5", "#6B7A8C", ""),
    "outside": ("#FFFFFF", "#8A8F98", ' stroke-dasharray="6 4"'),
}
REPO = "https://github.com/toddcreasy/methyl-flow/blob/main/"
WALK = REPO + "docs/walkthrough.md"
FONT = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
CSS = (
    ".t{fill:#1F2933}.s{fill:#52606D;font-size:11px}"
    ".g{fill:#3E4C59;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}"
    ".e{fill:#3E4C59;font-size:10.5px}"
    "a:hover rect.n{stroke-width:2.5}g.h:hover rect.n{stroke-width:2.5}"
)
ARROW = (
    '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#3E4C59"/></marker></defs>'
)


def esc(text):
    return html.escape(text, quote=True)


def header(width, height, title, desc):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">',
        f"<title>{esc(title)}</title>",
        f"<desc>{esc(desc)}</desc>",
        ARROW,
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        f"<style>{CSS}</style>",
    ]


def panel(x, y, w, h, label, note):
    return (
        f'<g><title>{esc(note)}</title><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
        f'fill="#FAFBFC" stroke="#CBD2D9" stroke-width="1"/>'
        f'<text x="{x + 14}" y="{y + 20}" class="g">{esc(label)}</text></g>'
    )


def node(x, y, w, h, kind, name, sub, note, link=None):
    fill, stroke, dash = STYLE[kind]
    cx = x + w / 2
    body = (
        f"<title>{esc(note)}</title>"
        f'<rect class="n" x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.5"{dash}/>'
        f'<text x="{cx}" y="{y + h / 2 - 4}" text-anchor="middle" class="t" font-size="13" '
        f'font-weight="700">{esc(name)}</text>'
        f'<text x="{cx}" y="{y + h / 2 + 13}" text-anchor="middle" class="s">{esc(sub)}</text>'
    )
    if link:
        return f'<a xlink:href="{esc(link)}" href="{esc(link)}" target="_blank">{body}</a>'
    return f'<g class="h">{body}</g>'


def arrow(points, label="", lx=None, ly=None, anchor="start"):
    pts = " ".join(f"{x},{y}" for x, y in points)
    out = (
        f'<g><polyline points="{pts}" fill="none" stroke="#3E4C59" stroke-width="1.5" '
        f'marker-end="url(#arr)"/>'
    )
    if label:
        out += f'<text x="{lx}" y="{ly}" class="e" text-anchor="{anchor}">{esc(label)}</text>'
    return out + "</g>"


W, H = 1240, 1010
NW, NH = 220, 56
s = header(
    W,
    H,
    "methyl-flow: how bisulfite reads become a beta table and QC reports",
    "A laptop submits each run to AWS Batch, where a Nextflow head job starts one job per task "
    "and every file lives in S3. The pipelines fetch reads from SRA, run nf-core/methylseq, "
    "convert its coverage files into the beta table methyl-floor reads, and write QC reports.",
)
s.append('<text x="40" y="26" class="t" font-size="15" font-weight="700">methyl-flow</text>')
s.append(
    '<text x="140" y="26" class="s">Dashed boxes are outside AWS. '
    "Open the SVG on its own and hover a box for what it does and why.</text>"
)

# Laptop and AWS.
LX, AX = [70], [390, 680, 970]
R = [80, 180, 280]
mid = [r + NH // 2 for r in R]
s.append(
    panel(
        40,
        40,
        280,
        320,
        "Laptop",
        "Submits runs and deploys the stack. No sequencing data or processing lives here.",
    )
)
s.append(
    panel(
        360,
        40,
        840,
        320,
        "AWS (Amazon Web Services), us-east-1",
        "One stack, MethylFlowBatchStack, deployed with the CDK (Cloud Development Kit). "
        "Billed only while jobs run, plus S3 storage.",
    )
)
s += [
    node(
        LX[0],
        R[0],
        NW,
        NH,
        "ops",
        "scripts/run.sh",
        "<pipeline> <params file>",
        "The one command for every run. Uploads config/, pipelines/, and src/ to S3 (Amazon "
        "Simple Storage Service) as a run bundle, then submits the Nextflow head process as an "
        "AWS Batch job. Pins nf-core/methylseq 4.2.0 and Nextflow 25.04.0.",
        REPO + "scripts/run.sh",
    ),
    node(
        LX[0],
        R[1],
        NW,
        NH,
        "data",
        "config/",
        "params files, run manifest",
        "One YAML (YAML Ain't Markup Language) params file per pipeline and dataset, checked "
        "into git, so a run is a file, not a typed command. config/gse95654/runs.tsv pins the 18 "
        "SRR (Sequence Read Archive run) accessions.",
        REPO + "config",
    ),
    node(
        LX[0],
        R[2],
        NW,
        NH,
        "ops",
        "cdk deploy",
        "infra/aws, in Python",
        "The AWS CDK (Cloud Development Kit) describes the stack in Python, with tests, and "
        "deploys it through CloudFormation in one command.",
        REPO + "infra/aws/README.md",
    ),
    node(
        AX[0],
        R[0],
        NW,
        NH,
        "compute",
        "Nextflow head job",
        "on-demand queue, 2 vCPU",
        "Runs Nextflow 25.04.0 itself as a Batch job on the on-demand queue, so a Spot reclaim "
        "can't kill a whole run and the laptop can close. Copies the run bundle from S3, then "
        "submits one Batch job per task.",
        "https://www.nextflow.io/docs/latest/aws.html",
    ),
    node(
        AX[1],
        R[0],
        NW,
        NH,
        "compute",
        "Task jobs on Spot",
        "methyl-flow-spot, up to 256 vCPU",
        "One EC2 (Elastic Compute Cloud) instance per batch of tasks, each in a pinned "
        "container. Spot capacity is cheaper but can be reclaimed; Nextflow resubmits a "
        "reclaimed task up to 3 times. Scales to zero when the queue is empty.",
        "https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html",
    ),
    node(
        AX[2],
        R[0],
        NW,
        NH,
        "outside",
        "Seqera Platform",
        "live run monitoring",
        "The head job streams each run's progress here when the token secret is set. Lists the "
        "QC (quality control) report and tables on the run's Outputs tab (tower.yml).",
        "https://docs.seqera.io/platform-cloud",
    ),
    node(
        AX[0],
        R[1],
        NW,
        NH,
        "ops",
        "Secrets Manager",
        "Seqera token",
        "Holds the Seqera Platform access token. Only the head job's execution role can read "
        "it; it is injected as an environment variable, never written to a file.",
        "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html",
    ),
    node(
        AX[1],
        R[1],
        NW,
        NH,
        "data",
        "S3 bucket",
        "data/ results/ work/ runs/",
        "Every file: downsampled reads and the reference under data/, pipeline output under "
        "results/<pipeline>/<run ID>/, Nextflow's intermediate files under work/, and each run's "
        "config bundle and log under runs/.",
        "https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html",
    ),
    node(
        AX[2],
        R[1],
        NW,
        NH,
        "ops",
        "Budget",
        "$50 a month, tag-filtered",
        "Emails at 80% and 100% of actual spend and 100% of forecast, counting only resources "
        "tagged project=methyl-flow.",
        "https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html",
    ),
    node(
        AX[0],
        R[2],
        NW,
        NH,
        "ops",
        "CloudFormation",
        "MethylFlowBatchStack",
        "Creates the VPC (virtual private cloud), compute environments, job queues, head job "
        "definition, roles, bucket, secret, and budget from the CDK app.",
        "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html",
    ),
    node(
        AX[1],
        R[2],
        NW,
        NH,
        "ops",
        "CloudWatch Logs",
        "/aws/batch/job",
        "Console output of the head job and every task, for when a run fails before Nextflow "
        "can write its own log.",
        "https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/WhatIsCloudWatchLogs.html",
    ),
]
s += [
    arrow([(LX[0] + NW, mid[0]), (AX[0], mid[0])], "submit", LX[0] + NW + 10, mid[0] - 6),
    arrow(
        [
            (LX[0] + NW, mid[0] + 14),
            (340, mid[0] + 14),
            (340, R[1] - 14),
            (AX[1] + 40, R[1] - 14),
            (AX[1] + 40, R[1]),
        ],
        "upload run bundle",
        AX[0] + NW + 8,
        R[1] - 20,
    ),
    arrow(
        [(LX[0] + NW / 2, R[1]), (LX[0] + NW / 2, R[0] + NH)], "read", LX[0] + NW / 2 + 6, R[1] - 16
    ),
    arrow([(LX[0] + NW, mid[2]), (AX[0], mid[2])], "deploy", LX[0] + NW + 10, mid[2] - 6),
    arrow([(AX[0] + NW, mid[0]), (AX[1], mid[0])], "per task", AX[0] + NW + 8, mid[0] - 6),
    arrow(
        [(AX[1] + NW / 2 + 30, R[0] + NH), (AX[1] + NW / 2 + 30, R[1])],
        "read, write",
        AX[1] + NW / 2 + 36,
        R[0] + NH + 16,
    ),
    arrow(
        [(AX[0] + NW / 2, R[1]), (AX[0] + NW / 2, R[0] + NH)],
        "token",
        AX[0] + NW / 2 + 6,
        R[1] - 16,
    ),
    arrow(
        [
            (AX[0] + NW - 30, R[0]),
            (AX[0] + NW - 30, R[0] - 14),
            (AX[2] + NW / 2, R[0] - 14),
            (AX[2] + NW / 2, R[0]),
        ],
        "stream progress",
        AX[1] + 50,
        R[0] - 18,
    ),
]

# Data flow.
C = [60, 290, 520, 750, 980]
DW = 170
RA, RB, RC = 420, 510, 600
ma, mb, mc = RA + NH // 2, RB + NH // 2, RC + NH // 2
s.append(
    panel(
        40,
        380,
        1160,
        300,
        "Data flow, one scripts/run.sh call per step",
        "Each step reads the last step's output from S3 and writes its own under "
        "results/<pipeline>/<run ID>/. Every run also writes Nextflow's interactive execution "
        "report and timeline to pipeline_info/.",
    )
)
s += [
    node(
        C[0],
        RA,
        DW,
        NH,
        "outside",
        "SRA",
        "GSE95654, 18 RRBS runs",
        "SRA (Sequence Read Archive) study SRP101332: RRBS (reduced representation bisulfite "
        "sequencing) of colorectal tumor and adjacent normal tissue from 9 patients.",
        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE95654",
    ),
    node(
        C[0],
        RB,
        DW,
        NH,
        "outside",
        "GENCODE + UCSC",
        "GRCh38, genes, CpG islands",
        "GENCODE release 50: the human reference genome (primary assembly) for alignment, and "
        "its gene annotation for DMR annotation. UCSC (University of California, Santa Cruz) "
        "hg38 CpG islands for DMR annotation. Each checked against a pinned MD5 (Message Digest "
        "5) checksum.",
        "https://www.gencodegenes.org/human/release_50.html",
    ),
    node(
        C[1],
        RA,
        DW,
        NH,
        "analysis",
        "fetch_sra",
        "prefetch, fasterq-dump, seqtk",
        "Downloads each run with MD5-validated prefetch, rejects SRA Lite files that replace "
        "quality scores with a constant, and downsamples to 20 million read pairs with seed 42. "
        "Writes the methylseq sample sheet.",
        REPO + "pipelines/fetch_sra/main.nf",
    ),
    node(
        C[2],
        RA,
        DW,
        NH,
        "analysis",
        "nf-core/methylseq 4.2.0",
        "trim, Bismark align, call",
        "FastQC (read quality check), Trim Galore (adapter and quality trimming), Bismark "
        "alignment to the bisulfite-converted genome, and Bismark methylation extraction. RRBS "
        "mode skips deduplication. Run, not rewritten.",
        "https://nf-co.re/methylseq/4.2.0",
    ),
    node(
        C[2],
        RB,
        DW,
        NH,
        "data",
        "MultiQC report",
        "interactive HTML",
        "MultiQC (combined quality control) gathers FastQC, trimming, alignment, and "
        "methylation reports for every sample into one interactive page.",
        REPO + "docs/reports",
    ),
    node(
        C[3],
        RA,
        DW,
        NH,
        "analysis",
        "convert",
        "src/methyl_flow/convert.py",
        "Reads each sample's Bismark coverage file, keeps chr1 to chr22, chrX, chrY and sites "
        "with 10 or more reads, and computes beta = methylated / total reads.",
        REPO + "src/methyl_flow/convert.py",
    ),
    node(
        C[4],
        RA,
        DW,
        NH,
        "outside",
        "methyl-floor",
        "sibling repo: detection limit",
        "Reads the beta table and sample sheet. The two files are the contract between the "
        "repos; tests/test_convert.py loads them with methyl-floor's own loader.",
    ),
    node(
        C[3],
        RB,
        DW,
        NH,
        "analysis",
        "qc",
        "qc.py, plots.py, report.py",
        "Per-sample bisulfite conversion rate, duplicate rate, and coverage; coverage and "
        "methylation distributions; PCA (principal component analysis) by tissue and read "
        "layout.",
        REPO + "src/methyl_flow/qc.py",
    ),
    node(
        C[4],
        RB,
        DW,
        NH,
        "data",
        "QC report",
        "report.html, table, PNGs",
        "Interactive QC (quality control) report: sortable table, then coverage, methylation, "
        "and PCA charts with hover. Static PNG versions sit beside it.",
        REPO + "docs/reports",
    ),
    node(
        C[3],
        RC,
        DW,
        NH,
        "analysis",
        "dss",
        "r/dss.R, ~ patient + tissue",
        "DSS (Dispersion Shrinkage for Sequencing data) in R fits a beta-binomial model to "
        "methylated and total reads at each CpG (cytosine followed by guanine) site with 5 or "
        "more reads in every sample, pairs each tumor with its own patient's normal, and calls "
        "DMRs (differentially methylated regions) from FDR (false discovery rate)-significant "
        "sites. src/methyl_flow/annotate.py then places each DMR against CpG islands, "
        "promoters, and the nearest protein-coding gene, and igv-reports draws a genome "
        "browser (IGV, Integrative Genomics Viewer) view of the strongest DMRs.",
        REPO + "r/dss.R",
    ),
    node(
        C[4],
        RC,
        DW,
        NH,
        "data",
        "DMR report",
        "report.html, IGV view",
        "DMRs (differentially methylated regions) built from FDR (false discovery rate)-"
        "significant sites, annotated with CpG island context and nearest gene, plus a volcano "
        "plot, enrichment against all tested sites, and each DMR's normal and tumor values per "
        "patient, as an interactive page and tables.",
        REPO + "docs/reports",
    ),
    arrow([(C[0] + DW, ma), (C[1], ma)], "reads", C[0] + DW + 6, ma - 6),
    arrow([(C[0] + DW, mb), (C[0] + DW + 20, mb), (C[0] + DW + 20, ma + 12), (C[1], ma + 12)]),
    arrow([(C[1] + DW, ma), (C[2], ma)], "FASTQ", C[1] + DW + 6, ma - 6),
    arrow([(C[2] + DW / 2, RA + NH), (C[2] + DW / 2, RB)]),
    arrow([(C[2] + DW, ma), (C[3], ma)], ".cov.gz", C[2] + DW + 6, ma - 6),
    arrow([(C[3] + DW, ma), (C[4], ma)], "betas", C[3] + DW + 6, ma - 6),
    arrow([(C[2] + DW, mb), (C[3], mb)], "reports", C[2] + DW + 6, mb - 6),
    arrow([(C[3] + DW / 2, RA + NH), (C[3] + DW / 2, RB)]),
    arrow([(C[3] + DW, mb), (C[4], mb)]),
    arrow(
        [(C[2] + DW, ma + 14), (C[2] + DW + 30, ma + 14), (C[2] + DW + 30, mc), (C[3], mc)],
        "read counts",
        C[2] + DW + 24,
        mc - 6,
        "end",
    ),
    arrow([(C[3] + DW, mc), (C[4], mc)]),
]

# Quality checks.
s.append(panel(40, 700, 1160, 110, "Quality checks", "What runs before code reaches main."))
RQ = 735
mq = RQ + NH // 2
s += [
    node(
        C[0],
        RQ,
        DW,
        NH,
        "ops",
        "pre-commit",
        "ruff before each commit",
        "Lint and format run before a commit lands.",
        "https://pre-commit.com/",
    ),
    node(
        C[1],
        RQ,
        DW,
        NH,
        "outside",
        "GitHub",
        "pull request to main",
        "main is protected: every change arrives as a pull request with passing CI "
        "(continuous integration) and is squash-merged.",
        "https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-"
        "repository/managing-protected-branches/about-protected-branches",
    ),
    node(
        C[2],
        RQ,
        DW,
        NH,
        "ops",
        "GitHub Actions",
        "uv sync --locked, ruff, pytest",
        "CI (continuous integration) on every pull request. --locked fails if pyproject.toml "
        "and uv.lock disagree.",
        REPO + ".github/workflows/ci.yml",
    ),
    node(
        C[3],
        RQ,
        DW,
        NH,
        "ops",
        "pytest + R tests",
        "fixture files, no network",
        "pytest checks conversion, QC (quality control) math, plots, and both reports on small "
        "fixture files; the methyl-floor schema check runs when that repo is installed. "
        "r/tests/test_dss.R plants a known DMR in synthetic data and runs in the same DSS "
        "container as AWS Batch.",
        REPO + "tests",
    ),
    arrow([(C[0] + DW, mq), (C[1], mq)]),
    arrow([(C[1] + DW, mq), (C[2], mq)]),
    arrow([(C[2] + DW, mq), (C[3], mq)]),
]

# Legend.
LY = 840
s.append(panel(40, LY, 1160, 140, "Key", "Box colors."))
for i, (kind, name, sub) in enumerate(
    [
        ("analysis", "Pipeline step", "runs on Batch"),
        ("data", "Data or report", "in S3 or the repo"),
        ("compute", "Compute", "AWS Batch"),
        ("ops", "Operations", "deploy, config, checks"),
        ("outside", "Outside AWS", "external service"),
    ]
):
    s.append(node(60 + i * 190, LY + 50, 176, NH, kind, name, sub, f"{name}: {sub}"))
s.append("</svg>")
(OUT / "architecture.svg").write_text("\n".join(s) + "\n")
print("wrote", OUT / "architecture.svg")
