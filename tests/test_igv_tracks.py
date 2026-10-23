import csv
import gzip
import json
import sys

from methyl_flow import igv_tracks

DMR_FIELDS = [
    "dmr_id",
    "chr",
    "start",
    "end",
    "length",
    "n_cpg",
    "area_stat",
    "beta_normal",
    "beta_tumor",
    "diff",
    "cpg_context",
    "promoter",
    "nearest_gene",
    "tss_distance",
]


def dmr(i, chrom, start, end, area):
    return dict(
        zip(
            DMR_FIELDS,
            [f"DMR{i:04d}", chrom, start, end, end - start + 1, 5, area, 0.2, 0.7, 0.5,
             "island", "True", f"G{i}", -100],
            strict=True,
        )
    )  # fmt: skip


def test_pick_dmrs_takes_strongest_per_direction_in_genome_order():
    dmrs = [
        dmr(1, "chr2", 500, 600, 50),
        dmr(2, "chr10", 100, 200, 40),
        dmr(3, "chr1", 900, 999, 10),
        dmr(4, "chr1", 100, 200, -60),
        dmr(5, "chr1", 300, 400, -5),
    ]
    picked = igv_tracks.pick_dmrs(dmrs, per_direction=2)
    # Top 2 up (DMR1, DMR2) and top 2 down (DMR4, DMR5), chr1 < chr2 < chr10
    assert [d["dmr_id"] for d in picked] == ["DMR0004", "DMR0005", "DMR0001", "DMR0002"]


def test_windows_merge_overlapping_flanks():
    picked = [dmr(1, "chr1", 1000, 1100, 5), dmr(2, "chr1", 3000, 3100, 5)]
    assert igv_tracks.windows(picked, flank=1000) == {"chr1": [(0, 4100)]}
    assert igv_tracks.windows(picked, flank=500) == {"chr1": [(500, 1600), (2500, 3600)]}


def test_main_writes_tracks_cut_to_windows(monkeypatch, tmp_path):
    dss = tmp_path / "dss"
    dss.mkdir()
    dmrs = [dmr(1, "chr1", 10_000, 10_100, 30), dmr(2, "chr1", 90_000, 90_100, -20)]
    with (dss / "dmrs_annotated.tsv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DMR_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(dmrs)
    with gzip.open(dss / "dml.tsv.gz", "wt") as f:
        f.write("chr\tpos\tstat\tpval\tfdr\tbeta_normal\tbeta_tumor\tdiff\n")
        for pos in (10_050, 11_000, 50_000, 90_050):
            f.write(f"chr1\t{pos}\t1\t0.01\t0.01\t0.2\t0.7\t0.5\n")
    islands = tmp_path / "cpgIslandExt.txt.gz"
    with gzip.open(islands, "wt") as f:
        f.write("1\tchr1\t9999\t10500\tCpG: 50\t501\t50\t300\t20\t60\t0.9\n")
        f.write("1\tchr1\t60000\t60500\tCpG: 50\t500\t50\t300\t20\t60\t0.9\n")
    gtf = tmp_path / "genes.gtf.gz"
    attrs = 'gene_id "g"; transcript_id "t{0}"; transcript_type "{1}"; gene_name "G{0}";'
    with gzip.open(gtf, "wt") as f:
        f.write("##format: gtf\n")
        f.write(
            f"chr1\tH\ttranscript\t10200\t20000\t.\t+\t.\t{attrs.format(1, 'protein_coding')}\n"
        )
        f.write(f"chr1\tH\texon\t10200\t10400\t.\t+\t.\t{attrs.format(1, 'protein_coding')}\n")
        f.write(f"chr1\tH\ttranscript\t10200\t11000\t.\t+\t.\t{attrs.format(2, 'lncRNA')}\n")
        f.write(
            f"chr1\tH\ttranscript\t50000\t52000\t.\t+\t.\t{attrs.format(3, 'protein_coding')}\n"
        )
    out = tmp_path / "out"
    argv = ["igv_tracks", "--dss", str(dss), "--gtf", str(gtf), "--cpg-islands", str(islands)]
    argv += ["--flank", "2000", "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    igv_tracks.main()

    with (out / "sites.tsv").open() as f:
        sites = list(csv.DictReader(f, delimiter="\t"))
    assert [s["dmr_id"] for s in sites] == ["DMR0001", "DMR0002"]
    assert sites[0]["direction"] == "higher in tumor" and sites[1]["direction"] == "lower in tumor"
    # 50,000 is outside both windows; bedGraph is 0-based
    assert (out / "tumor.bedgraph").read_text().splitlines() == [
        "chr1\t10049\t10050\t0.7000",
        "chr1\t10999\t11000\t0.7000",
        "chr1\t90049\t90050\t0.7000",
    ]
    assert (out / "cpg_islands.bed").read_text() == "chr1\t9999\t10500\tCpG: 50\n"
    assert (out / "dmrs_hyper.bed").read_text() == "chr1\t9999\t10100\tDMR0001 +0.50\n"
    assert (out / "dmrs_hypo.bed").read_text() == "chr1\t89999\t90100\tDMR0002 +0.50\n"
    # Only the protein-coding transcript that touches a window, with its exon
    assert len((out / "genes.gtf").read_text().splitlines()) == 2
    names = [t["name"] for t in json.loads((out / "tracks.json").read_text())]
    assert names[0] == "Normal, mean beta" and len(names) == 6
