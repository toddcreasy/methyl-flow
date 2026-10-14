# CLAUDE.md

## Explain before you act

The maintainer is using this project to learn bisulfite sequencing processing and differential
methylation analysis for MCED (multi-cancer early detection) bioinformatics. Before doing
anything, explain what you are about to do and why.

1. Before any change that edits files, adds a dependency, downloads data, runs the pipeline, or fits a model, say in plain language what the step is and why it comes next.
2. Define sequencing, methylation, and statistics terms the first time they come up (bisulfite conversion, read trimming, alignment, methylation calling, coverage, duplicate rate, beta value, CpG (a cytosine followed by a guanine) context, DMR (differentially methylated region), dispersion, multiple-testing correction, FDR (false discovery rate), batch effect). One or two sentences each, no stacked jargon.
3. Point to the code: file and function, e.g. `src/methyl_flow/convert.py:24`, so the maintainer can read along.
4. For every tool or library, say what job it does and why it was picked over the obvious alternative (for example, nf-core/methylseq over a hand-written Snakemake pipeline, or DSS (Dispersion Shrinkage for Sequencing data) over methylKit).
5. After a pipeline run, QC (quality control) summary, or differential methylation test, explain what the numbers mean and whether they are good: what a 99% bisulfite conversion rate implies, what coverage is enough to trust a CpG call, how many DMRs survive FDR (false discovery rate) correction and why.
6. This section overrides "skip preamble" and "no trailing summaries" below for sequencing, methylation, and statistics concepts and decisions. Routine steps (installs, lint fixes, commits, CI (continuous integration)) stay terse.
7. Spell out every acronym and abbreviation every time it appears, everywhere: chat replies, docs, reports, TODO.md, PR (pull request) descriptions, and commit messages. Not only the first time. Write the full term in parentheses right after it, for example RRBS (reduced representation bisulfite sequencing), WGBS (whole-genome bisulfite sequencing), SRA (Sequence Read Archive), IGV (Integrative Genomics Viewer), IDAT (Illumina's raw scanner file), MCED (multi-cancer early detection), CpG (a cytosine followed by a guanine). File formats, accession numbers (SRR, SRP, GSE), and tool names that are acronyms count too.

Python project template. Drop this file into a fresh repo, fill in the placeholders, and Claude
Code scaffolds the project in two phases, stopping for review after each.

## Project

Reproducible bisulfite sequencing processing with nf-core/methylseq, plus a conversion,
analysis, and visualization layer written on top of its output.

This is the upstream half of a two-project portfolio aimed at MCED (multi-cancer early
detection) bioinformatics roles. methyl-flow turns raw bisulfite reads into a beta table and
sample sheet; methyl-floor (sibling repo) turns beta tables into a detection limit. The shared
beta table format is the contract between them. Keep it independent work: no company names in
the repo.

### Core idea
- Processing: run nf-core/methylseq, don't write it. It handles read trimming, alignment with Bismark or bwa-meth (BWA is the Burrows-Wheeler Aligner), methylation calling, and a MultiQC (combined quality control) report. Don't rebuild aligners.
- Show reproducible use: pinned pipeline version, Docker (container software) profile, a sample sheet, and a params file checked into the repo.
- Convert: turn methylseq per-CpG (a cytosine followed by a guanine) coverage files into the shared beta table plus sample sheet that methyl-floor reads.
- Analyze: differential methylation between groups with DSS (Dispersion Shrinkage for Sequencing data), an R package. QC (quality control) summary of bisulfite conversion rate, coverage, and duplicate rate.
- Visualize: coverage and methylation distributions, PCA (principal component analysis) by group and batch, and DMR (differentially methylated region) plots. IGV (Integrative Genomics Viewer) tracks are optional.

### What the project must show
- A one-command, version-pinned methylseq run that works on the test profile and on a downsampled real dataset.
- A well-tested conversion step: unit tests on small fixture coverage files, plus a schema check that its output loads in methyl-floor.
- A QC summary table and the plots above, generated from pipeline output, not hand-edited.
- An honest limits section: downsampled data, small sample counts, RRBS (reduced representation bisulfite sequencing) covers only CpG-rich regions.

### Data
- Start with a small public RRBS (reduced representation bisulfite sequencing) or targeted bisulfite dataset from SRA (Sequence Read Archive). Not WGBS (whole-genome bisulfite sequencing); it needs far more compute and storage. Ten to twenty samples is plenty.
- No dataset accession has been verified yet. Check library strategy, organism, and group labels in the SRA (Sequence Read Archive) metadata before committing to one.

### Compute
- Run methylseq's test profile first, then a downsampled real set on the laptop. Move to cloud compute only if needed.
- Pipeline version: nf-core/methylseq 4.2.0 is the latest release (GitHub releases API, checked 2026-10-14). Re-check the release, the minimum Nextflow version, and the aligner options before pinning.

### Language split (decided 2026-10-14)
- Python for the conversion step, in `src/methyl_flow/`. Its output is the beta table methyl-floor reads, so it shares methyl-floor's language, tooling, and tests.
- R with DSS (Dispersion Shrinkage for Sequencing data) for differential methylation and DMR (differentially methylated region) calling. DSS models read counts per CpG (a cytosine followed by a guanine) with a beta-binomial model and shrinks the dispersion estimates, which holds up better than methylKit's defaults at small sample counts.
- The two halves talk through files on disk (the beta table and sample sheet), not by calling R from Python.
- R code lives in `analysis/`, outside `src/`, since the Python package does not import it. R package versions are pinned with renv.

### Order of work
1. methylseq test profile running locally with Docker (container software), version pinned.
2. Pick and download the dataset, downsample, write the sample sheet, run methylseq on it.
3. Conversion step to the shared beta table, with tests.
4. QC (quality control) summary and plots.
5. Differential methylation and DMR (differentially methylated region) plots.
6. Later, optional: array input path that preprocesses IDAT (Illumina's raw scanner file) files with SeSAMe or minfi (R packages for methylation arrays) into the same beta table format.

Keep scope small. A working version in 2 to 3 weeks beats an ambitious one that never ships.

## How Claude Code must use this file

1. Work through the setup phases in order. Never skip ahead.
2. Complete every checklist item in a phase, then run the STOP gate verification.
3. At each STOP gate: show the evidence (command output), mark the checkboxes done by editing this file, then wait for maintainer approval before starting the next phase.
4. If a phase fails, diagnose before retrying. Read the error, check assumptions, try a focused fix. Ask the maintainer only when genuinely stuck after investigation.
5. Every changed line must trace to a checklist item. No extra features, no speculative abstractions.
6. Once STOP gate 1 passes, delete the "Setup phases" section. The repo itself is the record.

## Operating rules

Direct. Evidence-first. Skip preamble.

### Writing style
- Never use em dashes or en dashes in any written output. Use commas, periods, semicolons, or restructure.
- Write in the maintainer's voice for all prose output. The voice profile is `~/.claude/rules/writing-voice.md`. Read it; do not edit it. No generic LLM prose.
- Keep all prose short and direct. State the point; skip "actually matters" style framing.

### Core protocol
- Evidence: read files before stating facts about them. Verify data claims against source.
- Action: default to implementation. Explain architecture decisions; act on details.
- Output: no trailing summaries after actions. The maintainer reads diffs directly.
- Safety: no force push. No `rm -rf`; use `trash`. Ask before bulk operations. Never commit secrets, API keys, or credentials.
- Comms: never send email, messages, or any external communication without showing a draft and getting explicit approval.
- Parallel: launch independent subagents in a single message when tasks are independent. Delegate mechanical exploration; preserve main context for decisions.

### Python
- Use `uv` for everything: `uv sync`, `uv run <cmd>`, `uv add <pkg>`. Never activate a venv manually; `uv run` handles it. Never use pip with `--break-system-packages`.
- Always `pyproject.toml`. Always a `.env.example` with every variable the app reads.
- Settings load through `pydantic-settings`. Secrets are `SecretStr`. Locally they come from `.env`; deployed they come from the host's secret store. `.env` is gitignored.

### Coding principles
- Don't add features, refactors, or improvements beyond what was asked.
- Don't add comments, docstrings, or type annotations to code you didn't change.
- No helpers or abstractions for one-time operations. Three similar lines beat a premature abstraction.
- Validate only at system boundaries (user input, external APIs). Trust internal code.
- When editing: match existing style, don't touch adjacent code, remove only what YOUR change made unused. Mention unrelated dead code; don't delete it.
- No OWASP top 10 vulnerabilities. Fix insecure code you wrote immediately.

## Toolchain

| Job | Tool | Why |
|---|---|---|
| Installs, envs, lockfile | uv | One fast tool replacing pip, venv, and poetry. Reproducible installs from `uv.lock`. |
| Build backend | `uv_build` | Native src-layout support; no setuptools config. |
| Lint + format | ruff | One binary, milliseconds, so checks never feel optional. |
| Tests | pytest | The standard runner. Every STOP gate needs a runnable proof. |
| Config | pydantic-settings | Typed settings from env vars; bad config fails at startup, not deep in a call. |
| Pre-commit | pre-commit | Runs ruff before each commit so broken code never lands. |
| CI | GitHub Actions | Lives beside the code, free tier covers a personal project. |
| Pipeline runner | Nextflow | The workflow manager MCED (multi-cancer early detection) teams run in production; resumes failed runs and swaps local or cloud executors by profile. |
| Bisulfite processing | nf-core/methylseq | Community-standard trimming, alignment, methylation calling, and MultiQC (combined quality control) report. Writing this by hand adds risk and shows nothing new. |
| Differential methylation | DSS (Dispersion Shrinkage for Sequencing data), R | Beta-binomial model with dispersion shrinkage, built for small bisulfite sequencing studies. methylKit is the common alternative. |
| R environment | renv | Lockfile for R packages, the R counterpart to `uv.lock`. |
| Containers | Docker | Pins every pipeline tool's exact build so runs reproduce on another machine. |

## Repository layout, and why

Every file and directory the Python template creates, what goes in it, and whether it is a real
convention or just a choice. The distinction matters: some of these have a technical reason and
breaking them causes real bugs. Others are habit, and you should feel free to disagree.

```
.
├── CLAUDE.md                 instructions the AI assistant reads every session
├── README.md                 instructions a human reads
├── pyproject.toml            project definition: dependencies, build, tool config
├── uv.lock                   exact versions, so every machine installs the same thing
├── .python-version           pins the interpreter
├── .env.example              every environment variable the app reads, with no values
├── .pre-commit-config.yaml   checks that run before each commit
├── src/methyl_flow/            the application code
├── tests/                    tests for it
├── scripts/                  one-shot operational scripts
├── docs/                     long-form documentation
└── .github/workflows/        CI: what runs on every push
```

### The ones with a real technical reason

#### `src/methyl_flow/` and why not just `methyl_flow/`

This is the **src layout**, and it is the current Python packaging recommendation.

The alternative, putting your package at the top level, has a subtle failure. When you run tests
from the project root, Python finds your package in the current directory and imports it from
there, whether or not the package is correctly installable. Packaging mistakes stay invisible
until someone installs it elsewhere and it breaks.

With `src/`, the current directory contains no importable package. `import myapp` only works if
the package is installed. Your tests therefore exercise the same thing your users get.

The `uv_build` backend expects this layout by default. Configuration is only needed when the
package name differs from the project name:

```toml
[tool.uv.build-backend]
module-name = "myapp"
```

**Verdict: real convention, adopt it.** The failure it prevents shows up at the worst possible
moment.

#### `tests/` outside `src/`

Tests sit beside the package, not inside it, so they are not shipped to whoever installs your
code. Nobody wants your test fixtures in their site-packages.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Verdict: real convention.** Both parts, the name and the position outside the package.

#### `pyproject.toml` and `uv.lock`

`pyproject.toml` is the single file describing the project: dependencies, build system, and
configuration for ruff and pytest. It replaced the older scatter of `setup.py`,
`setup.cfg`, `requirements.txt`, and per-tool config files. Keep tool config here; a stray
`pytest.ini` or `.flake8` splits the truth across two places.

`uv.lock` records the exact resolved version of every dependency, transitive ones included.
`pyproject.toml` says "roughly this"; the lock file says "precisely this". Commit both. CI runs
`uv sync --locked`, which fails if the two disagree instead of quietly re-resolving.

**Verdict: the standard. There is no live alternative.**

#### `.python-version`

One line naming the interpreter. uv reads it and installs that version if it is missing, so every
machine and the CI runner test against the same Python. `requires-python` in `pyproject.toml` is
the floor you promise users; `.python-version` is what you develop on.

**Verdict: real convention for applications.** A library tested across several versions leaves
the matrix to CI instead.

#### `.github/workflows/`

Not a choice at all. GitHub Actions only reads workflow files from this exact path. Put them
anywhere else and nothing runs.

**Verdict: mandatory.**

### The ones that are common convention

#### `.env.example`

A list of every environment variable the app reads, with the values blank. The real `.env` is
gitignored, so without this file a new clone has no way to know what configuration it needs
except by reading the settings code.

Keep it in step with the `pydantic-settings` class. A variable the app reads but this file omits
is a setup bug waiting for the next person.

**Verdict: common convention, and cheap enough to always do.**

#### `.pre-commit-config.yaml`

Runs ruff before each commit lands. The point is the fast feedback loop: a lint error caught at
commit time costs seconds, the same error caught in CI costs a push and a wait.

It does not replace CI. Hooks can be skipped with `--no-verify`, and CI cannot.

**Verdict: common convention. The filename is fixed by the tool.**

#### `scripts/`

One-shot operational tools: seed data, probe an API, run a migration by hand. Things a person
runs occasionally.

The line worth holding: if the application imports it, it belongs in `src/`. If it is only ever
run directly by a person, it belongs here. Scripts that quietly become dependencies are a common
source of mess.

**Verdict: common convention.**

#### `docs/`

Long-form documentation that does not belong in the README: architecture decisions, runbooks,
design notes.

A README should be readable in one sitting. Everything that would bloat it past that goes here,
and the README links across.

**Verdict: common convention.**

### The ones that are just choices

#### `.claude/` and `CLAUDE.md`

Configuration for the AI assistant: permission rules, hooks, project instructions. Tool-specific,
and it would disappear along with the tool.

**Verdict: a choice, and a temporary one.**

### Directories to add only when needed

The template leaves these out. Add each one the day the project needs it, not before.

| Directory | When it appears | Why it sits outside `src/` |
|---|---|---|
| `migrations/` | The project gets a database with a schema that changes | Schema history is not application code, and each file replays in order against any environment |
| `frontend/` | There is a web UI | Different language, tooling, and build. Same repo is the right default at small scale |
| `evals/` | The code calls an LLM | Evals hit a real model, so they are slow and cost money. The normal test suite has to stay fast |

### The general rule underneath all of this

Directories separate things by **lifecycle**, not by type.

Application code, tests, operational scripts, and documentation change for different reasons, on
different schedules, with different consequences when wrong. Keeping them apart means a change to
one does not force you to reason about the others.

That is also why `src/` contains only what ships. Everything outside it exists to build, test,
run, or explain the thing inside it.

## Conventions

- src layout. `import methyl_flow` works only when installed, so tests exercise what users get.
- Tool config lives in `pyproject.toml`. No `setup.cfg`, `pytest.ini`, or `.flake8`.
- Unit tests make no network calls. Anything that does is marked and skipped by default.
- Use `logging` in `src/`, never `print`. Configure handlers once at the entrypoint.
- Pin dependency lower bounds in `pyproject.toml`; `uv.lock` pins exact versions.

---

# Setup phases

## Phase 0: Scaffold

Goal: a clean repo that lints, tests, and installs from lockfile.

- [x] `uv init --package` with `pyproject.toml`: project metadata, `requires-python = ">=3.14"`, `uv_build` backend, `.python-version`
- [x] Dev deps via `uv add --dev`: `ruff`, `pytest`, `pre-commit`
- [x] `[tool.ruff]` config: line length, target version, lint rules (at least `E`, `F`, `I`, `B`, `UP`, `SIM`); format enabled
- [x] `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, a `network` marker skipped by default
- [x] `.pre-commit-config.yaml` with ruff lint and format hooks; `uv run pre-commit install`
- [x] Directory layout created as above, with `src/methyl_flow/__init__.py` and one passing test in `tests/`
- [x] `.gitignore` (Python, `.venv`, `.env`, caches, IDE (integrated development environment))
- [x] `.env.example` created (empty until the app reads a variable)
- [x] README: project name, one-line purpose, setup commands (`uv sync`, `uv run pytest`)
- [x] Initial commit pushed

STOP gate 0: show clean output from `uv run ruff check .`, `uv run ruff format --check .`,
and `uv run pytest`.

## Phase 1: CI (continuous integration)

Goal: every push and pull request runs the same three checks as the local gate.

- [ ] `.github/workflows/ci.yml`: on pull request and push to main, `astral-sh/setup-uv` with caching, `uv sync --locked`, then ruff check, ruff format check, pytest
- [ ] Concurrency group per ref with `cancel-in-progress: true`
- [ ] Branch protection on main: PR (pull request) plus passing CI (continuous integration) required, `enforce_admins` on or it will not stop the repo owner. Needs GitHub Pro on a private repo; the API (application programming interface) returns 403 on the free plan

STOP gate 1: open a trivial PR (pull request), show the green CI (continuous integration) run, merge it.
