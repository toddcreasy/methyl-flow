import csv
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from methyl_flow import plots


def test_pca_drops_incomplete_sites_and_finds_the_split():
    # Two samples per group differ at site 0; site 2 has a missing value
    matrix = np.array(
        [
            [0.1, 0.50, 0.2],
            [0.1, 0.52, np.nan],
            [0.9, 0.50, 0.7],
            [0.9, 0.48, 0.7],
        ]
    )
    scores, explained, n_sites = plots.pca(matrix)
    assert n_sites == 2
    assert scores.shape == (4, 2)
    assert explained[0] > 0.99
    # PC1 separates the groups (its sign is arbitrary)
    assert np.sign(scores[0, 0]) == np.sign(scores[1, 0]) != np.sign(scores[2, 0])


def test_main_writes_plots(monkeypatch, tmp_path):
    samples = tmp_path / "samples_qc.tsv"
    samples.write_text(
        "sample_id\tsample\tpatient\ttissue\tbatch\n"
        "GSM1\tP1_normal\tP1\tnormal\tpaired\n"
        "GSM2\tP1_tumor\tP1\ttumor\tpaired\n"
        "GSM3\tP2_normal\tP2\tnormal\tsingle\n"
    )
    hist = tmp_path / "coverage_hist.tsv"
    hist.write_text(
        "sample_id\tcoverage\tsites\n"
        + "".join(f"GSM{i}\t{c}\t{n}\n" for i in (1, 2, 3) for c, n in [(1, 5), (10, 3), (100, 1)])
    )
    betas = tmp_path / "GSE1.parquet"
    pq.write_table(
        pa.table(
            {
                "probe": ["chr1:1", "chr1:2", "chr1:3"],
                "GSM1": pa.array([0.1, 0.8, None], pa.float32()),
                "GSM2": pa.array([0.9, 0.7, 0.5], pa.float32()),
                "GSM3": pa.array([0.2, 0.9, 0.4], pa.float32()),
            }
        ),
        betas,
    )
    out = tmp_path / "plots"
    argv = ["plots", "--samples", str(samples), "--coverage-hist", str(hist)]
    argv += ["--betas", str(betas), "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    plots.main()

    for name in ["coverage.png", "methylation.png", "pca.png"]:
        assert (out / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    with (out / "pca.tsv").open() as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert [r["sample_id"] for r in rows] == ["GSM1", "GSM2", "GSM3"]
    assert sum(float(r["pc1"]) for r in rows) == pytest.approx(0, abs=1e-6)
