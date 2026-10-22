"""Per-sample QC summary of a methylseq Bismark run.

Writes ``<out>/samples_qc.tsv`` (one row per sample) and ``<out>/coverage_hist.tsv`` (sites
per read count, per sample, for the coverage plot). Samples come from the ``samples.tsv``
that ``convert.py`` wrote, so the QC table and the beta table share sample IDs.

- conversion_rate: share of non-CpG cytosines (CHG and CHH contexts) read as converted, from
  Bismark's splitting report. Human non-CpG cytosines are almost never methylated, so the
  unconverted share estimates failed bisulfite conversion.
- duplicate_rate: 1 minus FastQC's deduplicated percentage, read-weighted across R1 and R2.
  methylseq skips deduplication in RRBS mode, and RRBS reads share MspI cut-site starts by
  design, so expect this to be high.
- coverage: reads per CpG cytosine on chr1 to chr22, chrX, chrY, from the coverage files.

Needs only pyarrow; ``convert`` must be importable next to it.
"""

import argparse
import csv
import logging
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from methyl_flow.convert import CHROMOSOMES, COVERAGE_COLUMNS, match_coverage_files

log = logging.getLogger(__name__)

QC_FIELDS = [
    "sample_id",
    "sample",
    "patient",
    "tissue",
    "batch",
    "conversion_rate",
    "duplicate_rate",
    "cpg_sites",
    "median_coverage",
    "sites_min_coverage",
    "fraction_min_coverage",
]

NON_CPG = ["CHG", "CHH"]

SPLITTING_LINE = re.compile(r"Total (methylated C's|C to T conversions) in (\w+) context:\t(\d+)")


def conversion_rate(path: Path) -> float:
    """Converted share of non-CpG cytosines in one Bismark splitting report."""
    counts = {}
    for line in path.read_text().splitlines():
        if m := SPLITTING_LINE.match(line):
            counts[m[1], m[2]] = int(m[3])
    if len(counts) != 6:
        raise ValueError(f"{path.name}: expected 6 context totals, found {len(counts)}")
    methylated = sum(counts["methylated C's", c] for c in NON_CPG)
    converted = sum(counts["C to T conversions", c] for c in NON_CPG)
    return converted / (methylated + converted)


def duplicate_rates(path: Path, samples: list[str]) -> dict[str, float]:
    """Duplicate rate per sample from MultiQC's ``multiqc_fastqc.txt``.

    Paired-end samples have two rows (``<sample>_1``, ``<sample>_2``), single-end one.
    """
    with path.open() as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    rates = {}
    for sample in samples:
        hits = [r for r in rows if r["Sample"] in (sample, f"{sample}_1", f"{sample}_2")]
        if len(hits) not in (1, 2):
            raise ValueError(f"{sample}: expected 1 or 2 FastQC rows, found {len(hits)}")
        reads = sum(float(r["Total Sequences"]) for r in hits)
        unique = sum(
            float(r["total_deduplicated_percentage"]) / 100 * float(r["Total Sequences"])
            for r in hits
        )
        rates[sample] = 1 - unique / reads
    return rates


def coverage_stats(path: Path, min_coverage: int, max_bin: int) -> tuple[dict, dict[int, int]]:
    """Coverage summary and histogram for one ``.bismark.cov.gz`` file.

    The histogram maps read count to number of sites; its ``max_bin`` holds every site with
    ``max_bin`` or more reads.
    """
    table = pacsv.read_csv(
        path,
        read_options=pacsv.ReadOptions(column_names=COVERAGE_COLUMNS),
        parse_options=pacsv.ParseOptions(delimiter="\t"),
        convert_options=pacsv.ConvertOptions(
            include_columns=["chrom", "methylated", "unmethylated"],
            column_types={
                "chrom": pa.string(),
                "methylated": pa.int64(),
                "unmethylated": pa.int64(),
            },
        ),
    )
    table = table.filter(pc.is_in(table["chrom"], value_set=pa.array(CHROMOSOMES)))
    total = pc.add(table["methylated"], table["unmethylated"])
    passing = pc.sum(pc.greater_equal(total, min_coverage)).as_py() or 0
    stats = {
        "cpg_sites": len(total),
        "median_coverage": pc.quantile(total, q=0.5)[0].as_py(),
        "sites_min_coverage": passing,
        "fraction_min_coverage": passing / len(total),
    }
    counts = pc.value_counts(pc.min_element_wise(total, max_bin))
    values, sites = counts.field("values").to_pylist(), counts.field("counts").to_pylist()
    hist = dict(sorted(zip(values, sites, strict=True)))
    return stats, hist


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True, help="convert.py samples.tsv")
    parser.add_argument("--splitting-reports", type=Path, nargs="+", required=True)
    parser.add_argument("--coverage", type=Path, nargs="+", required=True)
    parser.add_argument("--fastqc", type=Path, required=True, help="multiqc_fastqc.txt")
    parser.add_argument("--min-coverage", type=int, default=10)
    parser.add_argument("--max-bin", type=int, default=100)
    parser.add_argument("--out", type=Path, default=Path("."))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with args.samples.open() as f:
        samples = list(csv.DictReader(f, delimiter="\t"))
    names = [s["beta_column"] for s in samples]
    reports = match_coverage_files(args.splitting_reports, names)
    coverage = match_coverage_files(args.coverage, names)
    duplicates = duplicate_rates(args.fastqc, names)

    rows, hist_rows = [], []
    for s in samples:
        name = s["beta_column"]
        stats, hist = coverage_stats(coverage[name], args.min_coverage, args.max_bin)
        row = {
            "sample_id": s["sample_id"],
            "sample": name,
            "patient": s["patient"],
            "tissue": s["tissue"],
            "batch": s["batch"],
            "conversion_rate": round(conversion_rate(reports[name]), 5),
            "duplicate_rate": round(duplicates[name], 4),
            "cpg_sites": stats["cpg_sites"],
            "median_coverage": stats["median_coverage"],
            "sites_min_coverage": stats["sites_min_coverage"],
            "fraction_min_coverage": round(stats["fraction_min_coverage"], 4),
        }
        rows.append(row)
        hist_rows += [
            {"sample_id": s["sample_id"], "coverage": c, "sites": n} for c, n in hist.items()
        ]
        log.info(
            "%s: conversion %.4f, duplicates %.3f, %d of %d sites at >= %d reads",
            name,
            row["conversion_rate"],
            row["duplicate_rate"],
            row["sites_min_coverage"],
            row["cpg_sites"],
            args.min_coverage,
        )

    args.out.mkdir(parents=True, exist_ok=True)
    for path, fields, data in [
        (args.out / "samples_qc.tsv", QC_FIELDS, rows),
        (args.out / "coverage_hist.tsv", ["sample_id", "coverage", "sites"], hist_rows),
    ]:
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(data)


if __name__ == "__main__":
    main()
