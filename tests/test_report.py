import json
import re

import numpy as np

from methyl_flow import report

ROW = {
    "patient": "P1",
    "batch": "paired",
    "duplicate_rate": "0.7",
    "cpg_sites": "1000",
    "median_coverage": "5.0",
    "sites_min_coverage": "250",
    "fraction_min_coverage": "0.25",
}


def write(tmp_path, samples):
    path = tmp_path / "report.html"
    matrix = np.array([[0.1, 0.9, np.nan], [0.2, 0.8, 0.5]])
    report.write_report(
        path,
        "run_1",
        samples,
        {s["sample_id"]: [(1, 3), (10, 1)] for s in samples},
        matrix,
        np.array([[1.0, 0.5], [-1.0, -0.5]]),
        np.array([0.8, 0.2]),
        2,
        10,
        100,
        {"tissue": {"normal": "#2a78d6", "tumor": "#eb6834"}, "batch": {"paired": "#6250d6"}},
        {"paired": "o"},
    )
    page = path.read_text()
    data = json.loads(re.search(r'<script id="data"[^>]*>(.*?)</script>', page, re.S)[1])
    return page, data


def test_report_embeds_table_and_chart_data(tmp_path):
    samples = [
        {
            **ROW,
            "sample_id": "GSM1",
            "sample": "P1_normal",
            "tissue": "normal",
            "conversion_rate": "0.995",
        },
        {
            **ROW,
            "sample_id": "GSM2",
            "sample": "P1_tumor",
            "tissue": "tumor",
            "conversion_rate": "0.98",
        },
    ]
    page, data = write(tmp_path, samples)

    assert "2 samples (1 normal, 1 tumor)" in page
    assert '<td data-v="0.995">99.50%</td>' in page
    # Only the conversion below 99% is flagged
    assert page.count('class="flag"') == 1
    assert '<td data-v="0.98" class="flag">98.00%</td>' in page
    assert data["coverage"]["GSM1"] == {"x": [1, 10], "y": [0.75, 0.25]}
    assert len(data["methylation"]["GSM1"]) == len(data["beta_mids"]) == 25
    assert data["pca"]["GSM2"] == [-1.0, -0.5]
    assert data["explained"] == ["80%", "20%"]
    assert data["symbols"] == {"paired": "circle"}
    assert report.PLOTLY_JS in page


def test_report_escapes_sample_names(tmp_path):
    name = "</script><b>x"
    samples = [
        {
            **ROW,
            "sample_id": "GSM1",
            "sample": name,
            "tissue": "normal",
            "conversion_rate": "0.995",
        },
        {**ROW, "sample_id": "GSM2", "sample": "ok", "tissue": "tumor", "conversion_rate": "0.995"},
    ]
    page, data = write(tmp_path, samples)

    # Escaped in the table, and unable to close the JSON script block
    assert "&lt;/script&gt;&lt;b&gt;x" in page
    assert "</script><b>" not in page
    assert data["samples"][0]["sample"] == name
