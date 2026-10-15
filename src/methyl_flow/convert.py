"""Convert Bismark coverage files into methyl-floor's shared format.

Writes ``<out>/samples.tsv`` (one row per sample, methyl-floor's sample sheet columns) and
``<out>/betas/<study>.parquet`` (one row per CpG cytosine, one float32 column per sample,
named by ``sample_id``). The ``probe`` column holds the site as ``chrom:position`` (1-based).

Bismark reports the two cytosines of a CpG, one per strand, at position p and p+1. They stay
separate rows: telling them apart needs the reference sequence. A beta is left missing where
a sample has fewer than ``--min-coverage`` reads at the site.

Runs on its own with only pyarrow installed, so a Nextflow task can call it as a script.
"""

import argparse
import csv
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

# Same columns, same order, as methyl-floor's load.SAMPLE_FIELDS
SAMPLE_FIELDS = [
    "sample_id",
    "source",
    "study",
    "beta_column",
    "tissue",
    "disease_state",
    "batch",
    "site",
    "patient",
    "sex",
    "age_years",
    "pipeline",
]

# Autosomes and sex chromosomes; drops chrM and the unplaced and unlocalized scaffolds
CHROMOSOMES = [f"chr{c}" for c in [*range(1, 23), "X", "Y"]]

COVERAGE_COLUMNS = ["chrom", "start", "end", "percent", "methylated", "unmethylated"]


def read_coverage(path: Path, min_coverage: int) -> pa.Table:
    """Read one ``.bismark.cov.gz`` file into chromosome index, position, and beta.

    Keeps sites on ``CHROMOSOMES`` with at least ``min_coverage`` reads.
    """
    table = pacsv.read_csv(
        path,
        read_options=pacsv.ReadOptions(column_names=COVERAGE_COLUMNS),
        parse_options=pacsv.ParseOptions(delimiter="\t"),
        convert_options=pacsv.ConvertOptions(
            include_columns=["chrom", "start", "methylated", "unmethylated"],
            column_types={
                "chrom": pa.string(),
                "start": pa.int64(),
                "methylated": pa.int64(),
                "unmethylated": pa.int64(),
            },
        ),
    )
    chrom = pc.index_in(table["chrom"], value_set=pa.array(CHROMOSOMES))
    total = pc.add(table["methylated"], table["unmethylated"])
    keep = pc.and_(pc.is_valid(chrom), pc.greater_equal(total, min_coverage))
    beta = pc.divide(pc.cast(table["methylated"], pa.float64()), pc.cast(total, pa.float64()))
    return pa.table(
        {
            "chrom": pc.cast(chrom, pa.int8()),
            "pos": table["start"],
            "beta": pc.cast(beta, pa.float32()),
        }
    ).filter(keep)


def match_coverage_files(paths: list[Path], samples: list[str]) -> dict[str, Path]:
    """Map each sample name to its coverage file.

    methylseq names each file after the sample (``P08_normal_1_val_1_bismark_bt2_pe...``).
    """
    matched = {}
    for sample in samples:
        hits = [p for p in paths if p.name.startswith(f"{sample}_")]
        if len(hits) != 1:
            raise ValueError(f"{sample}: expected one coverage file, found {len(hits)}")
        matched[sample] = hits[0]
    return matched


def merge_betas(tables: dict[str, pa.Table]) -> pa.Table:
    """Join per-sample tables into one site-by-sample table, sorted by chromosome and position.

    A site appears if any sample passed the coverage filter there; others are null.
    """
    merged = None
    for sample_id, table in tables.items():
        table = table.rename_columns(["chrom", "pos", sample_id])
        if merged is None:
            merged = table
        else:
            merged = merged.join(table, keys=["chrom", "pos"], join_type="full outer")
    merged = merged.sort_by([("chrom", "ascending"), ("pos", "ascending")])
    probe = pc.binary_join_element_wise(
        pc.take(pa.array(CHROMOSOMES), merged["chrom"]),
        pc.cast(merged["pos"], pa.string()),
        ":",
    )
    return pa.table({"probe": probe, **{s: merged[s] for s in tables}})


def sample_rows(manifest: Path, study: str, disease_state: str, pipeline: str) -> list[dict]:
    """Sample sheet rows from the run manifest (``config/<study>/runs.tsv``)."""
    with manifest.open() as f:
        return [
            {
                "sample_id": r["gsm"],
                "source": "SRA",
                "study": study,
                "beta_column": r["sample"],
                "tissue": r["group"],
                "disease_state": disease_state,
                "batch": r["layout"],
                "site": "",
                "patient": r["patient"],
                "sex": "",
                "age_years": "",
                "pipeline": pipeline,
            }
            for r in csv.DictReader(f, delimiter="\t")
        ]


def write_samples(rows: list[dict], path: Path) -> None:
    ids = [r["sample_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate sample_id in sample sheet")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLE_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage", type=Path, nargs="+", help="Bismark .cov.gz files")
    parser.add_argument("--manifest", type=Path, required=True, help="runs.tsv")
    parser.add_argument("--study", required=True)
    parser.add_argument("--disease-state", required=True)
    parser.add_argument("--pipeline", required=True, help="pipeline and version, for the sheet")
    parser.add_argument("--min-coverage", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("."))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rows = sample_rows(args.manifest, args.study, args.disease_state, args.pipeline)
    files = match_coverage_files(args.coverage, [r["beta_column"] for r in rows])
    tables = {}
    for r in rows:
        tables[r["sample_id"]] = read_coverage(files[r["beta_column"]], args.min_coverage)
        log.info(
            "%s (%s): %d sites at >= %d reads",
            r["beta_column"],
            r["sample_id"],
            tables[r["sample_id"]].num_rows,
            args.min_coverage,
        )

    betas = merge_betas(tables)
    (args.out / "betas").mkdir(parents=True, exist_ok=True)
    pq.write_table(betas, args.out / "betas" / f"{args.study}.parquet")
    write_samples(rows, args.out / "samples.tsv")
    log.info("%s: %d sites, %d samples", args.study, betas.num_rows, len(rows))


if __name__ == "__main__":
    main()
