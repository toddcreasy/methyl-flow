"""Annotate DSS results with genes, promoters, and CpG island context.

Reads the DSS step's ``dml.tsv.gz`` (tested sites) and ``dmrs.tsv``, a GENCODE GTF, and UCSC's
``cpgIslandExt.txt.gz``, and writes to ``--out``:
  dmrs_annotated.tsv          each DMR plus its CpG context, promoter overlap, nearest
                              protein-coding gene, and signed distance to that gene's TSS
  annotation_enrichment.tsv   share of sites in each feature, per group, and fold change against
                              all tested sites

Definitions (all positions 1-based, inclusive):
- TSS: start of each protein-coding transcript, strand-aware.
- promoter: within PROMOTER_BP of a protein-coding TSS, either side.
- gene body: inside a protein-coding gene, not in a promoter. Everything else is intergenic.
- CpG context: island; shore within SHORE_BP of an island; shelf within SHELF_BP; else open sea.

Groups compare like with like: every group is a set of tested CpG sites. RRBS already
over-samples CpG islands, so fold change is against the tested sites, not the genome.
"""

import argparse
import csv
import gzip
import hashlib
import logging
import re
from pathlib import Path

import numpy as np
import pyarrow.compute as pc
import pyarrow.csv as pacsv

log = logging.getLogger(__name__)

PROMOTER_BP = 1_000
SHORE_BP = 2_000
SHELF_BP = 4_000

CPG_CONTEXTS = ["island", "shore", "shelf", "open_sea"]
GENIC_CONTEXTS = ["promoter", "gene_body", "intergenic"]

ATTRIBUTE = re.compile(r'(\w+) "([^"]*)"')


def md5(path: Path, decompress: bool = False) -> str:
    """MD5 of a file, or of its decompressed content when ``decompress`` is set."""
    digest = hashlib.md5()
    with gzip.open(path, "rb") if decompress else path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_md5(path: Path, expected: str, decompress: bool = False) -> None:
    actual = md5(path, decompress)
    if actual != expected:
        raise ValueError(f"{path.name}: MD5 {actual}, expected {expected}")


def read_cpg_islands(path: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """UCSC cpgIslandExt (0-based start, end exclusive) as 1-based inclusive starts and ends."""
    spans: dict[str, list[tuple[int, int]]] = {}
    with gzip.open(path, "rt") as f:
        for row in csv.reader(f, delimiter="\t"):
            spans.setdefault(row[1], []).append((int(row[2]) + 1, int(row[3])))
    return {c: tuple(np.array(x) for x in zip(*sorted(v), strict=True)) for c, v in spans.items()}


def read_genes(path: Path) -> tuple[dict, dict]:
    """Protein-coding TSSs and merged gene spans per chromosome, from a GENCODE GTF.

    Returns ``tss[chrom] = (positions, gene names, strands)`` sorted by position, and
    ``genes[chrom] = (starts, ends)`` with overlapping genes merged.
    """
    tss: dict[str, list[tuple[int, str, str]]] = {}
    genes: dict[str, list[tuple[int, int]]] = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            chrom, _, feature, start, end, _, strand, _, attrs = line.rstrip("\n").split("\t")
            if feature not in ("gene", "transcript") or '"protein_coding"' not in attrs:
                continue
            a = dict(ATTRIBUTE.findall(attrs))
            if feature == "gene" and a.get("gene_type") == "protein_coding":
                genes.setdefault(chrom, []).append((int(start), int(end)))
            elif feature == "transcript" and a.get("transcript_type") == "protein_coding":
                position = int(start) if strand == "+" else int(end)
                tss.setdefault(chrom, []).append((position, a["gene_name"], strand))
    tss_out = {}
    for chrom, rows in tss.items():
        rows = sorted(set(rows))
        tss_out[chrom] = (
            np.array([r[0] for r in rows]),
            np.array([r[1] for r in rows]),
            np.array([r[2] for r in rows]),
        )
    genes_out = {}
    for chrom, spans in genes.items():
        merged: list[list[int]] = []
        for s, e in sorted(spans):
            if merged and s <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        genes_out[chrom] = (np.array([m[0] for m in merged]), np.array([m[1] for m in merged]))
    return tss_out, genes_out


def distance_to_spans(starts, ends, lo, hi) -> np.ndarray:
    """Distance from each query interval [lo, hi] to the nearest span; 0 if they overlap.

    ``starts`` and ``ends`` are sorted, non-overlapping spans. A point is lo == hi.
    """
    lo, hi = np.asarray(lo), np.asarray(hi)
    if len(starts) == 0:
        return np.full(len(lo), np.iinfo(np.int64).max)
    i = np.searchsorted(starts, hi, side="right") - 1
    has_left = i >= 0
    left_end = np.where(has_left, ends[np.clip(i, 0, None)], np.iinfo(np.int64).min // 2)
    overlap = has_left & (left_end >= lo)
    left = np.where(has_left, lo - left_end, np.iinfo(np.int64).max)
    j = i + 1
    has_right = j < len(starts)
    right = np.where(
        has_right, starts[np.clip(j, None, len(starts) - 1)] - hi, np.iinfo(np.int64).max
    )
    return np.where(overlap, 0, np.minimum(left, right))


def cpg_context(distance: np.ndarray) -> np.ndarray:
    return np.select(
        [distance == 0, distance <= SHORE_BP, distance <= SHELF_BP],
        ["island", "shore", "shelf"],
        "open_sea",
    )


def nearest_tss(positions, names, strands, lo, hi):
    """Nearest TSS to each interval [lo, hi]: gene name, and distance signed by the gene's strand.

    Negative means the interval is upstream of the TSS, positive downstream, 0 if it contains it.
    """
    lo, hi = np.asarray(lo), np.asarray(hi)
    n = len(positions)
    if n == 0:
        return np.full(len(lo), ""), np.zeros(len(lo), dtype=np.int64)
    inside = np.searchsorted(positions, lo, side="left")
    contains = (inside < n) & (positions[np.clip(inside, None, n - 1)] <= hi)
    left_i = np.clip(inside - 1, 0, None)
    right_i = np.clip(inside, None, n - 1)
    left_d = np.where(inside > 0, lo - positions[left_i], np.iinfo(np.int64).max)
    right_d = np.where(inside < n, positions[right_i] - hi, np.iinfo(np.int64).max)
    pick = np.where(contains, right_i, np.where(left_d <= right_d, left_i, right_i))
    # Interval right of the TSS is downstream on + and upstream on -, and the reverse on the left
    offset = np.where(contains, 0, np.where(left_d <= right_d, left_d, -right_d))
    signed = np.where(strands[pick] == "+", offset, -offset)
    return names[pick], signed


def annotate_sites(chrom, pos, islands, tss, genes):
    """CpG context and genic context for sites on one chromosome."""
    starts, ends = islands.get(chrom, (np.array([]), np.array([])))
    context = cpg_context(distance_to_spans(starts, ends, pos, pos))
    t = tss.get(chrom, (np.array([]), np.array([]), np.array([])))[0]
    tss_distance = distance_to_spans(t, t, pos, pos)
    gs, ge = genes.get(chrom, (np.array([]), np.array([])))
    in_gene = distance_to_spans(gs, ge, pos, pos) == 0
    genic = np.where(
        tss_distance <= PROMOTER_BP, "promoter", np.where(in_gene, "gene_body", "intergenic")
    )
    return context, genic


def annotate_dmrs(dmrs: list[dict], islands, tss) -> list[dict]:
    out = []
    by_chrom: dict[str, list[dict]] = {}
    for d in dmrs:
        by_chrom.setdefault(d["chr"], []).append(d)
    for chrom, rows in by_chrom.items():
        lo = np.array([int(r["start"]) for r in rows])
        hi = np.array([int(r["end"]) for r in rows])
        starts, ends = islands.get(chrom, (np.array([]), np.array([])))
        context = cpg_context(distance_to_spans(starts, ends, lo, hi))
        positions, names, strands = tss.get(chrom, (np.array([]), np.array([]), np.array([])))
        gene, signed = nearest_tss(positions, names, strands, lo, hi)
        for r, c, g, s in zip(rows, context, gene, signed, strict=True):
            out.append(
                {
                    **r,
                    "cpg_context": str(c),
                    "promoter": bool(g) and abs(int(s)) <= PROMOTER_BP,
                    "nearest_gene": str(g),
                    "tss_distance": int(s) if g else "",
                }
            )
    order = {d["dmr_id"]: i for i, d in enumerate(dmrs)}
    return sorted(out, key=lambda r: order[r["dmr_id"]])


def enrichment(dml, dmrs, islands, tss, genes, fdr: float) -> list[dict]:
    """Share of sites per feature for each group, and fold change against all tested sites."""
    chrom = np.array(dml["chr"].to_pylist())
    pos = dml["pos"].to_numpy()
    stat = pc.cast(dml["stat"], "float64").to_numpy(zero_copy_only=False)
    sig = np.nan_to_num(pc.cast(dml["fdr"], "float64").to_numpy(zero_copy_only=False), nan=1) < fdr
    context = np.empty(len(pos), dtype=object)
    genic = np.empty(len(pos), dtype=object)
    dmr_dir = np.zeros(len(pos), dtype=np.int8)
    for c in np.unique(chrom):
        idx = np.flatnonzero(chrom == c)
        context[idx], genic[idx] = annotate_sites(c, pos[idx], islands, tss, genes)
        # dml.tsv.gz is sorted by position within each chromosome
        for d in (d for d in dmrs if d["chr"] == c):
            first = np.searchsorted(pos[idx], int(d["start"]), side="left")
            last = np.searchsorted(pos[idx], int(d["end"]), side="right")
            dmr_dir[idx[first:last]] = 1 if float(d["area_stat"]) > 0 else -1
    groups = {
        "tested": np.ones(len(pos), dtype=bool),
        "significant_hyper": sig & (stat > 0),
        "significant_hypo": sig & (stat < 0),
        "dmr_hyper": dmr_dir == 1,
        "dmr_hypo": dmr_dir == -1,
    }
    base = {}
    rows = []
    for group, mask in groups.items():
        n = int(mask.sum())
        for feature in CPG_CONTEXTS + GENIC_CONTEXTS:
            labels = context if feature in CPG_CONTEXTS else genic
            share = float((labels[mask] == feature).mean()) if n else 0.0
            if group == "tested":
                base[feature] = share
            fold = share / base[feature] if base[feature] else float("nan")
            rows.append(
                {
                    "group": group,
                    "sites": n,
                    "feature": feature,
                    "share": round(share, 4),
                    "fold_vs_tested": round(fold, 3),
                }
            )
    return rows


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dss", type=Path, required=True, help="r/run_dss.R output folder")
    parser.add_argument("--gtf", type=Path, required=True, help="GENCODE GTF, gzipped")
    parser.add_argument("--gtf-md5", required=True)
    parser.add_argument("--cpg-islands", type=Path, required=True, help="UCSC cpgIslandExt.txt.gz")
    # UCSC's mirrors serve this file compressed at different times, so the gzip header (and the
    # file's MD5) varies while the content doesn't; check the content instead.
    parser.add_argument("--cpg-islands-content-md5", required=True, help="MD5 after gunzip")
    parser.add_argument("--fdr", type=float, default=0.05)
    parser.add_argument("--out", type=Path, default=Path("."))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    check_md5(args.gtf, args.gtf_md5)
    check_md5(args.cpg_islands, args.cpg_islands_content_md5, decompress=True)
    islands = read_cpg_islands(args.cpg_islands)
    tss, genes = read_genes(args.gtf)
    log.info(
        "%d CpG islands, %d protein-coding TSSs",
        sum(len(s) for s, _ in islands.values()),
        sum(len(t[0]) for t in tss.values()),
    )

    with (args.dss / "dmrs.tsv").open(newline="") as f:
        dmrs = list(csv.DictReader(f, delimiter="\t"))
    dml = pacsv.read_csv(args.dss / "dml.tsv.gz", parse_options=pacsv.ParseOptions(delimiter="\t"))

    args.out.mkdir(parents=True, exist_ok=True)
    annotated = annotate_dmrs(dmrs, islands, tss)
    fields = list(dmrs[0]) if dmrs else ["dmr_id", "chr", "start", "end"]
    fields += ["cpg_context", "promoter", "nearest_gene", "tss_distance"]
    write_tsv(args.out / "dmrs_annotated.tsv", annotated, fields)
    rows = enrichment(dml, dmrs, islands, tss, genes, args.fdr)
    write_tsv(
        args.out / "annotation_enrichment.tsv",
        rows,
        ["group", "sites", "feature", "share", "fold_vs_tested"],
    )
    for r in rows:
        if r["feature"] in ("island", "open_sea", "promoter"):
            log.info(
                "%s %s: %.1f%% (x%.2f)",
                r["group"],
                r["feature"],
                100 * r["share"],
                r["fold_vs_tested"],
            )


if __name__ == "__main__":
    main()
