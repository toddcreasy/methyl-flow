"""QC plots from ``qc.py`` and ``convert.py`` output.

Writes to ``<out>``:
  coverage.png       share of each sample's CpG sites at each read count
  methylation.png    beta distribution per sample (sites passing the coverage filter)
  pca.png            PC1 and PC2 of the beta table, colored by tissue and by batch
  pca.tsv            the PC1 and PC2 scores behind pca.png

With ``--report``, also writes an interactive HTML version of all three (``report.py``).

PCA uses only sites with a beta in every sample, centered per site and not scaled.
"""

import argparse
import csv
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from methyl_flow.report import write_report  # noqa: E402

log = logging.getLogger(__name__)

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
# Categorical slots validated for light-surface CVD separation; batch avoids the tissue hues
TISSUE_COLORS = {"normal": "#2a78d6", "tumor": "#eb6834"}
BATCH_COLORS = {"paired": "#6250d6", "single": "#1baf7a"}
BATCH_MARKERS = {"paired": "o", "single": "^"}

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": TEXT,
        "axes.titlecolor": TEXT,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "font.size": 10,
    }
)


def pca(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """PC1 and PC2 scores, their share of variance, and the site count, for samples x sites.

    Drops sites with a missing value in any sample, then centers each site.
    """
    complete = matrix[:, ~np.isnan(matrix).any(axis=0)]
    centered = complete - complete.mean(axis=0)
    u, s, _ = np.linalg.svd(centered, full_matrices=False)
    explained = s**2 / (s**2).sum()
    return u[:, :2] * s[:2], explained[:2], complete.shape[1]


def legend_handles(colors: dict[str, str], markers: dict[str, str] | None = None) -> list:
    return [
        plt.Line2D([], [], color=c, marker=(markers or {}).get(k, "o"), linestyle="", label=k)
        for k, c in colors.items()
    ]


def plot_coverage(samples, hist, min_coverage, max_bin, path):
    fig, ax = plt.subplots(figsize=(7, 4))
    for s in samples:
        rows = hist[s["sample_id"]]
        total = sum(n for _, n in rows)
        ax.plot(
            [c for c, _ in rows],
            [n / total for _, n in rows],
            color=TISSUE_COLORS[s["tissue"]],
            linewidth=1.2,
            alpha=0.75,
        )
    ax.axvline(min_coverage, color=TEXT_SECONDARY, linestyle="--", linewidth=1)
    ax.annotate(
        f"{min_coverage}-read cutoff",
        (min_coverage, 1),
        xycoords=("data", "axes fraction"),
        xytext=(4, -12),
        textcoords="offset points",
        color=TEXT_SECONDARY,
    )
    ax.set_xscale("log")
    ax.set_xlabel(f"Reads per CpG site (last point is {max_bin} or more)")
    ax.set_ylabel("Share of the sample's sites")
    ax.set_title("Coverage per sample")
    ax.legend(handles=legend_handles(TISSUE_COLORS), loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_methylation(samples, matrix, path):
    bins = np.linspace(0, 1, 26)
    fig, ax = plt.subplots(figsize=(7, 4))
    for s, betas in zip(samples, matrix, strict=True):
        density, _ = np.histogram(betas[~np.isnan(betas)], bins=bins, density=True)
        ax.stairs(density, bins, color=TISSUE_COLORS[s["tissue"]], linewidth=1.2, alpha=0.75)
    ax.set_xlabel("Beta value (methylated reads / total reads)")
    ax.set_ylabel("Density")
    ax.set_title("Methylation per sample")
    ax.legend(handles=legend_handles(TISSUE_COLORS), loc="upper center")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_pca(samples, scores, explained, n_sites, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharex=True, sharey=True)
    for ax, key, colors in [
        (axes[0], "tissue", TISSUE_COLORS),
        (axes[1], "batch", BATCH_COLORS),
    ]:
        for s, (x, y) in zip(samples, scores, strict=True):
            ax.scatter(
                x,
                y,
                s=64,
                color=colors[s[key]],
                marker=BATCH_MARKERS[s["batch"]],
                edgecolor=SURFACE,
                linewidth=1.5,
                zorder=3,
            )
            ax.annotate(
                s["patient"],
                (x, y),
                xytext=(5, 4),
                textcoords="offset points",
                fontsize=8,
                color=TEXT_SECONDARY,
            )
        ax.set_xlabel(f"PC1 ({explained[0]:.0%} of variance)")
        ax.set_title(f"Colored by {key}")
        ax.legend(handles=legend_handles(colors, BATCH_MARKERS if key == "batch" else None))
    axes[0].set_ylabel(f"PC2 ({explained[1]:.0%} of variance)")
    fig.suptitle(f"PCA of beta values, {n_sites:,} CpG sites covered in every sample")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True, help="qc.py samples_qc.tsv")
    parser.add_argument("--coverage-hist", type=Path, required=True, help="qc.py output")
    parser.add_argument("--betas", type=Path, required=True, help="convert.py parquet")
    parser.add_argument("--min-coverage", type=int, default=10)
    parser.add_argument("--max-bin", type=int, default=100)
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, help="also write an interactive HTML report here")
    parser.add_argument("--title", default="methyl-flow", help="report title, e.g. the run name")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with args.samples.open() as f:
        samples = list(csv.DictReader(f, delimiter="\t"))
    hist = {s["sample_id"]: [] for s in samples}
    with args.coverage_hist.open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            hist[r["sample_id"]].append((int(r["coverage"]), int(r["sites"])))

    ids = [s["sample_id"] for s in samples]
    table = pq.read_table(args.betas, columns=ids)
    matrix = np.vstack([table[i].to_numpy(zero_copy_only=False) for i in ids]).astype(float)
    scores, explained, n_sites = pca(matrix)
    log.info("PCA on %d sites: PC1 %.3f, PC2 %.3f", n_sites, *explained)

    args.out.mkdir(parents=True, exist_ok=True)
    plot_coverage(samples, hist, args.min_coverage, args.max_bin, args.out / "coverage.png")
    plot_methylation(samples, matrix, args.out / "methylation.png")
    plot_pca(samples, scores, explained, n_sites, args.out / "pca.png")
    with (args.out / "pca.tsv").open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["sample_id", "sample", "tissue", "batch", "pc1", "pc2"])
        for s, (x, y) in zip(samples, scores, strict=True):
            writer.writerow([s["sample_id"], s["sample"], s["tissue"], s["batch"], x, y])
    if args.report:
        write_report(
            args.report,
            args.title,
            samples,
            hist,
            matrix,
            scores,
            explained,
            n_sites,
            args.min_coverage,
            args.max_bin,
            {"tissue": TISSUE_COLORS, "batch": BATCH_COLORS},
            BATCH_MARKERS,
        )


if __name__ == "__main__":
    main()
