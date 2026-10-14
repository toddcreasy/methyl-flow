# TODO: cover the methyl-flow project brief

Each item from two sections of the brief in `CLAUDE.md` ("Core idea" and "What the project must show"), in order. For each: what the terms mean, whether this repo does it today, and what to build. Section 3 groups the builds following the brief's order of work. Section 4 is the dataset plan.

Status: 🟢 **Yes** (done, with evidence), 🟡 **Partly** (some of it), 🔴 **No** (nothing yet), ⚪ not a codebase item. Build items: ✅ done, ⬜ open.

## Open work

**0. Scaffold and CI (continuous integration)** (1 of 4 done)
- ⬜ CI (continuous integration) workflow: `uv sync --locked`, ruff check, ruff format check, pytest; concurrency group per ref.
- ⬜ Branch protection on main: PR (pull request) plus passing CI (continuous integration), `enforce_admins` on.
- ⬜ Setup phases removed from CLAUDE.md after STOP gate 1.

**A. methylseq test profile** (0 of 3 done)
- ⬜ Install Nextflow (workflow manager for bioinformatics pipelines); check the minimum version nf-core/methylseq 4.2.0 needs.
- ⬜ Run nf-core/methylseq 4.2.0 with `-profile test,docker`; record the command and the run time.
- ⬜ Pinned run config checked in: pipeline version, params file, Docker (container software) profile.

**B. Real dataset** (0 of 5 done)
- ⬜ Find RRBS (reduced representation bisulfite sequencing) or targeted bisulfite candidates in SRA (Sequence Read Archive); check library strategy, organism, and group labels in the metadata.
- ⬜ Pick one dataset, 10 to 20 samples, two groups.
- ⬜ Download script with pinned SRR (Sequence Read Archive run) accessions and checksums.
- ⬜ Downsample reads to a laptop-sized run; record the seed and read count.
- ⬜ methylseq sample sheet and params file for the dataset; run it.

**C. Conversion to the beta table** (0 of 4 done)
- ⬜ Read Bismark coverage files from methylseq output.
- ⬜ Write the beta table (samples by CpG (a cytosine followed by a guanine) sites) plus sample sheet in methyl-floor's format.
- ⬜ Unit tests on small fixture coverage files.
- ⬜ Schema check: the output loads in methyl-floor.

**D. QC (quality control) summary and plots** (0 of 4 done)
- ⬜ QC (quality control) table per sample: bisulfite conversion rate, coverage, duplicate rate, generated from pipeline output.
- ⬜ Coverage and methylation distribution plots.
- ⬜ PCA (principal component analysis) by group and batch.
- ⬜ One command regenerates the table and plots from pipeline output.

**E. Differential methylation** (0 of 4 done)
- ⬜ R (statistics language) environment pinned with renv (R package lockfile tool); code in `analysis/`.
- ⬜ DSS (Dispersion Shrinkage for Sequencing data) test per CpG (a cytosine followed by a guanine) site between groups, then DMR (differentially methylated region) calling.
- ⬜ DMR (differentially methylated region) plots.
- ⬜ Report how many DMRs (differentially methylated regions) survive FDR (false discovery rate) correction.

**F. Limits and docs** (0 of 2 done)
- ⬜ README limits section: downsampled data, small sample counts, RRBS (reduced representation bisulfite sequencing) covers only CpG-rich (cytosine-guanine-rich) regions.
- ⬜ One-command run documented in the README.

**Later, optional**
- ⬜ Array input path: IDAT (Illumina's raw scanner file) files through SeSAMe or minfi (R packages for methylation arrays) into the same beta table format.
- ⬜ IGV (Integrative Genomics Viewer) tracks.

## 1. "Core idea"

### 1.1 Processing: run nf-core/methylseq, don't write it

- **Bisulfite conversion:** a chemical treatment that turns unmethylated cytosine into uracil, read as thymine after amplification. Methylated cytosine stays cytosine, so each C (cytosine) or T (thymine) at a CpG (a cytosine followed by a guanine) site in a read records that site's methylation in one DNA (deoxyribonucleic acid) molecule.
- **Read trimming:** cutting adapter sequence and low-quality bases off read ends before alignment.
- **Alignment:** finding where each read came from in the reference genome. Bisulfite reads need special aligners, because converted Ts (thymines) would look like mismatches to a normal aligner.
- **Bismark or bwa-meth (BWA is the Burrows-Wheeler Aligner):** the two aligner options in methylseq. Bismark is the older default and also does methylation calling.
- **Methylation calling:** counting, at each CpG (a cytosine followed by a guanine) site, how many reads show it methylated and how many unmethylated.
- **MultiQC (combined quality control):** gathers the reports from every tool in the run into one HTML (web page) report.

**Status: 🔴 No.** Nextflow (workflow manager for bioinformatics pipelines) not installed or run yet. **Build A, B.**

### 1.2 Reproducible use: pinned pipeline version, Docker (container software) profile, a sample sheet, and a params file in the repo

- **Profile:** a named Nextflow (workflow manager for bioinformatics pipelines) config bundle. `docker` runs every tool in a pinned container; `test` swaps in a tiny bundled dataset.
- **Params file:** a YAML (YAML Ain't Markup Language) file holding the run's options (genome, aligner, RRBS (reduced representation bisulfite sequencing) mode), so the run is a file in git, not a long command typed once.
- **Sample sheet:** a CSV (comma-separated values) file listing each sample and its FASTQ (sequence reads with quality scores) files.

**Status: 🔴 No.** Python side pinned (`uv.lock`, `.python-version`); nothing for the pipeline yet. **Build A, B.**

### 1.3 Convert: methylseq per-CpG (a cytosine followed by a guanine) coverage files to the shared beta table plus sample sheet

- **Coverage file:** Bismark's per-site output. Each row is one CpG (a cytosine followed by a guanine) site with its methylated and unmethylated read counts.
- **Coverage:** how many reads cover a site. Low coverage makes the beta value noisy; 1 of 2 reads methylated and 50 of 100 both give 0.5.
- **Beta value:** methylated reads divided by total reads at one site, from 0 (never methylated) to 1 (always).
- **The contract:** methyl-floor reads a beta table (samples by CpG (a cytosine followed by a guanine) sites) plus a sample sheet. This step is what ties the two repos together.

**Status: 🔴 No.** **Build C.**

### 1.4 Analyze: differential methylation with DSS (Dispersion Shrinkage for Sequencing data); QC (quality control) summary of conversion rate, coverage, and duplicate rate

- **Bisulfite conversion rate:** the share of unmethylated cytosines that converted. Usually estimated from non-CpG (non cytosine-guanine) cytosines, which are almost never methylated in most human tissue. 99% means about 1 in 100 unmethylated cytosines reads as methylated, which sets a floor on false methylation.
- **Duplicate rate:** share of reads that are PCR (polymerase chain reaction) copies of the same molecule. In RRBS (reduced representation bisulfite sequencing) many reads start at the same enzyme cut site by design, so duplicates cannot be told apart by position; check how methylseq handles deduplication in RRBS (reduced representation bisulfite sequencing) mode before reporting it.
- **Differential methylation:** testing each site for a difference in methylation between groups.
- **DMR (differentially methylated region):** a run of nearby CpG (a cytosine followed by a guanine) sites that differ together. More stable than single sites.
- **Dispersion:** extra spread between samples beyond counting noise. DSS (Dispersion Shrinkage for Sequencing data) pulls each site's noisy estimate toward the average across sites.
- **FDR (false discovery rate):** the expected share of false calls among all calls. Testing thousands of sites makes some look significant by chance; multiple-testing correction controls it.

**Status: 🔴 No.** **Build D, E.**

### 1.5 Visualize: coverage and methylation distributions, PCA (principal component analysis) by group and batch, DMR (differentially methylated region) plots

- **PCA (principal component analysis):** projects samples onto the directions of largest variation. If samples cluster by batch rather than group, the batch is driving the signal.
- **Batch effect:** differences from how samples were processed (run, lab, date) rather than biology.

**Status: 🔴 No.** **Build D, E.**

## 2. "What the project must show"

### 2.1 A one-command, version-pinned methylseq run that works on the test profile and on a downsampled real dataset

**Status: 🔴 No.** **Build A, B.**

### 2.2 A well-tested conversion step: unit tests on small fixture coverage files, plus a schema check that its output loads in methyl-floor

**Status: 🔴 No.** pytest and CI (continuous integration) are set up; one import test only. **Build C.**

### 2.3 A QC (quality control) summary table and the plots, generated from pipeline output, not hand-edited

**Status: 🔴 No.** **Build D.**

### 2.4 An honest limits section: downsampled data, small sample counts, RRBS (reduced representation bisulfite sequencing) covers only CpG-rich (cytosine-guanine-rich) regions

- **Why RRBS (reduced representation bisulfite sequencing) is partial:** it cuts DNA (deoxyribonucleic acid) with an enzyme (MspI) that targets CCGG (cytosine-cytosine-guanine-guanine) sites and keeps the short fragments, so it reads promoters and CpG (a cytosine followed by a guanine) islands well and most of the rest of the genome not at all.

**Status: 🔴 No.** **Build F.**

## 3. Build plan

Order follows the brief's order of work.

### 0. Scaffold and CI (continuous integration)
- ✅ uv package, ruff, pytest with a `network` marker, pre-commit, src layout, Python 3.14. (`17e6cb5`)
- ⬜ CI (continuous integration) workflow: `uv sync --locked`, ruff check, ruff format check, pytest; concurrency group per ref.
- ⬜ Branch protection on main: PR (pull request) plus passing CI (continuous integration), `enforce_admins` on.
- ⬜ Setup phases removed from CLAUDE.md after STOP gate 1.

### A. methylseq test profile (1.1, 1.2, 2.1)
- ⬜ Install Nextflow (workflow manager for bioinformatics pipelines); check the minimum version nf-core/methylseq 4.2.0 needs.
- ⬜ Run nf-core/methylseq 4.2.0 with `-profile test,docker`; record the command and the run time.
- ⬜ Pinned run config checked in: pipeline version, params file, Docker (container software) profile.

### B. Real dataset (1.1, 1.2, 2.1)
- ⬜ Find RRBS (reduced representation bisulfite sequencing) or targeted bisulfite candidates in SRA (Sequence Read Archive); check library strategy, organism, and group labels in the metadata.
- ⬜ Pick one dataset, 10 to 20 samples, two groups.
- ⬜ Download script with pinned SRR (Sequence Read Archive run) accessions and checksums.
- ⬜ Downsample reads to a laptop-sized run; record the seed and read count.
- ⬜ methylseq sample sheet and params file for the dataset; run it.

### C. Conversion (1.3, 2.2)
- ⬜ Read Bismark coverage files from methylseq output.
- ⬜ Write the beta table plus sample sheet in methyl-floor's format.
- ⬜ Unit tests on small fixture coverage files.
- ⬜ Schema check: the output loads in methyl-floor.

### D. QC (quality control) summary and plots (1.4, 1.5, 2.3)
- ⬜ QC (quality control) table per sample: bisulfite conversion rate, coverage, duplicate rate.
- ⬜ Coverage and methylation distribution plots.
- ⬜ PCA (principal component analysis) by group and batch.
- ⬜ One command regenerates the table and plots from pipeline output.

### E. Differential methylation (1.4, 1.5)
- ⬜ R (statistics language) environment pinned with renv (R package lockfile tool); code in `analysis/`.
- ⬜ DSS (Dispersion Shrinkage for Sequencing data) test per site, then DMR (differentially methylated region) calling.
- ⬜ DMR (differentially methylated region) plots.
- ⬜ Report how many DMRs (differentially methylated regions) survive FDR (false discovery rate) correction.

### F. Limits and docs (2.4)
- ⬜ README limits section.
- ⬜ One-command run documented in the README.

## 4. Dataset plan

No dataset chosen yet. Requirements from the brief: RRBS (reduced representation bisulfite sequencing) or targeted bisulfite, not WGBS (whole-genome bisulfite sequencing); public in SRA (Sequence Read Archive); 10 to 20 samples; group labels in the metadata. Check library strategy, organism, and labels before committing to one.
