import csv
import gzip
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from methyl_flow import convert

# chrom, start, end, percent methylated, methylated reads, unmethylated reads
NORMAL = [
    ("chr10", 500, 500, 50.0, 5, 5),
    ("chr2", 300, 300, 90.0, 9, 1),
    ("chr2", 301, 301, 100.0, 3, 0),  # 3 reads: below min coverage
    ("KI270422.1", 234, 234, 100.0, 20, 0),  # unplaced scaffold
    ("chrM", 100, 100, 0.0, 0, 40),
]
TUMOR = [
    ("chr2", 300, 300, 25.0, 3, 9),
    ("chrX", 700, 700, 0.0, 0, 15),
]
MANIFEST = (
    "sample\tpatient\tgroup\tlayout\trun\tgsm\tread_count\n"
    "P1_normal\tP1\tnormal\tpaired\tSRR1\tGSM1\t100\n"
    "P1_tumor\tP1\ttumor\tpaired\tSRR2\tGSM2\t100\n"
)


def write_cov(path, rows):
    lines = "".join("\t".join(str(v) for v in row) + "\n" for row in rows)
    path.write_bytes(gzip.compress(lines.encode()))
    return path


@pytest.fixture
def inputs(tmp_path):
    normal = write_cov(tmp_path / "P1_normal_1_val_1_bismark_bt2_pe.bismark.cov.gz", NORMAL)
    tumor = write_cov(tmp_path / "P1_tumor_trimmed_bismark_bt2.bismark.cov.gz", TUMOR)
    manifest = tmp_path / "runs.tsv"
    manifest.write_text(MANIFEST)
    return normal, tumor, manifest


def test_read_coverage_filters_and_computes_beta(inputs):
    table = convert.read_coverage(inputs[0], min_coverage=10)
    chroms = [convert.CHROMOSOMES[i] for i in table["chrom"].to_pylist()]
    assert list(zip(chroms, table["pos"].to_pylist(), strict=True)) == [
        ("chr10", 500),
        ("chr2", 300),
    ]
    assert table["beta"].to_pylist() == pytest.approx([0.5, 0.9])
    assert table.schema.field("beta").type == pa.float32()


def test_min_coverage_is_inclusive(inputs):
    table = convert.read_coverage(inputs[0], min_coverage=3)
    assert 301 in table["pos"].to_pylist()


def test_match_coverage_files(inputs):
    normal, tumor, _ = inputs
    matched = convert.match_coverage_files([tumor, normal], ["P1_normal", "P1_tumor"])
    assert matched == {"P1_normal": normal, "P1_tumor": tumor}


def test_match_coverage_files_requires_every_sample(inputs):
    with pytest.raises(ValueError, match="P2_normal"):
        convert.match_coverage_files(list(inputs[:2]), ["P1_normal", "P2_normal"])


def test_match_coverage_files_does_not_match_longer_names(tmp_path):
    p10 = write_cov(tmp_path / "P10_normal_trimmed.bismark.cov.gz", NORMAL)
    with pytest.raises(ValueError):
        convert.match_coverage_files([p10], ["P1_normal"])


def test_merge_betas_takes_union_in_genome_order(inputs):
    tables = {
        "GSM1": convert.read_coverage(inputs[0], 10),
        "GSM2": convert.read_coverage(inputs[1], 10),
    }
    betas = convert.merge_betas(tables)
    assert betas.column_names == ["probe", "GSM1", "GSM2"]
    # Chromosome order, not text order: chr2 before chr10
    assert betas["probe"].to_pylist() == ["chr2:300", "chr10:500", "chrX:700"]
    assert betas["GSM1"].to_pylist() == pytest.approx([0.9, 0.5, None], nan_ok=True)
    assert betas["GSM2"].to_pylist() == pytest.approx([0.25, None, 0.0], nan_ok=True)


def test_write_samples_rejects_duplicate_ids(tmp_path):
    rows = [{"sample_id": "GSM1"}, {"sample_id": "GSM1"}]
    with pytest.raises(ValueError):
        convert.write_samples(rows, tmp_path / "samples.tsv")


def run_main(monkeypatch, inputs, out):
    normal, tumor, manifest = inputs
    argv = [
        "convert",
        str(normal),
        str(tumor),
        "--manifest",
        str(manifest),
        "--study",
        "GSE1",
        "--disease-state",
        "colorectal cancer",
        "--pipeline",
        "nf-core/methylseq 4.2.0",
        "--out",
        str(out),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    convert.main()


def test_main_writes_methyl_floor_layout(monkeypatch, inputs, tmp_path):
    out = tmp_path / "processed"
    run_main(monkeypatch, inputs, out)

    with (out / "samples.tsv").open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        assert reader.fieldnames == convert.SAMPLE_FIELDS
        rows = list(reader)
    assert [(r["sample_id"], r["tissue"], r["patient"], r["batch"]) for r in rows] == [
        ("GSM1", "normal", "P1", "paired"),
        ("GSM2", "tumor", "P1", "paired"),
    ]

    schema = pq.read_schema(out / "betas" / "GSE1.parquet")
    assert schema.names == ["probe", "GSM1", "GSM2"]
    assert schema.field("probe").type == pa.string()
    assert {schema.field(s).type for s in ["GSM1", "GSM2"]} == {pa.float32()}


def test_output_loads_in_methyl_floor(monkeypatch, inputs, tmp_path):
    """Schema check against methyl-floor itself. Skipped unless it is installed:
    uv run --with ../methyl-floor pytest"""
    load = pytest.importorskip("methyl_floor.load")
    probes = pytest.importorskip("methyl_floor.probes")
    import numpy as np

    assert convert.SAMPLE_FIELDS == load.SAMPLE_FIELDS

    out = tmp_path / "processed"
    run_main(monkeypatch, inputs, out)
    path = out / "betas" / "GSE1.parquet"
    assert probes.shared_probes([path]) == ["chr2:300", "chr10:500", "chrX:700"]
    ids, matrix = next(probes.iter_betas(path, ["chrX:700", "chr2:300"]))
    assert ids == ["GSM1", "GSM2"]
    np.testing.assert_allclose(matrix, [[np.nan, 0.0], [0.9, 0.25]], rtol=1e-6)
