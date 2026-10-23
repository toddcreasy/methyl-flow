import gzip
import json
import re
import sys

from methyl_flow import dmr_report

SUMMARY = {
    "samples": 4,
    "patients": 2,
    "min_reads": 5,
    "min_cg": 3,
    "sites_tested": 4,
    "fdr": 0.05,
    "p_threshold": 0.001,
    "sites_significant": 2,
    "sites_hyper": 1,
    "sites_hypo": 1,
    "dmrs": 1,
    "dmrs_hyper": 1,
    "dmrs_hypo": 0,
}


def write_dss(tmp_path, dmrs=True):
    d = tmp_path / "dss"
    d.mkdir()
    rows = [
        ("chr1", 100, 6.1, 1e-9, 0.001, 0.1, 0.9, 0.8),
        ("chr1", 120, -5.0, 1e-7, 0.01, 0.8, 0.2, -0.6),
        ("chr2", 50, 0.3, 0.7, 0.9, 0.5, 0.52, 0.02),
        # DSS can leave a site untested; fwrite writes the missing FDR as empty
        ("chr2", 90, 0.1, 0.9, "", 0.4, 0.41, 0.01),
    ]
    with gzip.open(d / "dml.tsv.gz", "wt") as f:
        f.write("chr\tpos\tstat\tpval\tfdr\tbeta_normal\tbeta_tumor\tdiff\n")
        f.writelines("\t".join(map(str, r)) + "\n" for r in rows)
    summary = dict(SUMMARY, dmrs=1 if dmrs else 0, dmrs_hyper=1 if dmrs else 0)
    (d / "summary.tsv").write_text(
        "metric\tvalue\n" + "".join(f"{k}\t{v}\n" for k, v in summary.items())
    )
    header = "dmr_id\tchr\tstart\tend\tlength\tn_cpg\tarea_stat\tbeta_normal\tbeta_tumor\tdiff\n"
    body = "DMR0001\tchr1\t100\t180\t81\t4\t21.5\t0.12\t0.85\t0.73\n" if dmrs else ""
    (d / "dmrs.tsv").write_text(header + body)
    samples = "sample\tdmr_id\tbeta\tsample_id\tpatient\ttissue\n"
    if dmrs:
        samples += "".join(
            f"{p}_{t}\tDMR0001\t{b}\tGSM{i}\t{p}\t{t}\n"
            for i, (p, t, b) in enumerate(
                [
                    ("P1", "normal", 0.1),
                    ("P1", "tumor", 0.9),
                    ("P2", "normal", 0.14),
                    ("P2", "tumor", 0.8),
                ]
            )
        )
    (d / "dmr_samples.tsv").write_text(samples)
    return d


def run(monkeypatch, tmp_path, dss):
    out = tmp_path / "out"
    argv = ["dmr_report", "--dss", str(dss), "--out", str(out), "--title", "dss_run"]
    monkeypatch.setattr(sys, "argv", argv)
    dmr_report.main()
    page = (out / "report.html").read_text()
    data = json.loads(re.search(r'<script id="data"[^>]*>(.*?)</script>', page, re.S)[1])
    return out, page, data


def test_report_and_plots(monkeypatch, tmp_path):
    out, page, data = run(monkeypatch, tmp_path, write_dss(tmp_path))

    for name in ["volcano.png", "top_dmrs.png"]:
        assert (out / "plots" / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "DMR report: dss_run" in page
    # Significant sites split by direction; the rest, including the untested one, are background
    assert [p[:2] for p in data["volcano"]["sig_hyper"]] == [["chr1", 100]]
    assert [p[:2] for p in data["volcano"]["sig_hypo"]] == [["chr1", 120]]
    assert sorted(p[1] for p in data["volcano"]["background"]) == [50, 90]
    assert data["volcano"]["sig_hyper"][0][3] == 9.0
    assert data["dmrs"] == [
        {"dmr_id": "DMR0001", "chr": "chr1", "start": 100, "n_cpg": 4, "diff": 0.73}
    ]
    assert {(r["patient"], r["tissue"]) for r in data["dmr_samples"]["DMR0001"]} == {
        ("P1", "normal"),
        ("P1", "tumor"),
        ("P2", "normal"),
        ("P2", "tumor"),
    }
    assert '<td data-v="0.73">+0.73</td>' in page


def test_no_dmrs(monkeypatch, tmp_path):
    out, page, data = run(monkeypatch, tmp_path, write_dss(tmp_path, dmrs=False))

    assert (out / "plots" / "volcano.png").exists()
    assert not (out / "plots" / "top_dmrs.png").exists()
    assert data["dmrs"] == []
