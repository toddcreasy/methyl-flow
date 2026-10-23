import csv
import gzip
import sys

import numpy as np
import pytest

from methyl_flow import annotate

# Gene A on +, TSS at 10,000; gene B on -, TSS at 50,000 (its end). A lncRNA is ignored.
GTF = [
    ("chr1", "gene", 10_000, 20_000, "+", 'gene_type "protein_coding"; gene_name "A";'),
    (
        "chr1",
        "transcript",
        10_000,
        20_000,
        "+",
        'gene_type "protein_coding"; gene_name "A"; transcript_type "protein_coding";',
    ),
    ("chr1", "gene", 40_000, 50_000, "-", 'gene_type "protein_coding"; gene_name "B";'),
    (
        "chr1",
        "transcript",
        40_000,
        50_000,
        "-",
        'gene_type "protein_coding"; gene_name "B"; transcript_type "protein_coding";',
    ),
    ("chr1", "gene", 70_000, 71_000, "+", 'gene_type "lncRNA"; gene_name "L";'),
]
# UCSC rows: bin, chrom, 0-based start, end (exclusive), name, ... Islands at 9,501-10,500 and
# 30,001-30,500 in 1-based inclusive coordinates.
ISLANDS = [
    ("585", "chr1", "9500", "10500", "CpG: 90", "1000", "90", "700", "18", "70", "0.8"),
    ("585", "chr1", "30000", "30500", "CpG: 40", "500", "40", "300", "16", "60", "0.7"),
]


def write_inputs(tmp_path):
    gtf = tmp_path / "genes.gtf.gz"
    with gzip.open(gtf, "wt") as f:
        f.write("##format: gtf\n")
        for chrom, feature, start, end, strand, attrs in GTF:
            f.write(f"{chrom}\tHAVANA\t{feature}\t{start}\t{end}\t.\t{strand}\t.\t{attrs}\n")
    islands = tmp_path / "cpgIslandExt.txt.gz"
    with gzip.open(islands, "wt") as f:
        f.writelines("\t".join(r) + "\n" for r in ISLANDS)
    return gtf, islands


def test_islands_become_one_based(tmp_path):
    _, path = write_inputs(tmp_path)
    starts, ends = annotate.read_cpg_islands(path)["chr1"]
    assert starts.tolist() == [9501, 30001]
    assert ends.tolist() == [10500, 30500]


def test_genes_keep_protein_coding_and_strand_aware_tss(tmp_path):
    gtf, _ = write_inputs(tmp_path)
    tss, genes = annotate.read_genes(gtf)
    positions, names, strands = tss["chr1"]
    assert positions.tolist() == [10_000, 50_000]
    assert names.tolist() == ["A", "B"]
    assert strands.tolist() == ["+", "-"]
    assert [a.tolist() for a in genes["chr1"]] == [[10_000, 40_000], [20_000, 50_000]]


def test_distance_and_cpg_context():
    starts, ends = np.array([9501, 30001]), np.array([10500, 30500])
    points = np.array([10_000, 10_501, 12_500, 12_501, 14_500, 14_501, 9_500])
    d = annotate.distance_to_spans(starts, ends, points, points)
    assert d.tolist() == [0, 1, 2000, 2001, 4000, 4001, 1]
    assert annotate.cpg_context(d).tolist() == [
        "island", "shore", "shore", "shelf", "shelf", "open_sea", "shore",
    ]  # fmt: skip
    # An interval overlapping an island's edge counts as island
    assert annotate.distance_to_spans(starts, ends, [10_400], [10_600]).tolist() == [0]


def test_nearest_tss_signs_by_strand():
    positions = np.array([10_000, 50_000])
    names, strands = np.array(["A", "B"]), np.array(["+", "-"])
    lo = np.array([9_500, 10_400, 9_900, 50_200, 49_000])
    hi = np.array([9_600, 10_500, 10_100, 50_300, 49_100])
    gene, signed = annotate.nearest_tss(positions, names, strands, lo, hi)
    assert gene.tolist() == ["A", "A", "A", "B", "B"]
    # Upstream of A (+), downstream of A, contains A, upstream of B (-), downstream of B
    assert signed.tolist() == [-400, 400, 0, -200, 900]


def test_main_annotates_dmrs_and_measures_enrichment(monkeypatch, tmp_path):
    gtf, islands = write_inputs(tmp_path)
    dss = tmp_path / "dss"
    dss.mkdir()
    # Ten tested sites: 4 in the A island, 2 in the shore, 4 in open sea
    sites = [9_600, 9_700, 9_800, 9_900, 11_000, 11_500, 25_000, 25_100, 60_000, 60_100]
    sig_hyper = {9_600, 9_700, 9_800, 9_900}
    sig_hypo = {25_000, 25_100}
    with gzip.open(dss / "dml.tsv.gz", "wt") as f:
        f.write("chr\tpos\tstat\tpval\tfdr\tbeta_normal\tbeta_tumor\tdiff\n")
        for p in sites:
            stat, fdr = (
                (5, 0.001) if p in sig_hyper else (-5, 0.001) if p in sig_hypo else (0.1, 0.9)
            )
            f.write(f"chr1\t{p}\t{stat}\t0.5\t{fdr}\t0.5\t0.5\t0\n")
    header = "dmr_id\tchr\tstart\tend\tlength\tn_cpg\tarea_stat\tbeta_normal\tbeta_tumor\tdiff\n"
    (dss / "dmrs.tsv").write_text(
        header
        + "DMR0001\tchr1\t9600\t9900\t301\t4\t20\t0.1\t0.7\t0.6\n"
        + "DMR0002\tchr1\t25000\t25100\t101\t2\t-10\t0.8\t0.3\t-0.5\n"
    )
    out = tmp_path / "out"
    argv = ["annotate", "--dss", str(dss), "--gtf", str(gtf), "--cpg-islands", str(islands)]
    argv += ["--gtf-md5", annotate.md5(gtf)]
    argv += ["--cpg-islands-content-md5", annotate.md5(islands, decompress=True)]
    argv += ["--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    annotate.main()

    with (out / "dmrs_annotated.tsv").open() as f:
        dmrs = list(csv.DictReader(f, delimiter="\t"))
    assert [d["dmr_id"] for d in dmrs] == ["DMR0001", "DMR0002"]
    assert dmrs[0]["cpg_context"] == "island"
    assert dmrs[0]["promoter"] == "True" and dmrs[0]["nearest_gene"] == "A"
    assert dmrs[0]["tss_distance"] == "-100"
    assert dmrs[1]["cpg_context"] == "open_sea"
    # Nearest TSS is A's at 10,000 (B's is 24,900 away), and the DMR is downstream of it
    assert dmrs[1]["nearest_gene"] == "A" and dmrs[1]["tss_distance"] == "15000"
    assert dmrs[1]["promoter"] == "False"

    with (out / "annotation_enrichment.tsv").open() as f:
        rows = {(r["group"], r["feature"]): r for r in csv.DictReader(f, delimiter="\t")}
    assert rows[("tested", "island")]["share"] == "0.4"
    assert rows[("dmr_hyper", "island")]["sites"] == "4"
    assert rows[("dmr_hyper", "island")]["share"] == "1.0"
    assert rows[("dmr_hyper", "island")]["fold_vs_tested"] == "2.5"
    assert rows[("dmr_hypo", "open_sea")]["fold_vs_tested"] == "2.5"
    assert rows[("significant_hyper", "promoter")]["share"] == "1.0"
    # Promoter: the 4 island sites and 11,000 (exactly 1,000 from A's TSS); gene body: 11,500
    assert rows[("tested", "promoter")]["share"] == "0.5"
    assert rows[("tested", "gene_body")]["share"] == "0.1"
    assert rows[("tested", "intergenic")]["share"] == "0.4"


def test_wrong_checksum_is_rejected(tmp_path):
    gtf, _ = write_inputs(tmp_path)
    with pytest.raises(ValueError, match="expected 0000"):
        annotate.check_md5(gtf, "0000")


def test_content_md5_ignores_gzip_header(tmp_path):
    # Same content compressed with different header timestamps, as UCSC's mirrors serve it
    a, b = tmp_path / "a.gz", tmp_path / "b.gz"
    a.write_bytes(gzip.compress(b"chr1\t1\t2\n", mtime=1))
    b.write_bytes(gzip.compress(b"chr1\t1\t2\n", mtime=2))
    assert annotate.md5(a) != annotate.md5(b)
    assert annotate.md5(a, decompress=True) == annotate.md5(b, decompress=True)
