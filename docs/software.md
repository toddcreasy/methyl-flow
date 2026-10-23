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

## Differential methylation

| Tool | What it is | What it does here | Why this one | Passed over, and why |
|---|---|---|---|---|
| R 4.5.2 | Statistics language | `r/dss.R`: reads coverage files, fits the model, calls DMRs (differentially methylated regions) | Where the established differential methylation methods live | |
| DSS (Dispersion Shrinkage for Sequencing data) 2.58.0 | Bioconductor differential methylation package | Fits a beta-binomial model to methylated and total reads at each CpG (cytosine followed by guanine) site with `~ patient + tissue`, tests the tissue term, and joins FDR (false discovery rate)-significant sites into DMRs (differentially methylated regions) | Shrinks each site's dispersion estimate toward the average across sites, which holds up with 9 pairs. Its multifactor model handles the paired design | **methylKit:** its defaults are less stable at small sample counts. **DSS's two-group test:** allows smoothing across neighboring sites, but can't pair each tumor with its own normal |
| data.table 1.17.8 | R table library | Reads and joins the coverage files, writes the results | Fast enough for 18 files of about 9 million rows each; already a DSS dependency | |
| BioContainers `bioconductor-dss:2.58.0` | Container image built from Bioconda | Runs `DSS_TEST` on AWS (Amazon Web Services) Batch and the R tests in CI (continuous integration) | A pinned, ready-made image for this exact package | **A custom image:** nothing to add |
| GENCODE release 50 basic gene annotation | Gene annotation (GTF, gene transfer format) | `src/methyl_flow/annotate.py`: protein-coding TSSs (transcription start sites) for promoters and the nearest gene, and gene spans for gene bodies | The same release as the reference genome, so coordinates match exactly. The basic set drops fragmentary transcripts | **RefSeq:** a different release cycle and chromosome naming from the reference |
| UCSC (University of California, Santa Cruz) hg38 CpG islands | CpG (cytosine followed by guanine) island track (`cpgIslandExt`) | Island, shore, shelf, and open-sea context for each site and DMR (differentially methylated region) | The island set most methylation papers use, so results compare | **annotatr (R):** downloads the same UCSC track at run time, unpinned; a small Python step with a checksum is simpler |
| renv | R package lockfile tool | `r/renv.lock` pins DSS and data.table for local work, the R counterpart to `uv.lock` | Keeps everything R-specific in `r/` | |

The laptop runs R 4.6.1, where Bioconductor 3.23 installs DSS 2.60.0; the container has DSS 2.58.0 on R 4.5.2. The container is the version of record for every real run, and `r/tests/test_dss.R` passes in both. The R tests use base R only, so they run in the pinned image with nothing installed on top.

The DMR (differentially methylated region) plots and report come from `src/methyl_flow/dmr_report.py`, in the same Python container as the QC (quality control) report. R does the statistics; Python does the presentation, and they hand off through files.

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
| CloudFront (Amazon's content delivery network) | Web hosting in front of S3 (Amazon Simple Storage Service) | Serves the results hub and reports from `MethylFlowSiteStack`, HTTPS (secure HTTP) only, with security headers; the bucket blocks public access and only CloudFront reads it | Same AWS (Amazon Web Services) account and CDK (Cloud Development Kit) app as the pipelines; pennies a month at this size | **GitHub Pages:** simplest, but needs a public repo or a paid plan. **S3 website hosting:** needs a public bucket and has no HTTPS |
| igv-reports 1.16.0 | Genome browser report builder (IGV, Integrative Genomics Viewer) | Turns the windowed tracks from `igv_tracks.py` into one HTML (web page) file per run | Embeds only the data near each region, so the page stays small and needs no access to the data bucket; the genome sequence streams from UCSC (University of California, Santa Cruz) when it opens | **igv.js inside the DMR report:** more custom code for the same view |
| Seqera Containers | Container builder | Pinned images for `fetch_sra`, `convert`, and `qc`, built from Bioconda and PyPI (Python Package Index) packages | Builds a container from a package list, so no Dockerfile to maintain | **A custom Dockerfile per pipeline:** more to maintain for the same result |
