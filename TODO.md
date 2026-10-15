# TODO: cover the methyl-flow project brief

Each item from two sections of the brief in `CLAUDE.md` ("Core idea" and "What the project must show"), in order. For each: what the terms mean, whether this repo does it today, and what to build. Section 3 groups the builds following the brief's order of work. Section 4 is the dataset plan.

Status: 🟢 **Yes** (done, with evidence), 🟡 **Partly** (some of it), 🔴 **No** (nothing yet), ⚪ not a codebase item. Build items: ✅ done, ⬜ open.

## Open work

**0. Scaffold and CI (continuous integration)** (4 of 4 done)

**A. methylseq test profile** (3 of 3 done)

**B. Real dataset** (2 of 5 done)
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
- ⬜ R (statistics language) environment pinned with renv (R package lockfile tool); code, `renv.lock`, and R library all in `r/`.
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

**Status: 🟡 Partly.** Test profile runs end to end: trimming, Bismark alignment, deduplication, methylation calling, MultiQC (combined quality control). No real data yet. **Build B.**

### 1.2 Reproducible use: pinned pipeline version, Docker (container software) profile, a sample sheet, and a params file in the repo

- **Profile:** a named Nextflow (workflow manager for bioinformatics pipelines) config bundle. `docker` runs every tool in a pinned container; `test` swaps in a tiny bundled dataset.
- **Params file:** a YAML (YAML Ain't Markup Language) file holding the run's options (genome, aligner, RRBS (reduced representation bisulfite sequencing) mode), so the run is a file in git, not a long command typed once.
- **Sample sheet:** a CSV (comma-separated values) file listing each sample and its FASTQ (sequence reads with quality scores) files.

**Status: 🟡 Partly.** Pinned: methylseq 4.2.0, Nextflow 25.04.0, AWS (Amazon Web Services) Batch with a Nextflow head job, in `scripts/run.sh` and `infra/aws/`; params file `config/methylseq/test.yaml`. The test profile brings its own sample sheet; the real dataset's sample sheet comes with Build B.

### 1.3 Convert: methylseq per-CpG (a cytosine followed by a guanine) coverage files to the shared beta table plus sample sheet

- **Coverage file:** Bismark's per-site output. Each row is one CpG (a cytosine followed by a guanine) site with its methylated and unmethylated read counts.
- **Coverage:** how many reads cover a site. Low coverage makes the beta value noisy; 1 of 2 reads methylated and 50 of 100 both give 0.5.
- **Beta value:** methylated reads divided by total reads at one site, from 0 (never methylated) to 1 (always).
- **The contract:** methyl-floor reads a beta table (samples by CpG (a cytosine followed by a guanine) sites) plus a sample sheet. This step is what ties the two repos together.

**Status: 🔴 No.** **Build C.**

### 1.4 Analyze: differential methylation with DSS (Dispersion Shrinkage for Sequencing data); QC (quality control) summary of conversion rate, coverage, and duplicate rate

- **Bisulfite conversion rate:** the share of unmethylated cytosines that converted. Usually estimated from non-CpG (non cytosine-guanine) cytosines, which are almost never methylated in most human tissue. 99% means about 1 in 100 unmethylated cytosines reads as methylated, which sets a floor on false methylation.
- **Duplicate rate:** share of reads that are PCR (polymerase chain reaction) copies of the same molecule. In RRBS (reduced representation bisulfite sequencing) many reads start at the same enzyme cut site by design, so duplicates cannot be told apart by position. methylseq 4.2.0 skips deduplication when `rrbs: true` (`workflows/methylseq/main.nf:136`), so the QC (quality control) table has to take duplicate levels from FastQC and say that RRBS (reduced representation bisulfite sequencing) inflates them by design.
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

**Status: 🟡 Partly.** Test profile: `scripts/run.sh methylseq config/methylseq/test.yaml` completes on AWS (Amazon Web Services) Batch. Downsampled real dataset not yet. **Build B.**

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
- ✅ CI (continuous integration) workflow: `uv sync --locked`, ruff check, ruff format check, pytest; concurrency group per ref. (`6a6c84e`, PR (pull request) #1)
- ✅ Branch protection on main: PR (pull request) plus passing CI (continuous integration), `enforce_admins` on.
- ✅ Setup phases removed from CLAUDE.md after STOP gate 1. (PR (pull request) #2)

### A. methylseq test profile (1.1, 1.2, 2.1)
- ✅ Install Nextflow (workflow manager for bioinformatics pipelines); check the minimum version nf-core/methylseq 4.2.0 needs. Installed 26.04.6; 4.2.0 requires `>=25.04.0`. Runs pin `NXF_VER=25.04.0`, the version 4.2.0's CI (continuous integration) must pass on: newer Nextflow rejects the 4.2.0 config, which includes `conf/aws/batch/nextflow.config`, a file missing from the release tag.
- ✅ Run nf-core/methylseq 4.2.0 with `-profile test,docker`; record the command and the run time. `scripts/run_methylseq.sh config/methylseq/test.yaml test`: 36 tasks, 272 s (seconds) with container pulls, 154 s (seconds) cached, on an Apple Silicon laptop (18 cores, 64 GB (gigabytes)) with `emulate_amd64`.
- ✅ Pinned run config checked in: pipeline version, params file, Docker (container software) profile. (`scripts/run_methylseq.sh`, `config/methylseq/test.yaml`)

### B. Real dataset (1.1, 1.2, 2.1)
- ✅ Find RRBS (reduced representation bisulfite sequencing) or targeted bisulfite candidates in SRA (Sequence Read Archive); check library strategy, organism, and group labels in the metadata. 146 human RRBS (reduced representation bisulfite sequencing) studies with 10 to 40 samples; 6 shortlisted; BioSample labels checked (section 4).
- ✅ Pick one dataset, 10 to 20 samples, two groups. GSE95654 (GEO (Gene Expression Omnibus) Series 95654), 9 colorectal cancer patients, tumor and adjacent normal (section 4).
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
- ⬜ R (statistics language) environment pinned with renv (R package lockfile tool); code, `renv.lock`, and R library all in `r/`.
- ⬜ DSS (Dispersion Shrinkage for Sequencing data) test per site, then DMR (differentially methylated region) calling.
- ⬜ DMR (differentially methylated region) plots.
- ⬜ Report how many DMRs (differentially methylated regions) survive FDR (false discovery rate) correction.

### F. Limits and docs (2.4)
- ⬜ README limits section.
- ⬜ One-command run documented in the README.

## 4. Dataset plan

Decided 2026-10-14: **GSE95654 (GEO (Gene Expression Omnibus) Series 95654), SRA (Sequence Read Archive) study SRP101332**, colorectal cancer subset.

- **Paper:** Hanley MP et al. Genome-wide DNA (deoxyribonucleic acid) methylation profiling reveals cancer-associated changes within early colonic neoplasia. *Oncogene* 2017. [DOI (Digital Object Identifier) 10.1038/onc.2017.130](https://doi.org/10.1038/onc.2017.130), PMID (PubMed identifier) 28459462.
- **Assay:** human RRBS (reduced representation bisulfite sequencing), Illumina HiSeq 2500.
- **Subset:** primary tumor and adjacent normal colon from 9 KRAS-mutant colorectal cancer patients, 18 samples. Labels from the BioSample `tissue` field (`primary tumor`, `adjacent normal colon`) with a patient number on each. The study's other 20 samples (aberrant crypt foci and normal crypts from healthy people) are left out.
- **Dropped: patient 41.** The tumor run, SRR5311101, has a single constant quality score (`?`) on every base in both NCBI (National Center for Biotechnology Information) and ENA (European Nucleotide Archive); no full-quality copy exists. Quality trimming and Bismark's mismatch scoring both need real scores, so the whole pair is out.
- **Batch: read layout.** Patients 32 and 42 are single-end 1x100; the other 7 are paired-end 2x100. Each patient's tumor and normal share a layout, so layout is a between-patient batch, not confounded with tumor versus normal. Recorded in `config/gse95654/runs.tsv`.
- **Download:** `pipelines/fetch_sra` on AWS (Amazon Web Services) Batch (`scripts/run.sh fetch_sra config/fetch_sra/gse95654.yaml`) runs `prefetch` (MD5-validated) and `fasterq-dump` from NCBI (National Center for Biotechnology Information), then `seqtk sample` to 5,000,000 reads (read pairs for paired-end) per sample with seed 42, in one task per sample so the unpacked FASTQ (sequence reads with quality scores) never leaves the instance. Container: `community.wave.seqera.io/library/sra-tools_seqtk:67fdf6e5e7fd06bc` (sra-tools 3.2.1, seqtk 1.4). SRA Lite files, which replace quality scores with a constant, are rejected. It also fetches and MD5-checks the GENCODE reference and writes the methylseq samplesheet. nf-core/fetchngs was checked first: it does not force full-quality files, cannot downsample, and cannot write a methylseq samplesheet.
- **Reference:** GENCODE release 50 GRCh38 primary assembly (no alt haplotypes), Bismark index built by methylseq with `save_reference`. Chosen over nf-core's iGenomes GRCh38, which nf-core flags as old and unmaintained (index built 2017).
- **Runner-up:** SRP421427, 10 clear cell renal cell carcinoma tumor and normal pairs, all paired-end; unpublished, all male, and kidney tumors shed little cfDNA (cell-free DNA).
