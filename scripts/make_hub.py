"""Write the results hub, index.html: one page that explains each step and links to the
full reports. Counts, ranges, and shares are read from the run tables in
docs/reports/gse95654_20m/tables/. Three figures come from the checks in docs/walkthrough.md steps
7 and 9 and are quoted as text: 8 of 9 tumors on PC1, the 0.30 median change, and 93.1% agreement.

The page links to reports/, images/, and architecture.svg, which scripts/publish_site.sh places
beside it. With --base-url (the public site URL), it also adds link-preview tags pointing at
thumbnail.png; scripts/publish_site.sh makes that image from this page.

scripts/publish_site.sh runs this; by hand:
  uv run python scripts/make_hub.py --out <folder>/index.html [--base-url https://example.cloudfront.net]
"""

import argparse
import csv
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reports" / "gse95654_20m" / "tables"

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="", help="public site URL, for link-preview tags")
# Links into the repo only work for visitors once it is public; publish_site.sh passes this then
parser.add_argument("--repo-url", default="", help="public GitHub repo URL, for source links")
parser.add_argument("--out", type=Path, required=True, help="where to write index.html")
args = parser.parse_args()


def read(name):
    with (DATA / name).open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


qc = read("samples_qc.tsv")
summary = {r["metric"]: float(r["value"]) for r in read("summary.tsv")}
enrich = {(r["group"], r["feature"]): r for r in read("annotation_enrichment.tsv")}
top = read("top_dmrs.tsv")[:10]


def span(field, fmt):
    values = [float(r[field]) for r in qc]
    return f"{fmt(min(values))} to {fmt(max(values))}"


def n(key):
    return f"{int(summary[key]):,}"


def share(group, feature):
    return float(enrich[(group, feature)]["share"])


def fold(group, feature):
    return float(enrich[(group, feature)]["fold_vs_tested"])


def pct(x):
    return f"{x:.1%}"


patients = len({r["patient"] for r in qc})
sig_pct = summary["sites_significant"] / summary["sites_tested"]
title = "methyl-flow: tumor-specific DNA methylation from bisulfite sequencing"
description = (
    f"Raw bisulfite reads from {len(qc)} colorectal tumor and normal samples to "
    f"{n('dmrs')} differentially methylated regions, reproducibly on AWS Batch with "
    "nf-core/methylseq, DSS, and Nextflow."
)

stats = [
    (f"{len(qc)}", f"samples: tumor and matched normal from {patients} patients"),
    (n("sites_tested"), "CpG (cytosine followed by guanine) sites tested"),
    (n("dmrs"), "DMRs (differentially methylated regions) at FDR (false discovery rate) < 5%"),
    (
        pct(share("dmr_hyper", "island")),
        "of sites gaining methylation in tumor sit in CpG islands",
    ),
]


def section(anchor, heading, body, figure=None, alt="", links=()):
    fig = (
        f'<figure><img src="{figure}" alt="{html.escape(alt)}" loading="lazy"></figure>'
        if figure
        else ""
    )
    link_html = "".join(
        f'<a class="button" href="{href}">{html.escape(label)}</a>' for label, href in links
    )
    return (
        f'<section id="{anchor}"><h2>{html.escape(heading)}</h2>{body}{fig}'
        f'<div class="links">{link_html}</div></section>'
    )


def context(d):
    return "promoter" if d["promoter"] == "True" else d["cpg_context"].replace("_", " ")


top_rows = "".join(
    "<tr>"
    f"<td>{html.escape(d['chr'])}:{int(d['start']):,}</td>"
    f"<td>{html.escape(d['nearest_gene'])}</td>"
    f"<td>{html.escape(context(d))}</td>"
    f"<td>{int(d['n_cpg'])}</td>"
    f"<td>{float(d['beta_normal']):.2f} to {float(d['beta_tumor']):.2f}</td>"
    "</tr>"
    for d in top
)

sections = [
    section(
        "pipeline",
        "How it runs",
        "<p>A laptop submits each step with one command, <code>scripts/run.sh</code>, and does no "
        "processing. A Nextflow head job on AWS (Amazon Web Services) Batch starts one job per "
        "task on Spot capacity, which scales to zero when idle, and every file lives in S3 "
        "(Amazon Simple Storage Service). Pipeline and tool versions are pinned, so a run "
        "reproduces from its params file. The steps: fetch reads from the SRA (Sequence Read "
        "Archive), process them with nf-core/methylseq, convert the methylation calls into a "
        "beta table, check quality, test tumor against normal with DSS (Dispersion Shrinkage "
        "for Sequencing data), and annotate the results.</p>",
        "architecture.svg",
        "Architecture: a laptop submits runs to AWS Batch; pipelines fetch reads, run "
        "nf-core/methylseq, convert, run QC, and test with DSS; reports land in S3.",
    ),
    section(
        "data",
        "Data",
        "<p>GSE95654 (GEO, Gene Expression Omnibus, Series 95654) is public RRBS (reduced "
        "representation bisulfite sequencing) of primary colorectal tumors and adjacent normal "
        f"colon. This analysis uses {patients} patients and {len(qc)} samples, each downsampled to "
        "20 million read pairs with a fixed seed. Bisulfite treatment turns unmethylated "
        "cytosines into uracil, read as thymine, while methylated cytosines stay cytosine; so "
        "counting C and T at each CpG (cytosine followed by guanine) site gives its methylation "
        "level, the beta value, from 0 to 1.</p>",
    ),
    section(
        "qc",
        "Quality control",
        f"<p>Bisulfite conversion was {span('conversion_rate', pct)} in every sample, above the "
        "usual 99% bar, so false methylation from unconverted cytosines stays under 1%. Median "
        f"coverage was {span('median_coverage', lambda v: f'{v:.0f}')} reads per site, with "
        f"{span('fraction_min_coverage', pct)} of sites at 10 or more reads. PCA (principal "
        "component analysis) separates 8 of 9 tumors from the normals on its first component, "
        "and the one batch in the data, single-end against paired-end reads, does not separate "
        "samples.</p>",
        "images/pca.png",
        "PCA of 18 samples, colored by tissue and by read layout",
        [
            ("QC report", "reports/qc_report.html"),
            ("MultiQC report", "reports/multiqc_report.html"),
        ],
    ),
    section(
        "dmrs",
        "Tumor against normal",
        "<p>DSS (Dispersion Shrinkage for Sequencing data) fits a beta-binomial model to "
        "methylated and total reads at each site and compares each tumor with its own "
        f"patient's normal. Of {n('sites_tested')} sites with 5 or more reads in every sample, "
        f"{n('sites_significant')} ({pct(sig_pct)}) pass FDR (false discovery rate) < 5%: "
        f"{n('sites_hypo')} lose methylation in tumor and {n('sites_hyper')} gain it. Runs of "
        f"nearby significant sites form {n('dmrs')} DMRs (differentially methylated regions). "
        "Before trusting a quarter of sites passing, three checks: significant sites change a "
        "lot (median 0.30 in beta), the p-value distribution shows no inflation, and 93.1% of "
        "DMRs move the same way in at least 8 of 9 patients.</p>",
        "images/top_dmrs.png",
        "Normal and tumor methylation per patient for the 12 strongest DMRs",
        [("DMR report", "reports/dmr_report.html")],
    ),
    section(
        "annotation",
        "Where the changes fall",
        "<p>Cancer is expected to gain methylation at CpG (cytosine followed by guanine) "
        "islands in promoters, which switches genes off, and to lose it across the rest of the "
        "genome. The test knew nothing about islands or genes, so this is an independent check. "
        f"Sites in DMRs gaining methylation are {pct(share('dmr_hyper', 'island'))} in islands "
        f"({fold('dmr_hyper', 'island'):.2f} times the tested background) and "
        f"{pct(share('dmr_hyper', 'promoter'))} in promoters; sites losing it are "
        f"{pct(share('dmr_hypo', 'open_sea'))} in open sea, away from islands. The strongest "
        "regions and their nearest protein-coding genes:</p>"
        "<div class='wrap'><table><thead><tr><th>Region start</th><th>Nearest gene</th>"
        "<th>Context</th><th>CpG sites</th><th>Normal to tumor beta</th></tr></thead>"
        f"<tbody>{top_rows}</tbody></table></div>"
        "<p class='note'>A gene name is a position, not a function: no expression data was "
        "measured, so a DMR at a promoter suggests, but doesn't show, that the gene is switched "
        "off.</p>",
        "images/annotation.png",
        "Share of tested, significant, and DMR sites in CpG island and gene contexts",
        [("DMR report", "reports/dmr_report.html#annotation")],
    ),
    section(
        "browser",
        "Genome browser",
        "<p>An IGV (Integrative Genomics Viewer) view of the 25 strongest DMRs (differentially "
        "methylated regions) in each direction: mean methylation in normal and tumor at every "
        "tested site, the DMRs, CpG (cytosine followed by guanine) islands, and genes. Pick a "
        "region from the table, then zoom out to see 2,000 bases either side.</p>",
        links=[("Genome browser", "reports/igv_report.html")],
    ),
    section(
        "runs",
        "Run records",
        "<p>Nextflow's execution reports and timelines record every task's run time, CPU, and "
        "memory.</p>",
        links=[
            ("methylseq", "reports/methylseq_execution_report.html"),
            ("QC", "reports/qc_execution_report.html"),
            ("DSS", "reports/dss_execution_report.html"),
        ],
    ),
    section(
        "limits",
        "Limits",
        "<ul><li>Downsampled to 20 million read pairs per sample; median coverage is 4 to 7 "
        "reads per site.</li>"
        f"<li>{patients} patients: enough to show the pipeline and a clear tumor signal, not "
        "enough to generalize.</li>"
        "<li>RRBS (reduced representation bisulfite sequencing) reads CpG-rich regions well "
        "and most of the genome not at all.</li>"
        "<li>Tissue, not blood. MCED (multi-cancer early detection) tests read cell-free DNA, "
        "where tumor DNA is a small fraction of the total.</li></ul>",
    ),
]

repo = args.repo_url.rstrip("/")
repo_links = (
    "<p class='hero-links'>"
    f"<a href='{repo}'>Source on GitHub</a>"
    f"<a href='{repo}/blob/main/docs/walkthrough.md'>Walkthrough</a>"
    f"<a href='{repo}/blob/main/docs/software.md'>Software</a></p>"
    if repo
    else ""
)

nav = "".join(
    f'<a href="#{a}">{label}</a>'
    for a, label in [
        ("pipeline", "Pipeline"),
        ("data", "Data"),
        ("qc", "QC"),
        ("dmrs", "Tumor vs normal"),
        ("annotation", "Annotation"),
        ("browser", "Browser"),
        ("limits", "Limits"),
    ]
)

stat_html = "".join(
    f"<div class='stat'><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>"
    for v, k in stats
)
hero_alt = html.escape(
    f"Volcano plot: methylation change against significance for {n('sites_tested')} CpG sites, "
    "gains in orange and losses in blue"
)

preview = ""
if args.base_url:
    base = args.base_url.rstrip("/")
    preview = (
        f'<meta property="og:type" content="website">'
        f'<meta property="og:title" content="{html.escape(title)}">'
        f'<meta property="og:description" content="{html.escape(description)}">'
        f'<meta property="og:url" content="{base}/">'
        f'<meta property="og:image" content="{base}/thumbnail.png">'
        f'<meta property="og:image:width" content="1200">'
        f'<meta property="og:image:height" content="630">'
        f'<meta name="twitter:card" content="summary_large_image">'
    )

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>methyl-flow results</title>
<meta name="description" content="{html.escape(description)}">
{preview}
<style>
:root {{
  --ink: #0f1b2d; --text: #1f2933; --muted: #52606d; --line: #e4e7eb; --bg: #fbfbfa;
  --hero: #0f1b2d; --hero-text: #f5f7fa; --hero-muted: #b8c4d3; --accent: #eb6834;
  --card: #ffffff;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
a {{ color: inherit; }}
.hero {{ background: var(--hero); color: var(--hero-text); }}
.hero-inner {{ max-width: 1200px; min-height: 630px; margin: 0 auto; padding: 36px 48px;
  display: grid; grid-template-columns: 1fr 1fr; gap: 44px; align-items: center; }}
.kicker {{ color: var(--accent); font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  font-size: 13px; margin: 0 0 12px; }}
.hero h1 {{ font-size: 40px; line-height: 1.1; margin: 0 0 14px; }}
.hero p.lede {{ color: var(--hero-muted); font-size: 17px; margin: 0 0 22px; }}
.stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.stat {{ border: 1px solid #2b3a52; border-radius: 10px; padding: 12px 16px; }}
.stat b {{ display: block; font-size: 28px; line-height: 1.1; }}
.stat span {{ color: var(--hero-muted); font-size: 13px; line-height: 1.35; display: block;
  margin-top: 4px; }}
.hero-links {{ margin: 18px 0 0; display: flex; gap: 22px; flex-wrap: wrap; }}
.hero-links a {{ color: var(--hero-text); font-weight: 600; text-underline-offset: 4px; }}
.hero figure {{ margin: 0; background: #fcfcfb; border-radius: 12px; padding: 12px; }}
.hero figure img {{ width: 100%; display: block; }}
nav {{ position: sticky; top: 0; background: var(--card); border-bottom: 1px solid var(--line);
  z-index: 1; }}
nav .inner {{ max-width: 1000px; margin: 0 auto; padding: 10px 16px; display: flex; gap: 18px;
  overflow-x: auto; white-space: nowrap; font-size: 14px; }}
nav a {{ text-decoration: none; color: var(--muted); }}
nav a:hover {{ color: var(--ink); }}
main {{ max-width: 1000px; margin: 0 auto; padding: 16px 16px 64px; }}
section {{ padding: 32px 0; border-bottom: 1px solid var(--line); }}
h2 {{ color: var(--ink); font-size: 24px; margin: 0 0 8px; }}
section p, section li {{ max-width: 75ch; }}
figure {{ margin: 20px 0 8px; }}
figure img {{ max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px;
  background: #fff; }}
.links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
.button {{ display: inline-block; padding: 8px 14px; border-radius: 8px; background: var(--ink);
  color: #fff; text-decoration: none; font-size: 14px; font-weight: 600; }}
.button:hover {{ background: #24364f; }}
.wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 14px; margin: 12px 0; }}
th, td {{ padding: 6px 12px; border-bottom: 1px solid var(--line); text-align: left;
  white-space: nowrap; }}
th {{ color: var(--muted); font-weight: 600; }}
.note {{ color: var(--muted); font-size: 14px; }}
code {{ font-size: 14px; background: #eef1f4; padding: 1px 5px; border-radius: 4px; }}
footer {{ max-width: 1000px; margin: 0 auto; padding: 0 16px 48px; color: var(--muted);
  font-size: 14px; }}
@media (max-width: 860px) {{
  .hero-inner {{ grid-template-columns: 1fr; min-height: 0; padding: 32px 16px; gap: 28px; }}
  .hero h1 {{ font-size: 32px; }}
}}
</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
<div>
<p class="kicker">Bisulfite sequencing on AWS</p>
<h1>Tumor-specific DNA methylation in colorectal cancer</h1>
<p class="lede">{html.escape(description)}</p>
<div class="stats">{stat_html}</div>
{repo_links}
</div>
<figure><img src="images/volcano.png" alt="{hero_alt}"></figure>
</div></header>
<nav><div class="inner">{nav}</div></nav>
<main>
{"".join(sections)}
</main>
<footer>
<p>methyl-flow is a research project on public data, not a clinical or diagnostic tool. Data:
Hanley, M. P., et al. "Genome-wide DNA methylation profiling reveals cancer-associated changes
within early colonic neoplasia." <i>Oncogene</i>, 2017.
<a href="https://doi.org/10.1038/onc.2017.130">doi:10.1038/onc.2017.130</a>. Figures and
reports are derived from that data.</p>
</footer>
</body>
</html>
"""
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(page)
print("wrote", args.out)
