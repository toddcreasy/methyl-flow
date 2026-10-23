"""Track files for an igv-reports view of the strongest DMRs.

Reads ``dml.tsv.gz`` and ``dmrs_annotated.tsv`` from ``--dss``, a GENCODE GTF, and UCSC's
``cpgIslandExt.txt.gz``, and writes to ``--out``:
  sites.tsv           the DMRs to show, one per row, 1-based, with their annotation
  normal.bedgraph     mean beta in normal tissue at each tested CpG site
  tumor.bedgraph      mean beta in tumor at each tested CpG site
  dmrs_hyper.bed      DMRs higher in tumor
  dmrs_hypo.bed       DMRs lower in tumor
  cpg_islands.bed     UCSC CpG islands
  genes.gtf           protein-coding GENCODE transcripts
  tracks.json         igv.js track settings for create_report --track-config

Every track is cut down to the windows igv-reports shows (each DMR plus FLANK_BP either side),
which keeps the report small. The GTF and island file were checksum-checked by annotate.py in the
same pipeline run.
"""

import argparse
import csv
import gzip
import json
import logging
from pathlib import Path

import numpy as np
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from methyl_flow.dmr_report import HYPER, HYPO
from methyl_flow.plots import TISSUE_COLORS

log = logging.getLogger(__name__)

FLANK_BP = 2_000
PER_DIRECTION = 25

SITE_FIELDS = [
    "chrom",
    "start",
    "end",
    "dmr_id",
    "direction",
    "nearest_gene",
    "tss_distance",
    "cpg_context",
    "n_cpg",
    "beta_normal",
    "beta_tumor",
    "diff",
]


def pick_dmrs(dmrs: list[dict], per_direction: int) -> list[dict]:
    """The strongest DMRs in each direction, by absolute area statistic, in genome order."""
    picked = []
    for sign in (1, -1):
        same = [d for d in dmrs if np.sign(float(d["area_stat"])) == sign]
        picked += sorted(same, key=lambda d: -abs(float(d["area_stat"])))[:per_direction]
    chrom_order = {f"chr{c}": i for i, c in enumerate([*range(1, 23), "X", "Y"])}
    return sorted(picked, key=lambda d: (chrom_order.get(d["chr"], 99), int(d["start"])))


def windows(picked: list[dict], flank: int) -> dict[str, list[tuple[int, int]]]:
    """Merged 1-based windows per chromosome around the picked DMRs."""
    out: dict[str, list[list[int]]] = {}
    for d in picked:
        out.setdefault(d["chr"], []).append([int(d["start"]) - flank, int(d["end"]) + flank])
    merged = {}
    for chrom, spans in out.items():
        rows: list[list[int]] = []
        for s, e in sorted(spans):
            if rows and s <= rows[-1][1]:
                rows[-1][1] = max(rows[-1][1], e)
            else:
                rows.append([s, e])
        merged[chrom] = [(s, e) for s, e in rows]
    return merged


def overlaps(win: dict, chrom: str, start: int, end: int) -> bool:
    return any(s <= end and start <= e for s, e in win.get(chrom, []))


def write_bedgraphs(dml_path: Path, win: dict, out: Path) -> int:
    table = pacsv.read_csv(dml_path, parse_options=pacsv.ParseOptions(delimiter="\t"))
    chrom = np.array(table["chr"].to_pylist())
    pos = table["pos"].to_numpy()
    keep = np.zeros(len(pos), dtype=bool)
    for c, spans in win.items():
        on = chrom == c
        for s, e in spans:
            keep |= on & (pos >= s) & (pos <= e)
    idx = np.flatnonzero(keep)
    for tissue in ("normal", "tumor"):
        values = pc.cast(table[f"beta_{tissue}"], "float64").to_numpy(zero_copy_only=False)
        with (out / f"{tissue}.bedgraph").open("w") as f:
            f.writelines(f"{chrom[i]}\t{pos[i] - 1}\t{pos[i]}\t{values[i]:.4f}\n" for i in idx)
    return len(idx)


def write_dmr_beds(dmrs: list[dict], win: dict, out: Path) -> None:
    """One BED per direction: igv.js ignores BED item colors here, so each track gets one color."""
    with (out / "dmrs_hyper.bed").open("w") as hyper, (out / "dmrs_hypo.bed").open("w") as hypo:
        for d in dmrs:
            start, end = int(d["start"]), int(d["end"])
            if overlaps(win, d["chr"], start, end):
                f = hyper if float(d["area_stat"]) > 0 else hypo
                f.write(f"{d['chr']}\t{start - 1}\t{end}\t{d['dmr_id']} {float(d['diff']):+.2f}\n")


def write_island_bed(path_in: Path, win: dict, path_out: Path) -> None:
    """UCSC rows are already 0-based, end exclusive, which is BED."""
    with gzip.open(path_in, "rt") as f, path_out.open("w") as out:
        for row in csv.reader(f, delimiter="\t"):
            chrom, start, end = row[1], int(row[2]), int(row[3])
            if overlaps(win, chrom, start + 1, end):
                out.write(f"{chrom}\t{start}\t{end}\t{row[4]}\n")


def write_genes(gtf: Path, win: dict, path: Path) -> int:
    """GTF lines of protein-coding transcripts that touch a window (transcripts, exons, CDS)."""
    n = 0
    with gzip.open(gtf, "rt") as f, path.open("w") as out:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.split("\t", 8)
            if fields[2] not in ("transcript", "exon", "CDS", "UTR"):
                continue
            if 'transcript_type "protein_coding"' not in fields[8]:
                continue
            if overlaps(win, fields[0], int(fields[3]), int(fields[4])):
                out.write(line)
                n += 1
    return n


def track_config() -> list[dict]:
    beta = {"type": "wig", "format": "bedgraph", "min": 0, "max": 1, "autoscale": False}
    return [
        {"name": "Normal, mean beta", "url": "normal.bedgraph", "color": TISSUE_COLORS["normal"],
         "height": 60, **beta},
        {"name": "Tumor, mean beta", "url": "tumor.bedgraph", "color": TISSUE_COLORS["tumor"],
         "height": 60, **beta},
        {"name": "DMRs, higher in tumor", "url": "dmrs_hyper.bed", "type": "annotation",
         "format": "bed", "color": HYPER, "height": 30},
        {"name": "DMRs, lower in tumor", "url": "dmrs_hypo.bed", "type": "annotation",
         "format": "bed", "color": HYPO, "height": 30},
        {"name": "CpG islands (UCSC)", "url": "cpg_islands.bed", "type": "annotation",
         "format": "bed", "color": "#1d4e89", "height": 30},
        {"name": "Genes (GENCODE 50, protein-coding)", "url": "genes.gtf", "type": "annotation",
         "format": "gtf", "displayMode": "COLLAPSED", "height": 60},
    ]  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dss", type=Path, required=True, help="folder with dml.tsv.gz and dmrs_annotated.tsv"
    )
    parser.add_argument("--gtf", type=Path, required=True)
    parser.add_argument("--cpg-islands", type=Path, required=True)
    parser.add_argument("--per-direction", type=int, default=PER_DIRECTION)
    parser.add_argument("--flank", type=int, default=FLANK_BP)
    parser.add_argument("--out", type=Path, default=Path("."))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with (args.dss / "dmrs_annotated.tsv").open(newline="") as f:
        dmrs = list(csv.DictReader(f, delimiter="\t"))
    picked = pick_dmrs(dmrs, args.per_direction)
    win = windows(picked, args.flank)
    args.out.mkdir(parents=True, exist_ok=True)

    with (args.out / "sites.tsv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SITE_FIELDS, delimiter="\t")
        writer.writeheader()
        for d in picked:
            writer.writerow(
                {
                    "chrom": d["chr"],
                    **{k: d[k] for k in ("start", "end", "dmr_id", "nearest_gene", "tss_distance")},
                    "direction": "higher in tumor"
                    if float(d["area_stat"]) > 0
                    else "lower in tumor",
                    "cpg_context": d["cpg_context"].replace("_", " "),
                    "n_cpg": d["n_cpg"],
                    **{k: f"{float(d[k]):.2f}" for k in ("beta_normal", "beta_tumor", "diff")},
                }
            )
    sites = write_bedgraphs(args.dss / "dml.tsv.gz", win, args.out)
    write_dmr_beds(dmrs, win, args.out)
    write_island_bed(args.cpg_islands, win, args.out / "cpg_islands.bed")
    gene_lines = write_genes(args.gtf, win, args.out / "genes.gtf")
    (args.out / "tracks.json").write_text(json.dumps(track_config(), indent=2) + "\n")
    log.info(
        "%d DMRs, %d tested sites, %d gene lines in the windows", len(picked), sites, gene_lines
    )


if __name__ == "__main__":
    main()
