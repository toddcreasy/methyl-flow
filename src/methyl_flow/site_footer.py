"""The release footer on the results site's pages: license, source, release version, and date.

``scripts/publish_site.sh`` runs this on the pages this repo generates (the hub, the QC (quality
control) report, and the DMR (differentially methylated region) report) as it builds the site:

    python -m methyl_flow.site_footer --released-at 2026-11-25T23:42:00Z \\
        [--repo-url https://github.com/owner/repo] page.html ...

The version comes from ``version`` in ``pyproject.toml``, the one place a release bumps it. The
page shows the date in UTC (Coordinated Universal Time); a few lines of script rewrite it in the
visitor's own locale and timezone. The license and source links appear only with ``--repo-url``,
which ``publish_site.sh`` passes only while the repo is public, as for the hub's other source
links. Stamping a page twice replaces the footer instead of adding a second one.
"""

import argparse
import html
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
START, END = "<!-- release-footer -->", "<!-- /release-footer -->"
BLOCK = re.compile(re.escape(START) + ".*?" + re.escape(END) + "\n?", re.DOTALL)

# Each page has its own stylesheet, so the footer carries its own style. Every page defines --muted.
STYLE = (
    "max-width:1000px;margin:0 auto;padding:8px 16px 40px;color:var(--muted,#52606d);"
    "font:14px/1.5 system-ui,-apple-system,sans-serif;display:flex;flex-wrap:wrap;gap:4px 12px"
)
DOT = '<span aria-hidden="true" style="font-weight:700;color:var(--text,#1f2933)">&middot;</span>'
LOCAL_DATE = """<script>
for (const t of document.querySelectorAll("time.released")) {
  const d = new Date(t.dateTime);
  if (!isNaN(d)) t.textContent = d.toLocaleDateString(undefined,
    {year: "numeric", month: "long", day: "numeric"});
}
</script>"""


def version(pyproject: Path = PYPROJECT) -> str:
    return tomllib.loads(pyproject.read_text())["project"]["version"]


def footer(version: str, released_at: datetime, repo_url: str = "") -> str:
    when = released_at.astimezone(UTC)
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    utc_date = f"{when:%B} {when.day}, {when.year}"
    parts = []
    if repo_url:
        repo = html.escape(repo_url.rstrip("/"), quote=True)
        link = 'style="color:inherit;text-underline-offset:3px"'
        parts += [
            f'<a href="{repo}/blob/main/LICENSE" {link}>Apache 2.0 license</a>',
            f'<a href="{repo}" {link}>Source on GitHub</a>',
        ]
    parts += [
        f"<span>Release Version {html.escape(version)}</span>",
        f'<time class="released" datetime="{iso}" title="{iso} (UTC)">{utc_date}</time>',
    ]
    return (
        f'{START}\n<footer class="release" style="{STYLE}">\n'
        + f"\n{DOT}\n".join(parts)
        + f"\n</footer>\n{LOCAL_DATE}\n{END}\n"
    )


def stamp(page: str, block: str) -> str:
    """The page with ``block`` just before ``</body>``, replacing any earlier release footer."""
    page = BLOCK.sub("", page)
    at = page.lower().rfind("</body>")
    if at == -1:
        raise ValueError("page has no </body>")
    return page[:at] + block + page[at:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--released-at", required=True, help="publish time, ISO 8601 with zone")
    parser.add_argument("--repo-url", default="", help="public GitHub repo URL, for the links")
    parser.add_argument("pages", nargs="+", type=Path)
    args = parser.parse_args()
    released_at = datetime.fromisoformat(args.released_at)
    if released_at.tzinfo is None:
        parser.error("--released-at needs a timezone, e.g. 2026-11-25T23:42:00Z")
    block = footer(version(), released_at, args.repo_url)
    for page in args.pages:
        page.write_text(stamp(page.read_text(), block))
        print("footer:", page)


if __name__ == "__main__":
    main()
