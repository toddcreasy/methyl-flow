"""The release footer on the results site's pages: license, source, release version, and date.

``scripts/publish_site.sh`` runs this on the pages this repo generates (the hub, the QC (quality
control) report, and the DMR (differentially methylated region) report) as it builds the site:

    python -m methyl_flow.site_footer --released-at 2026-11-25T23:42:00Z \\
        [--repo-url https://github.com/owner/repo] page.html ...

The version is the installed package's, which comes from ``version`` in ``pyproject.toml``, the
one place a release bumps it. The page shows the date in UTC (Coordinated Universal Time); a few
lines of script rewrite it in the visitor's own locale and timezone. The license and source links
appear only with ``--repo-url``, which ``publish_site.sh`` passes only while the repo is public,
as for the hub's other source links. Stamping a page twice replaces the footer instead of adding
a second one.
"""

import argparse
import html
import logging
import re
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path

log = logging.getLogger(__name__)

START, END = "<!-- release-footer -->", "<!-- /release-footer -->"
BLOCK = re.compile(re.escape(START) + ".*?" + re.escape(END) + "\n?", re.DOTALL)
# Found in the page itself: lowercasing first can change the string's length (U+0130 becomes two
# code points) and shift the offset into the middle of the tag.
BODY_END = re.compile(r"</body\s*>", re.IGNORECASE)

# Each page has its own stylesheet, so the footer carries its own style. Every page defines --muted.
STYLE = (
    "max-width:1000px;margin:0 auto;padding:8px 16px 40px;color:var(--muted,#52606d);"
    "font:14px/1.5 system-ui,-apple-system,sans-serif;display:flex;flex-wrap:wrap;gap:4px 12px"
)
# Both links leave the site, so they open in a new tab, as in the other projects' footers.
LINK = 'target="_blank" rel="noopener noreferrer" style="color:inherit;text-underline-offset:3px"'
DOT = '<span aria-hidden="true" style="font-weight:700;color:var(--text,#1f2933)">&middot;</span>'
LOCAL_DATE = """<script>
for (const t of document.querySelectorAll("time.released")) {
  const d = new Date(t.dateTime);
  if (!isNaN(d)) t.textContent = d.toLocaleDateString(undefined,
    {year: "numeric", month: "long", day: "numeric"});
}
</script>"""


def version() -> str:
    return package_version("methyl-flow")


def footer(version: str, released_at: datetime, repo_url: str = "") -> str:
    when = released_at.astimezone(UTC)
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    utc_date = f"{when:%B} {when.day}, {when.year}"
    parts = []
    if repo_url:
        repo = html.escape(repo_url.rstrip("/"), quote=True)
        parts += [
            f'<a href="{repo}/blob/main/LICENSE" {LINK}>Apache 2.0 license</a>',
            f'<a href="{repo}" {LINK}>Source on GitHub</a>',
        ]
    parts += [
        f"<span>Release Version {html.escape(version)}</span>",
        f'<time class="released" datetime="{iso}" title="{iso} UTC (Coordinated Universal Time)">'
        f"{utc_date}</time>",
    ]
    return (
        f'{START}\n<footer class="release" style="{STYLE}">\n'
        + f"\n{DOT}\n".join(parts)
        + f"\n</footer>\n{LOCAL_DATE}\n{END}\n"
    )


def stamp(page: str, block: str) -> str:
    """The page with ``block`` just before ``</body>``, replacing any earlier release footer."""
    page = BLOCK.sub("", page)
    ends = list(BODY_END.finditer(page))
    if not ends:
        raise ValueError("page has no </body>")
    at = ends[-1].start()
    return page[:at] + block + page[at:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--released-at",
        required=True,
        help="publish time, ISO (International Organization for Standardization) 8601 with zone",
    )
    parser.add_argument(
        "--repo-url",
        default="",
        help="public GitHub repo URL (Uniform Resource Locator), for the links",
    )
    parser.add_argument("pages", nargs="+", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    released_at = datetime.fromisoformat(args.released_at)
    if released_at.tzinfo is None:
        parser.error("--released-at needs a timezone, e.g. 2026-11-25T23:42:00Z")
    block = footer(version(), released_at, args.repo_url)
    for page in args.pages:
        page.write_text(stamp(page.read_text(), block))
        log.info("footer: %s", page)


if __name__ == "__main__":
    main()
