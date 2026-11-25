from datetime import UTC, datetime, timedelta, timezone

import pytest

from methyl_flow import site_footer

WHEN = datetime(2026, 11, 26, 0, 42, tzinfo=UTC)
PAGE = "<html><body><main>results</main></body></html>"
REPO = "https://github.com/owner/methyl-flow"


def test_version_comes_from_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    assert site_footer.version(pyproject) == "1.2.3"
    assert site_footer.version() == site_footer.version(site_footer.PYPROJECT)


def test_footer_reads_license_source_release_date():
    block = site_footer.footer("0.1.0", WHEN, REPO + "/")
    text = [
        "Apache 2.0 license",
        "Source on GitHub",
        "Release Version 0.1.0",
        "November 26, 2026",
    ]
    positions = [block.index(t) for t in text]
    assert positions == sorted(positions)
    assert block.count("&middot;") == 3
    assert f'href="{REPO}/blob/main/LICENSE"' in block
    assert f'href="{REPO}"' in block
    assert 'datetime="2026-11-26T00:42:00Z"' in block


def test_footer_date_is_utc_without_script():
    # 7:42 PM in New York on November 25 is already November 26 in UTC.
    eastern = WHEN.astimezone(timezone(timedelta(hours=-5)))
    block = site_footer.footer("0.1.0", eastern, REPO)
    assert ">November 26, 2026</time>" in block
    assert 'datetime="2026-11-26T00:42:00Z"' in block


def test_footer_without_repo_has_no_source_links():
    block = site_footer.footer("0.1.0", WHEN)
    assert "github" not in block.lower()
    assert "license" not in block.lower()
    assert block.count("&middot;") == 1


def test_stamp_goes_before_body_and_replaces_an_earlier_footer():
    first = site_footer.stamp(PAGE, site_footer.footer("0.1.0", WHEN, REPO))
    assert first.index("</main>") < first.index("Release Version") < first.index("</body>")
    again = site_footer.stamp(first, site_footer.footer("0.2.0", WHEN, REPO))
    assert again.count(site_footer.START) == 1
    assert "Release Version 0.2.0" in again
    assert "0.1.0" not in again


def test_stamp_needs_a_body():
    with pytest.raises(ValueError):
        site_footer.stamp("<html></html>", site_footer.footer("0.1.0", WHEN))
