"""Plots and an interactive HTML report from the DSS step's output (``r/dss.R``).

Reads ``dml.tsv.gz`` (one row per tested CpG site), ``dmrs.tsv``, ``dmr_samples.tsv``, and
``summary.tsv`` from ``--dss``, and writes to ``--out``:
  plots/volcano.png     methylation difference against significance, every tested site
  plots/top_dmrs.png    normal and tumor beta per patient for the strongest DMRs
  report.html           summary, volcano, sortable DMR table, and a per-DMR patient view

The report embeds a random sample of at most VOLCANO_POINTS sites from each volcano group (higher
in tumor, lower in tumor, not significant), so it stays small however many sites were tested;
volcano.png plots every site. Plotly.js loads from the same pinned URL as ``report.py``.
"""

import argparse
import csv
import html
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.csv as pacsv  # noqa: E402

from methyl_flow.plots import GRID, TISSUE_COLORS  # noqa: E402
from methyl_flow.report import PLOTLY_JS  # noqa: E402

log = logging.getLogger(__name__)

HYPER, HYPO, NOT_SIG = "#eb6834", "#2a78d6", "#b8b6b0"
# Volcano points embedded in the report besides the significant ones
VOLCANO_POINTS = 8_000
TABLE_ROWS = 500
TOP_DMRS = 12


def read_tsv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read_dml(path: Path) -> dict[str, np.ndarray]:
    """Per-site results as columns; a missing FDR (DSS leaves some sites untested) is NaN."""
    table = pacsv.read_csv(path, parse_options=pacsv.ParseOptions(delimiter="\t"))
    cols = {c: table[c] for c in ("chr", "pos", "stat", "pval", "fdr", "diff")}
    out = {
        c: pc.cast(cols[c], "float64").to_numpy(zero_copy_only=False)
        for c in cols
        if c not in ("chr", "pos")
    }
    out["chr"] = np.array(cols["chr"].to_pylist())
    out["pos"] = cols["pos"].to_numpy()
    return out


def read_summary(path: Path) -> dict[str, str]:
    return {r["metric"]: r["value"] for r in read_tsv(path)}


def neg_log10(p: np.ndarray) -> np.ndarray:
    return -np.log10(np.clip(p, 1e-300, 1))


def plot_volcano(diff, pval, significant, stat, fdr, path):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    y = neg_log10(pval)
    groups = [
        (~significant, NOT_SIG, "not significant"),
        (significant & (stat > 0), HYPER, "higher in tumor"),
        (significant & (stat < 0), HYPO, "lower in tumor"),
    ]
    for mask, color, label in groups:
        ax.scatter(
            diff[mask],
            y[mask],
            s=2,
            color=color,
            alpha=0.5,
            linewidths=0,
            rasterized=True,
            label=f"{label} ({mask.sum():,})",
        )
    ax.set_xlabel("Mean beta, tumor minus normal")
    ax.set_ylabel("-log10 p-value")
    ax.set_title(f"Paired test per CpG site, FDR < {fdr:g} colored")
    ax.legend(markerscale=4, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_top_dmrs(dmrs, by_dmr, path):
    top = dmrs[:TOP_DMRS]
    cols = 4
    rows = max(1, -(-len(top) // cols))
    fig, axes = plt.subplots(rows, cols, figsize=(11, 2.6 * rows), sharey=True, squeeze=False)
    for ax in axes.flat[len(top) :]:
        ax.axis("off")
    for ax, d in zip(axes.flat, top, strict=False):
        for pair in by_dmr[d["dmr_id"]].values():
            if len(pair) == 2:
                ax.plot([0, 1], [pair["normal"], pair["tumor"]], color=GRID, linewidth=1, zorder=1)
        for x, tissue in enumerate(["normal", "tumor"]):
            values = [p[tissue] for p in by_dmr[d["dmr_id"]].values() if tissue in p]
            ax.scatter([x] * len(values), values, s=22, color=TISSUE_COLORS[tissue], zorder=2)
        ax.set_xticks([0, 1], ["normal", "tumor"])
        ax.set_xlim(-0.4, 1.4)
        ax.set_ylim(-0.03, 1.03)
        ax.set_title(f"{d['chr']}:{int(d['start']):,}\n{d['n_cpg']} CpGs", fontsize=9)
    for ax in axes[:, 0]:
        ax.set_ylabel("Mean beta in region")
    fig.suptitle("Strongest DMRs: each line joins one patient's normal and tumor")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DMR report: {title}</title>
<style>
:root {{ --bg: #fcfcfb; --text: #0b0b0b; --muted: #52514e; --grid: #e4e3df; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 18px; margin: 36px 0 4px; }}
p {{ margin: 4px 0 12px; color: var(--muted); max-width: 75ch; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }}
.stat {{ border: 1px solid var(--grid); border-radius: 8px; padding: 10px 14px; min-width: 150px; }}
.stat b {{ display: block; font-size: 22px; }}
.stat span {{ color: var(--muted); font-size: 13px; }}
.wrap {{ overflow-x: auto; max-height: 520px; overflow-y: auto; }}
table {{ border-collapse: collapse; font-size: 13px; width: 100%; }}
th, td {{ padding: 6px 10px; border-bottom: 1px solid var(--grid); text-align: right;
  white-space: nowrap; }}
th:nth-child(-n+2), td:nth-child(-n+2) {{ text-align: left; }}
th {{ cursor: pointer; user-select: none; color: var(--muted); font-weight: 600;
  position: sticky; top: 0; background: var(--bg); }}
tbody tr {{ cursor: pointer; }}
tbody tr:hover {{ background: #f1f0ec; }}
.chart {{ width: 100%; height: 440px; }}
select {{ font: inherit; padding: 4px 8px; }}
</style>
</head>
<body>
<main>
<h1>DMR report: {title}</h1>
<p>{intro}</p>
<div class="stats">{stats}</div>

<h2>Volcano</h2>
<p>Each point is one CpG (cytosine followed by guanine) site. Left and right is the change in mean
beta (methylated reads over total reads) from normal to tumor; up is stronger evidence. Colored
points pass FDR (false discovery rate) &lt; {fdr}, meaning about {fdr_pct} of them are expected to
be false calls. {volcano_note}</p>
<div id="volcano" class="chart"></div>

<h2>DMRs (differentially methylated regions)</h2>
<p>Runs of at least {min_cg} nearby FDR (false discovery rate)-significant sites. Area statistic is
the sum of the sites' test statistics: its size ranks the regions, its sign gives the direction.
{table_note} Click a column header to sort, or a row to plot it below.</p>
<div class="wrap"><table id="dmrs"><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>
</div>

<h2>One DMR across patients</h2>
<p>Mean beta over the region's sites in each sample. Each line joins one patient's normal and
tumor, so a consistent change shows as lines that all slope the same way.</p>
<p><select id="pick"></select></p>
<div id="dmr" class="chart"></div>
</main>

<script id="data" type="application/json">{data}</script>
<script src="{plotly_js}"></script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const base = {{
  paper_bgcolor: "#fcfcfb", plot_bgcolor: "#fcfcfb", margin: {{t: 16, r: 16, b: 56, l: 64}},
  font: {{family: "-apple-system, Helvetica, Arial, sans-serif", size: 12, color: "#0b0b0b"}},
  hovermode: "closest", legend: {{orientation: "h", y: 1.08}},
}};
const axis = (extra) => Object.assign({{gridcolor: "#e4e3df", zeroline: false}}, extra);
const cfg = {{responsive: true, displaylogo: false}};
const pick = document.getElementById("pick");
D.dmrs.forEach(d => pick.add(new Option(d.dmr_id + "  " + d.chr + ":" + d.start.toLocaleString()
  + "  (" + d.n_cpg + " CpGs, diff " + d.diff.toFixed(2) + ")", d.dmr_id)));
function drawDmr(id) {{
  if (!window.Plotly) return;
  const rows = D.dmr_samples[id] || [];
  const patients = [...new Set(rows.map(r => r.patient))];
  const traces = patients.map(p => {{
    const pr = ["normal", "tumor"].map(t => rows.find(r => r.patient === p && r.tissue === t));
    return {{x: ["normal", "tumor"], y: pr.map(r => r && r.beta), type: "scatter",
      mode: "lines+markers", name: p, showlegend: false,
      line: {{color: "#c9c7c1", width: 1.5}},
      marker: {{size: 10, color: ["normal", "tumor"].map(t => D.colors[t])}},
      hovertemplate: p + " %{{x}}: beta %{{y:.2f}}<extra></extra>"}};
  }});
  Plotly.react("dmr", traces, Object.assign({{}}, base, {{
    xaxis: axis({{}}), yaxis: axis({{title: "Mean beta in region", range: [-0.03, 1.03]}})}}), cfg);
}}
pick.addEventListener("change", () => drawDmr(pick.value));
document.querySelectorAll("#dmrs tbody tr").forEach(tr => tr.addEventListener("click", () => {{
  pick.value = tr.dataset.id; drawDmr(tr.dataset.id);
  document.getElementById("dmr").scrollIntoView({{behavior: "smooth"}});
}}));
if (window.Plotly) {{
  const groups = [["sig_hyper", "higher in tumor", D.colors.hyper],
    ["sig_hypo", "lower in tumor", D.colors.hypo], ["background", "not significant", D.colors.ns]];
  Plotly.newPlot("volcano", groups.map(([k, name, color]) => ({{
    x: D.volcano[k].map(p => p[2]), y: D.volcano[k].map(p => p[3]),
    text: D.volcano[k].map(p => p[0] + ":" + p[1]), type: "scatter", mode: "markers", name,
    marker: {{size: 4, color, opacity: k === "background" ? 0.4 : 0.7}},
    hovertemplate: "%{{text}}<br>diff %{{x:.2f}}, -log10 p %{{y:.1f}}<extra></extra>",
  }})), Object.assign({{}}, base, {{
    xaxis: axis({{title: "Mean beta, tumor minus normal"}}),
    yaxis: axis({{title: "-log10 p-value"}}),
  }}), cfg);
  if (D.dmrs.length) drawDmr(D.dmrs[0].dmr_id);
}} else {{
  document.querySelectorAll(".chart").forEach(el => {{
    el.style.height = "auto";
    el.textContent = "Charts need a network connection to load Plotly.js.";
  }});
}}
document.querySelectorAll("#dmrs th").forEach((th, i) => th.addEventListener("click", () => {{
  const body = th.closest("table").tBodies[0];
  const up = th.dataset.dir !== "asc";
  th.parentNode.querySelectorAll("th").forEach(h => delete h.dataset.dir);
  th.dataset.dir = up ? "asc" : "desc";
  const key = (r) => {{ const v = r.cells[i].dataset.v; return isNaN(v) ? v : Number(v); }};
  [...body.rows].sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0) * (up ? 1 : -1))
    .forEach(r => body.appendChild(r));
}}));
</script>
</body>
</html>
"""

COLUMNS = [
    ("dmr_id", "DMR"),
    ("chr", "Chromosome"),
    ("start", "Start"),
    ("length", "Length (bp)"),
    ("n_cpg", "CpGs"),
    ("area_stat", "Area statistic"),
    ("beta_normal", "Normal beta"),
    ("beta_tumor", "Tumor beta"),
    ("diff", "Difference"),
]


def cell(field: str, value: str) -> str:
    if field in ("start", "length"):
        text = f"{int(float(value)):,}"
    elif field in ("area_stat",):
        text = f"{float(value):.1f}"
    elif field in ("beta_normal", "beta_tumor", "diff"):
        text = f"{float(value):+.2f}" if field == "diff" else f"{float(value):.2f}"
    else:
        text = value
    return f'<td data-v="{html.escape(value)}">{html.escape(text)}</td>'


def stat_box(value: str, label: str) -> str:
    return f'<div class="stat"><b>{html.escape(value)}</b><span>{html.escape(label)}</span></div>'


def significant_sites(dml: dict[str, np.ndarray], fdr: float) -> np.ndarray:
    return np.nan_to_num(dml["fdr"], nan=1.0) < fdr


def write_report(path, title, summary, dml, dmrs, by_dmr, seed=0):
    fdr = float(summary["fdr"])
    significant = significant_sites(dml, fdr)
    y = neg_log10(dml["pval"])

    def points(index):
        return [
            [
                str(dml["chr"][i]),
                int(dml["pos"][i]),
                round(float(dml["diff"][i]), 4),
                round(float(y[i]), 3),
            ]
            for i in index
        ]

    rng = np.random.default_rng(seed)
    groups = {
        "sig_hyper": np.flatnonzero(significant & (dml["stat"] > 0)),
        "sig_hypo": np.flatnonzero(significant & (dml["stat"] < 0)),
        "background": np.flatnonzero(~significant),
    }
    shown = {
        k: np.sort(rng.choice(v, min(VOLCANO_POINTS, len(v)), replace=False))
        for k, v in groups.items()
    }
    table = dmrs[:TABLE_ROWS]
    data = {
        "volcano": {k: points(v) for k, v in shown.items()},
        "dmrs": [
            {
                "dmr_id": d["dmr_id"],
                "chr": d["chr"],
                "start": int(float(d["start"])),
                "n_cpg": int(d["n_cpg"]),
                "diff": float(d["diff"]),
            }
            for d in table
        ],
        "dmr_samples": {
            d["dmr_id"]: [
                {"patient": p, "tissue": t, "beta": round(b, 4)}
                for p, pair in by_dmr[d["dmr_id"]].items()
                for t, b in pair.items()
            ]
            for d in table
        },
        "colors": {**TISSUE_COLORS, "hyper": HYPER, "hypo": HYPO, "ns": NOT_SIG},
    }
    # R writes the summary as one numeric column, so a large count can come out as "1e+06"
    count = {
        k: int(float(summary[k]))
        for k in ("sites_tested", "sites_significant", "sites_hyper", "sites_hypo")
        + ("dmrs", "dmrs_hyper", "dmrs_hypo", "min_reads", "min_cg")
    }
    n_dmrs = count["dmrs"]
    stats = "".join(
        [
            stat_box(
                f"{count['sites_tested']:,}",
                f"CpG sites tested, {count['min_reads']}+ reads in all",
            ),
            stat_box(
                f"{count['sites_significant']:,}",
                f"sites at FDR < {fdr:g} ({count['sites_hyper']:,} up, "
                f"{count['sites_hypo']:,} down in tumor)",
            ),
            stat_box(
                f"{n_dmrs:,}",
                f"DMRs ({count['dmrs_hyper']:,} up, {count['dmrs_hypo']:,} down)",
            ),
        ]
    )
    page = PAGE.format(
        title=html.escape(title),
        intro=html.escape(
            f"Tumor against matched normal in {summary['patients']} patients ({summary['samples']} "
            "samples), tested with DSS (Dispersion Shrinkage for Sequencing data). The model is "
            "~ patient + tissue: each tumor is compared with its own patient's normal, so "
            "differences between patients, including read layout, drop out of the test."
        ),
        stats=stats,
        fdr=f"{fdr:g}",
        fdr_pct=f"{fdr:.0%}",
        volcano_note=html.escape(
            "To keep the page light, it shows a random "
            + ", ".join(
                f"{len(shown[k]):,} of {len(groups[k]):,} {label}"
                for k, label in [
                    ("sig_hyper", "sites higher in tumor"),
                    ("sig_hypo", "lower in tumor"),
                    ("background", "not significant"),
                ]
            )
            + ". volcano.png plots every site."
        ),
        min_cg=count["min_cg"],
        table_note=html.escape(
            f"Showing the {len(table):,} strongest of {n_dmrs:,}." if n_dmrs > len(table) else ""
        ),
        header="".join(f"<th>{html.escape(label)}</th>" for _, label in COLUMNS),
        rows="".join(
            f'<tr data-id="{html.escape(d["dmr_id"])}">'
            + "".join(cell(f, d[f]) for f, _ in COLUMNS)
            + "</tr>"
            for d in table
        ),
        data=json.dumps(data).replace("</", "<\\/"),
        plotly_js=PLOTLY_JS,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dss", type=Path, required=True, help="r/run_dss.R output folder")
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--title", default="methyl-flow", help="report title, e.g. the run name")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    summary = read_summary(args.dss / "summary.tsv")
    dml = read_dml(args.dss / "dml.tsv.gz")
    dmrs = read_tsv(args.dss / "dmrs.tsv")
    by_dmr: dict[str, dict[str, dict[str, float]]] = {}
    for r in read_tsv(args.dss / "dmr_samples.tsv"):
        by_dmr.setdefault(r["dmr_id"], {}).setdefault(r["patient"], {})[r["tissue"]] = float(
            r["beta"]
        )

    fdr = float(summary["fdr"])
    significant = significant_sites(dml, fdr)
    log.info("%d sites, %d significant, %d DMRs", len(dml["pos"]), significant.sum(), len(dmrs))

    (args.out / "plots").mkdir(parents=True, exist_ok=True)
    plot_volcano(
        dml["diff"], dml["pval"], significant, dml["stat"], fdr, args.out / "plots" / "volcano.png"
    )
    if dmrs:
        plot_top_dmrs(dmrs, by_dmr, args.out / "plots" / "top_dmrs.png")
    write_report(args.out / "report.html", args.title, summary, dml, dmrs, by_dmr)


if __name__ == "__main__":
    main()
