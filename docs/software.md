# Software

Every tool this project uses, what it does here, why it was picked, and what was passed over. Versions are the ones the 20 million read run of GSE95654 (GEO (Gene Expression Omnibus) Series 95654) used, from methylseq's `pipeline_info/nf_core_methylseq_software_mqc_versions.yml` and the pinned containers in each `pipelines/*/nextflow.config`.

## Bisulfite processing

| Tool | What it is | What it does here | Why this one | Passed over, and why |
|---|---|---|---|---|
| nf-core/methylseq 4.2.0 | Community bisulfite sequencing pipeline | Runs every step from raw reads to per-CpG (cytosine followed by guanine) methylation counts, plus the MultiQC (combined quality control) report | Community-maintained, versioned, and tested on every release. Writing these steps by hand adds risk and shows nothing new | **A hand-written Snakemake pipeline:** the same tools with none of the testing |
| Nextflow 25.04.0 | Workflow manager | Runs methylseq and this repo's three pipelines, sends each task to AWS (Amazon Web Services) Batch, retries tasks whose Spot instance is reclaimed, resumes failed runs from cache | The engine nf-core pipelines are written for. Pinned to the version methylseq 4.2.0's CI (continuous integration) must pass on; newer Nextflow rejects 4.2.0's config | **Snakemake:** nf-core pipelines don't run on it |
| Bismark 0.25.1 | Bisulfite-aware aligner and methylation caller | Aligns trimmed reads to an in-silico bisulfite-converted GRCh38 (human reference genome, build 38), then counts methylated and unmethylated reads at every cytosine | methylseq's default aligner; its coverage files and splitting reports are what `convert` and `qc` read | **bwa-meth (Burrows-Wheeler Aligner for methylation):** faster, but needs MethylDackel for calling, and Bismark is the default nf-core tests most |
| Trim Galore 0.6.10 (Cutadapt 4.9) | Adapter and quality trimmer | Cuts adapter sequence and low-quality ends; in RRBS (reduced representation bisulfite sequencing) mode it also removes the filled-in bases at enzyme cut sites | methylseq's default, with an RRBS (reduced representation bisulfite sequencing) mode built in | |
| FastQC 0.12.1 | Read quality checker | Per-sample read quality, adapter content, and duplicate levels; `qc` takes the duplicate rate from it | Standard first check on any sequencing run; methylseq runs it | |
| samtools 1.22.1 | Alignment file toolkit | Sorts and indexes Bismark's BAM (binary alignment map) files | Standard | |
| MultiQC 1.32 | Report aggregator | One interactive HTML (web page) report across every sample and every tool | methylseq builds it; nothing to add | |

methylseq skips deduplication when `rrbs: true`. RRBS (reduced representation bisulfite sequencing) reads start at the same MspI enzyme cut sites by design, so reads with the same start position aren't necessarily PCR (polymerase chain reaction) copies.

## Data download

| Tool | What it is | What it does here | Why this one | Passed over, and why |
|---|---|---|---|---|
| sra-tools 3.2.1 | NCBI (National Center for Biotechnology Information) download tools | `prefetch` downloads each run and checks its MD5 (Message Digest 5) checksum; `fasterq-dump` unpacks it to FASTQ (sequence reads with quality scores) | Official client. `pipelines/fetch_sra` rejects SRA Lite files, which replace quality scores with a constant | **nf-core/fetchngs:** doesn't force full-quality files, can't downsample, and can't write a methylseq sample sheet |
| seqtk 1.4 | FASTQ (sequence reads with quality scores) toolkit | Randomly downsamples each run to 20 million read pairs with seed 42, keeping mates paired | One small binary, reproducible with a fixed seed | |

## Conversion, QC (quality control), and reports

| Tool | What it is | What it does here | Why this one | Passed over, and why |
|---|---|---|---|---|
| Python 3.14 | Programming language | `src/methyl_flow/`: conversion, QC (quality control) table, plots, report | Same language and tooling as methyl-floor, which reads the beta table | |
| pyarrow 26.0.0 | Columnar data library | Reads Bismark coverage files, joins samples, writes the Parquet (columnar file format) beta table | Fast CSV (comma-separated values) reading and the Parquet (columnar file format) writer in one package; `convert.py` needs nothing else | **pandas:** a heavier dependency for the same joins |
| NumPy 2.5.4 | Array library | PCA (principal component analysis) by singular value decomposition, histograms | Enough for a 2-component PCA (principal component analysis) on 18 samples | **scikit-learn:** a large dependency for one function |
| matplotlib 3.11.2 | Plotting library | Static PNG (image) plots: coverage, methylation, PCA (principal component analysis) | Renders headless inside a container; PNGs drop straight into the README | |
| Plotly.js 2.35.2 | JavaScript charting library | The charts in `report.html`, loaded from a pinned CDN (content delivery network) URL | Hover and zoom with no Python dependency, so the QC (quality control) container stays the same | **Plotly for Python:** would mean rebuilding the pinned container. **Embedding Plotly.js:** adds 3.5 MB to every report |

## Planned: differential methylation (Build E)

| Tool | What it is | Why this one | Passed over, and why |
|---|---|---|---|
| R and Bioconductor | Statistics language and its bioinformatics package repository | Where the established differential methylation methods live | |
| DSS (Dispersion Shrinkage for Sequencing data) | Differential methylation package | Models read counts per CpG (cytosine followed by guanine) site with a beta-binomial model and shrinks each site's dispersion estimate toward the average, which holds up at small sample counts | **methylKit:** its defaults are less stable with 9 samples per group |
| renv | R package lockfile tool | The R counterpart to `uv.lock`; everything lives in `r/` | |

## Development

| Tool | What it is | What it does here | Why this one | Passed over, and why |
|---|---|---|---|---|
| uv | Python package and environment manager | Installs dependencies, pins exact versions in `uv.lock`, runs every command (`uv run`) | One fast tool, and the lockfile makes every machine install the same versions | **pip + venv:** no lockfile by default. **Poetry:** slower, and uv covers the same ground |
| `uv_build` | Build backend | Turns `src/methyl_flow` into an installable package | Native to uv and the src layout | **setuptools:** more config for the same result |
| ruff | Linter and formatter | Checks style and common bugs, formats code | One tool, runs in milliseconds | **flake8 + black + isort:** three tools for the same job |
| pytest | Test runner | Checks conversion, QC (quality control) math, plots, and the report on small fixture files, with no network | The standard for Python | **unittest:** more boilerplate |
| pre-commit | Git hook manager | Runs ruff before every commit | Catches problems before they reach CI (continuous integration) | |
| GitHub Actions | CI (continuous integration) | Runs `uv sync --locked`, ruff, and pytest on every pull request | Lives next to the code | |
| Claude Code | AI (artificial intelligence) coding assistant | Explained each sequencing and statistics concept before code changed and interpreted each result (see `CLAUDE.md`) | | |

## AWS (Amazon Web Services) and runs

| Tool | What it is | What it does here | Why this one | Passed over, and why |
|---|---|---|---|---|
| AWS Batch | Managed job scheduler | Runs the Nextflow head job on an on-demand queue and every task on a Spot queue, up to 256 vCPUs (virtual CPUs) | Starts instances per job and scales to zero when idle; no cluster to run. Nextflow has a mature Batch executor | **Local Docker (container software):** ran out of memory sharing Docker Desktop with other projects. **Slurm:** no cluster available. Both stay as `--compute local` and `--compute slurm` |
| S3 (Amazon Simple Storage Service) | Object storage | Reads, reference, pipeline output, Nextflow's work files, and run bundles | Batch jobs and the laptop both read it; Nextflow stages files through it directly | |
| AWS CDK (Cloud Development Kit), Python | Infrastructure as code | Defines `MethylFlowBatchStack` in `infra/aws/`, with tests | Same language as the rest of the repo, deployed in one command | **Hand-written CloudFormation YAML (YAML Ain't Markup Language):** longer and untested |
| Secrets Manager | Secret store | Holds the Seqera Platform token for the head job | The head job reads it at start; it never sits in a file | |
| AWS Budgets | Cost alerts | $50 a month, filtered to the `project=methyl-flow` tag | Email before a forgotten queue runs up a bill | |
| Seqera Platform | Nextflow run monitor | Live progress of each run, and an Outputs tab listing the reports (`tower.yml`) | Free tier covers a personal project; made for Nextflow | |
| Seqera Containers | Container builder | Pinned images for `fetch_sra`, `convert`, and `qc`, built from Bioconda and PyPI (Python Package Index) packages | Builds a container from a package list, so no Dockerfile to maintain | **A custom Dockerfile per pipeline:** more to maintain for the same result |
