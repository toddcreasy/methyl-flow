"""Interactive HTML QC report from the data behind ``plots.py``'s figures.

One self-contained page: the per-sample QC table (click a header to sort), then coverage,
methylation, and PCA charts with hover. The data is embedded as JSON; Plotly.js loads from a
pinned CDN URL, so the page needs a network connection to draw the charts. The table works
without it.
"""

import html
import json
from pathlib import Path

import numpy as np

PLOTLY_JS = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"

# Conversion below this suggests incomplete bisulfite treatment
MIN_CONVERSION = 0.99

COLUMNS = [
    ("sample", "Sample"),
    ("patient", "Patient"),
    ("tissue", "Tissue"),
    ("batch", "Read layout"),
    ("conversion_rate", "Conversion"),
    ("duplicate_rate", "Duplicates"),
    ("cpg_sites", "CpG (cytosine-guanine) sites"),
    ("median_coverage", "Median reads"),
    ("sites_min_coverage", "Sites at cutoff"),
    ("fraction_min_coverage", "Share at cutoff"),
]
PERCENT = {"conversion_rate", "duplicate_rate", "fraction_min_coverage"}
COUNT = {"cpg_sites", "sites_min_coverage"}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QC report: {title}</title>
<style>
:root {{ --bg: #fcfcfb; --text: #0b0b0b; --muted: #52514e; --grid: #e4e3df; --flag: #b3261e; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 18px; margin: 36px 0 4px; }}
p {{ margin: 4px 0 12px; color: var(--muted); max-width: 75ch; }}
.wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 13px; width: 100%; }}
th, td {{ padding: 6px 10px; border-bottom: 1px solid var(--grid); text-align: right;
  white-space: nowrap; }}
th:nth-child(-n+4), td:nth-child(-n+4) {{ text-align: left; }}
th {{ cursor: pointer; user-select: none; color: var(--muted); font-weight: 600; }}
th:hover {{ color: var(--text); }}
td.flag {{ color: var(--flag); font-weight: 600; }}
.chart {{ width: 100%; height: 420px; }}
</style>
</head>
<body>
<main>
<h1>QC report: {title}</h1>
<p>{summary}</p>

<h2>Per-sample summary</h2>
<p>Conversion is the share of cytosines outside CpG (cytosine followed by guanine) sites that
read as converted by bisulfite. Below {min_conversion} it is flagged red, since unconverted
cytosines read as false methylation. Duplicates come from FastQC (a read quality checker) and run
high in RRBS (reduced representation bisulfite sequencing) by design, because reads start at the
same enzyme cut sites. The cutoff is {min_coverage} reads, the minimum for a site to get a beta
value in the beta table. Click a column header to sort.</p>
<div class="wrap"><table id="qc"><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table></div>

<h2>Coverage</h2>
<p>Share of each sample's CpG (cytosine followed by guanine) sites at each read count. Curves
that sit further right mean deeper coverage; the dashed line is the {min_coverage}-read cutoff.
Hover a line for its sample.</p>
<div id="coverage" class="chart"></div>

<h2>Methylation</h2>
<p>Distribution of beta values (methylated reads over total reads) at sites passing the cutoff.
CpG (cytosine followed by guanine) sites are mostly fully methylated or fully unmethylated, so
two peaks near 0 and 1 are expected. Tumors often lose methylation, which shows as a lower peak
near 1.</p>
<div id="methylation" class="chart"></div>

<h2>PCA (principal component analysis)</h2>
<p>{pca_note} If samples split by tissue on PC1 (principal component 1) but not by read
layout, the biology is stronger than the batch. Hover a point for the sample; the menu switches
the coloring.</p>
<div id="pca" class="chart"></div>
</main>

<script id="data" type="application/json">{data}</script>
<script src="{plotly_js}"></script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const layout = (x, y, extra) => Object.assign({{
  paper_bgcolor: "#fcfcfb", plot_bgcolor: "#fcfcfb", margin: {{t: 16, r: 16, b: 56, l: 64}},
  font: {{family: "-apple-system, Helvetica, Arial, sans-serif", size: 12, color: "#0b0b0b"}},
  xaxis: Object.assign({{gridcolor: "#e4e3df", zeroline: false}}, x),
  yaxis: Object.assign({{gridcolor: "#e4e3df", zeroline: false}}, y),
  hovermode: "closest", legend: {{orientation: "h", y: 1.08}},
}}, extra || {{}});
const line = (s, x, y, text) => ({{
  x, y, type: "scatter", mode: "lines", name: s.tissue, legendgroup: s.tissue,
  line: {{color: D.colors.tissue[s.tissue], width: 1.5}}, opacity: 0.8,
  hovertemplate: text + "<extra>" + s.sample + "</extra>",
}});
const firstOf = (traces) => {{
  const seen = new Set();
  traces.forEach(t => {{ t.showlegend = !seen.has(t.name); seen.add(t.name); }});
  return traces;
}};
if (window.Plotly) {{
  const cfg = {{responsive: true, displaylogo: false}};
  Plotly.newPlot("coverage", firstOf(D.samples.map(s => line(s, D.coverage[s.sample_id].x,
    D.coverage[s.sample_id].y, "%{{x}} reads: %{{y:.1%}} of sites"))), layout(
    {{type: "log",
      title: "Reads per CpG (cytosine-guanine) site (last point is " + D.max_bin + " or more)"}},
    {{title: "Share of the sample's sites", tickformat: ".0%"}},
    {{shapes: [{{type: "line", x0: D.min_coverage, x1: D.min_coverage, yref: "paper", y0: 0,
      y1: 1, line: {{dash: "dash", color: "#52514e", width: 1}}}}]}}), cfg);
  Plotly.newPlot("methylation", firstOf(D.samples.map(s => line(s, D.beta_mids,
    D.methylation[s.sample_id], "beta %{{x:.2f}}: density %{{y:.2f}}"))), layout(
    {{title: "Beta value", range: [0, 1]}}, {{title: "Density"}}), cfg);
  const pcaTrace = (key) => Object.keys(D.colors[key]).map(v => {{
    const ss = D.samples.filter(s => s[key] === v);
    return {{
      x: ss.map(s => D.pca[s.sample_id][0]), y: ss.map(s => D.pca[s.sample_id][1]),
      text: ss.map(s => s.patient), customdata: ss.map(s => [s.sample, s.tissue, s.batch]),
      type: "scatter", mode: "markers+text", name: v, textposition: "top right",
      textfont: {{size: 10, color: "#52514e"}},
      marker: {{size: 11, color: D.colors[key][v], line: {{color: "#fcfcfb", width: 1.5}},
        symbol: ss.map(s => D.symbols[s.batch])}},
      hovertemplate: "%{{customdata[0]}}<br>tissue %{{customdata[1]}}, layout %{{customdata[2]}}"
        + "<br>PC1 %{{x:.2f}}, PC2 %{{y:.2f}}<extra></extra>",
    }};
  }});
  const byTissue = pcaTrace("tissue"), byBatch = pcaTrace("batch");
  const vis = (n, on) => Array.from({{length: n}}, () => on);
  Plotly.newPlot("pca", byTissue.concat(byBatch.map(t => Object.assign(t, {{visible: false}}))),
    layout({{title: "PC1 (principal component 1), " + D.explained[0] + " of variance"}},
      {{title: "PC2 (principal component 2), " + D.explained[1] + " of variance"}},
      {{updatemenus: [{{x: 1, y: 1.15, xanchor: "right", buttons: [
        {{label: "Color by tissue", method: "restyle",
          args: ["visible", vis(byTissue.length, true).concat(vis(byBatch.length, false))]}},
        {{label: "Color by read layout", method: "restyle",
          args: ["visible", vis(byTissue.length, false).concat(vis(byBatch.length, true))]}},
      ]}}]}}), cfg);
}} else {{
  document.querySelectorAll(".chart").forEach(el => {{
    el.style.height = "auto";
    el.textContent = "Charts need a network connection to load Plotly.js.";
  }});
}}
document.querySelectorAll("#qc th").forEach((th, i) => th.addEventListener("click", () => {{
  const body = th.closest("table").tBodies[0];
  const up = th.dataset.dir !== "asc";
  th.parentNode.querySelectorAll("th").forEach(h => delete h.dataset.dir);
  th.dataset.dir = up ? "asc" : "desc";
  const key = (r) => {{
    const v = r.cells[i].dataset.v;
    return isNaN(v) ? v : Number(v);
  }};
  [...body.rows].sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0) * (up ? 1 : -1))
    .forEach(r => body.appendChild(r));
}}));
</script>
</body>
</html>
"""


def cell(field: str, value: str) -> str:
    if field in PERCENT:
        text = f"{float(value):.2%}"
    elif field in COUNT:
        text = f"{int(value):,}"
    else:
        text = value
    flag = ' class="flag"' if field == "conversion_rate" and float(value) < MIN_CONVERSION else ""
    return f'<td data-v="{html.escape(value)}"{flag}>{html.escape(text)}</td>'


def write_report(
    path: Path,
    title: str,
    samples: list[dict],
    hist: dict[str, list[tuple[int, int]]],
    matrix: np.ndarray,
    scores: np.ndarray,
    explained: np.ndarray,
    n_sites: int,
    min_coverage: int,
    max_bin: int,
    colors: dict[str, dict[str, str]],
    symbols: dict[str, str],
) -> None:
    """Write the report for ``samples`` (rows of ``samples_qc.tsv``, in ``matrix`` row order)."""
    bins = np.linspace(0, 1, 26)
    coverage, methylation = {}, {}
    for s, betas in zip(samples, matrix, strict=True):
        rows = hist[s["sample_id"]]
        total = sum(n for _, n in rows)
        coverage[s["sample_id"]] = {"x": [c for c, _ in rows], "y": [n / total for _, n in rows]}
        density, _ = np.histogram(betas[~np.isnan(betas)], bins=bins, density=True)
        methylation[s["sample_id"]] = [round(float(d), 4) for d in density]

    data = {
        "samples": [
            {k: s[k] for k in ("sample_id", "sample", "patient", "tissue", "batch")}
            for s in samples
        ],
        "coverage": coverage,
        "methylation": methylation,
        "beta_mids": [round(float(m), 4) for m in (bins[:-1] + bins[1:]) / 2],
        "pca": {
            s["sample_id"]: [float(x), float(y)] for s, (x, y) in zip(samples, scores, strict=True)
        },
        "explained": [f"{e:.0%}" for e in explained],
        "min_coverage": min_coverage,
        "max_bin": max_bin,
        "colors": colors,
        # Plotly marker names for the matplotlib markers plots.py uses
        "symbols": {k: {"o": "circle", "^": "triangle-up"}[v] for k, v in symbols.items()},
    }
    tissues = sorted({s["tissue"] for s in samples})
    counts = ", ".join(f"{sum(s['tissue'] == t for s in samples)} {t}" for t in tissues)
    page = PAGE.format(
        title=html.escape(title),
        summary=html.escape(
            f"{len(samples)} samples ({counts}). Built from methylseq's Bismark output and the "
            "converted beta table."
        ),
        min_conversion=f"{MIN_CONVERSION:.0%}",
        min_coverage=min_coverage,
        header="".join(f"<th>{html.escape(label)}</th>" for _, label in COLUMNS),
        rows="".join(
            "<tr>" + "".join(cell(f, s[f]) for f, _ in COLUMNS) + "</tr>" for s in samples
        ),
        pca_note=html.escape(
            f"Principal component analysis on the {n_sites:,} CpG (cytosine followed by guanine) "
            "sites with a beta value in "
            "every sample. Each point is a sample; samples with similar methylation sit close "
            "together."
        ),
        data=json.dumps(data).replace("</", "<\\/"),
        plotly_js=PLOTLY_JS,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page)
