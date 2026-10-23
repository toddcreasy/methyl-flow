import csv
import gzip
import sys

import pytest

from methyl_flow import qc

# Trimmed from a real Bismark v0.25.1 splitting report
SPLITTING = """P1_normal_1_val_1_bismark_bt2_pe.bam

Final Cytosine Methylation Report
=================================
Total number of C's analysed:\t1100

Total methylated C's in CpG context:\t60
Total methylated C's in CHG context:\t3
Total methylated C's in CHH context:\t7

Total C to T conversions in CpG context:\t40
Total C to T conversions in CHG context:\t297
Total C to T conversions in CHH context:\t693

C methylated in CpG context:\t60.0%
"""

FASTQC = (
    "Sample\tTotal Sequences\ttotal_deduplicated_percentage\n"
    "P1_normal_1\t100.0\t40.0\n"
    "P1_normal_2\t300.0\t60.0\n"
    "P1_tumor\t200.0\t50.0\n"
    "P10_normal\t200.0\t90.0\n"
)

# chrom, start, end, percent methylated, methylated reads, unmethylated reads
COVERAGE = [
    ("chr1", 100, 100, 50.0, 1, 1),  # 2 reads
    ("chr1", 101, 101, 50.0, 5, 5),  # 10
    ("chr2", 300, 300, 50.0, 60, 90),  # 150: capped into the top bin
    ("chrX", 700, 700, 0.0, 0, 4),  # 4
    ("KI270422.1", 234, 234, 100.0, 1, 0),  # unplaced scaffold: dropped
    ("chrM", 100, 100, 0.0, 0, 40),  # dropped
]

SAMPLES = (
    "sample_id\tbeta_column\tpatient\ttissue\tbatch\n"
    "GSM1\tP1_normal\tP1\tnormal\tpaired\n"
    "GSM2\tP1_tumor\tP1\ttumor\tsingle\n"
)


def write_cov(path, rows):
    lines = "".join("\t".join(str(v) for v in row) + "\n" for row in rows)
    path.write_bytes(gzip.compress(lines.encode()))
    return path


def test_conversion_rate_uses_non_cpg_contexts(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text(SPLITTING)
    # (297 + 693) converted of (3 + 7 + 297 + 693) non-CpG cytosines
    assert qc.conversion_rate(path) == pytest.approx(0.99)


def test_conversion_rate_rejects_truncated_report(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text(SPLITTING.split("Total C to T")[0])
    with pytest.raises(ValueError, match="report.txt"):
        qc.conversion_rate(path)


def test_duplicate_rates_weights_paired_reads(tmp_path):
    path = tmp_path / "multiqc_fastqc.txt"
    path.write_text(FASTQC)
    rates = qc.duplicate_rates(path, ["P1_normal", "P1_tumor"])
    # Paired: (40 + 180) unique of 400 reads
    assert rates["P1_normal"] == pytest.approx(1 - 220 / 400)
    assert rates["P1_tumor"] == pytest.approx(0.5)


def test_duplicate_rates_requires_every_sample(tmp_path):
    path = tmp_path / "multiqc_fastqc.txt"
    path.write_text(FASTQC)
    with pytest.raises(ValueError, match="P2_normal"):
        qc.duplicate_rates(path, ["P2_normal"])


def test_coverage_stats(tmp_path):
    path = write_cov(tmp_path / "P1_normal.bismark.cov.gz", COVERAGE)
    stats, hist = qc.coverage_stats(path, min_coverage=10, max_bin=100)
    assert stats == {
        "cpg_sites": 4,
        "median_coverage": pytest.approx(7.0),
        "sites_min_coverage": 2,
        "fraction_min_coverage": 0.5,
    }
    assert hist == {2: 1, 4: 1, 10: 1, 100: 1}


def test_main_writes_tables(monkeypatch, tmp_path):
    samples = tmp_path / "samples.tsv"
    samples.write_text(SAMPLES)
    fastqc = tmp_path / "multiqc_fastqc.txt"
    fastqc.write_text(FASTQC)
    reports, coverage = [], []
    for name in ["P1_normal_1_val_1_bismark_bt2_pe", "P1_tumor_trimmed_bismark_bt2"]:
        report = tmp_path / f"{name}_splitting_report.txt"
        report.write_text(SPLITTING)
        reports.append(str(report))
        coverage.append(str(write_cov(tmp_path / f"{name}.bismark.cov.gz", COVERAGE)))
    out = tmp_path / "qc"
    argv = ["qc", "--samples", str(samples), "--fastqc", str(fastqc), "--out", str(out)]
    argv += ["--splitting-reports", *reports, "--coverage", *coverage]
    monkeypatch.setattr(sys, "argv", argv)
    qc.main()

    with (out / "samples_qc.tsv").open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        assert reader.fieldnames == qc.QC_FIELDS
        rows = list(reader)
    assert [(r["sample_id"], r["sample"], r["tissue"], r["batch"]) for r in rows] == [
        ("GSM1", "P1_normal", "normal", "paired"),
        ("GSM2", "P1_tumor", "tumor", "single"),
    ]
    assert float(rows[0]["conversion_rate"]) == pytest.approx(0.99)
    assert rows[1]["sites_min_coverage"] == "2"

    with (out / "coverage_hist.tsv").open() as f:
        hist = list(csv.DictReader(f, delimiter="\t"))
    assert len(hist) == 8
    assert hist[0] == {"sample_id": "GSM1", "coverage": "2", "sites": "1"}
