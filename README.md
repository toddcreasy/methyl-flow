# methyl-flow

Turn raw bisulfite sequencing reads into a methylation beta table, a QC (quality control) report, and a list of DMRs (differentially methylated regions) between tumor and normal tissue. Processing runs nf-core/methylseq, pinned, on AWS (Amazon Web Services) Batch; this repo adds the download, the conversion to a shared beta table, the QC (quality control) summary, the differential methylation test, and interactive reports.

![PCA of 18 colorectal samples: 8 of 9 tumors separate from the normals on PC1, and read layout does not split them](docs/images/pca.png)

*PCA (principal component analysis) of 9 colorectal tumors and their matched normal tissue, from 121,264 CpG (cytosine followed by guanine) sites. Left: colored by tissue. Right: colored by read layout, the one batch in the data.*

```bash
scripts/run.sh methylseq config/methylseq/gse95654_20m.yaml
```

[docs/walkthrough.md](docs/walkthrough.md) goes stage by stage: what each step does, the numbers it produced, and what went wrong. [docs/software.md](docs/software.md) lists every tool, what it does, and why it was picked over the alternatives.

A research project on public data. Not for clinical or diagnostic use.

## What it does

Bisulfite treatment turns unmethylated cytosines into uracil, which sequencing reads as T (thymine); methylated cytosines stay C (cytosine). Align the reads back to the genome, count Cs and Ts at each CpG (cytosine followed by guanine) site, and you have that site's methylation level in each sample. Cancer changes those levels in recognizable ways, which is what MCED (multi-cancer early detection) tests look for.

methyl-flow runs that end to end, one `scripts/run.sh` call per step:

| Step | Command | What it does | Main output |
|---|---|---|---|
| Fetch | `scripts/run.sh fetch_sra <params>` | Downloads each SRA (Sequence Read Archive) run with checksum checks, downsamples it with a fixed seed, fetches the reference genome, writes the sample sheet | FASTQ (sequence reads with quality scores) files, `samplesheet.csv` |
| Process | `scripts/run.sh methylseq <params>` | nf-core/methylseq 4.2.0: read trimming, Bismark alignment, methylation calling | Per-sample coverage files, MultiQC (combined quality control) report |
| Convert | `scripts/run.sh convert <params>` | Turns Bismark coverage files into one table of beta values, sites by samples | `betas/<study>.parquet`, `samples.tsv` |
| QC (quality control) | `scripts/run.sh qc <params>` | Bisulfite conversion rate, duplicate rate, and coverage per sample; coverage, methylation, and PCA (principal component analysis) plots | `samples_qc.tsv`, plots, `report.html` |
| Differential methylation | `scripts/run.sh dss <params>` | DSS (Dispersion Shrinkage for Sequencing data) in R: tumor against its own patient's normal at each CpG (cytosine followed by guanine) site, then DMRs (differentially methylated regions) from the FDR (false discovery rate)-significant sites | `dml.tsv.gz`, `dmrs.tsv`, plots, `report.html` |

Each step reads the last one's output from S3 (Amazon Simple Storage Service), so the params files in `config/` chain them together.

## Data

[GSE95654](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE95654) (GEO (Gene Expression Omnibus) Series 95654, SRA (Sequence Read Archive) study SRP101332): RRBS (reduced representation bisulfite sequencing) of primary tumor and adjacent normal colon from KRAS-mutant colorectal cancer patients, Illumina HiSeq 2500. This repo uses 9 patients, 18 samples, listed with their SRR (Sequence Read Archive run) accessions in `config/gse95654/runs.tsv`.

- **Patient 41 dropped.** Its tumor run has a constant quality score on every base in every archive copy, and trimming and alignment both need real scores.
- **Read layout is a batch.** Patients 32 and 42 are single-end, the other 7 paired-end. Tumor and normal from one patient share a layout.
- **Downsampled to 20 million read pairs per sample**, seed 42. Every run has at least 29.7 million. A first pass at 5 million left a median of 2 reads per CpG (cytosine followed by guanine) site, too few for a usable beta value ([walkthrough step 5](docs/walkthrough.md#5-qc-quality-control-shows-5-million-reads-is-too-thin)).
- **Reference:** GENCODE release 50 GRCh38 (human reference genome, build 38) primary assembly, checksum-verified.

No reads are stored in git or on the laptop. `fetch_sra` writes them straight to S3 (Amazon Simple Storage Service).

## How it fits together

<img src="docs/architecture.svg" alt="methyl-flow architecture. Top: a laptop runs scripts/run.sh, which uploads a run bundle to S3 and submits a Nextflow head job to AWS Batch; the head job starts one Spot task job per pipeline task, reads and writes S3, gets the Seqera token from Secrets Manager, and streams progress to Seqera Platform. cdk deploy creates the stack through CloudFormation. Middle: SRA and GENCODE feed fetch_sra, then nf-core/methylseq, which produces the MultiQC report and coverage files; convert turns those into the beta table methyl-floor reads; qc writes the QC report; dss reads the coverage counts and writes the DMR report. Bottom: pre-commit, pull requests, GitHub Actions, pytest, and the R tests." width="100%">

The laptop only submits. `scripts/run.sh` uploads `config/`, `pipelines/`, `src/`, and `r/` to S3 (Amazon Simple Storage Service), then starts Nextflow itself as an AWS (Amazon Web Services) Batch job on an on-demand queue, so the laptop can close and a Spot reclaim can't kill the whole run. Nextflow sends every task to a Spot queue that scales from zero to 256 vCPUs (virtual CPUs) and back. GitHub shows the diagram as a plain image. Opened in a browser, [`docs/architecture.svg`](docs/architecture.svg) is interactive: hover a box for what it does and why, and click it for its source or docs.

### AWS (Amazon Web Services) services

All defined in one CDK (Cloud Development Kit) app, `infra/aws/` ([its README](infra/aws/README.md)).

| Service | Job here | Why this one |
|---|---|---|
| **AWS Batch** | Two queues: on-demand for the Nextflow head job, Spot for tasks (m5, m6i, c5, c6i, r5, r6i) | Starts instances per job and scales to zero when idle; no cluster to run. Spot reclaimed one alignment three times in the 20 million read run, and `--resume` finished it. |
| **S3 (Amazon Simple Storage Service)** | `data/` reads and reference, `results/<pipeline>/<run ID>/`, Nextflow's `work/`, run bundles in `runs/` | Batch jobs and the laptop both read it, and Nextflow stages files through it directly. |
| **Secrets Manager** | The Seqera Platform token | Only the head job's role can read it; it never sits in a file. |
| **CloudWatch Logs** | Console output of every job | For failures that happen before Nextflow writes its own log. |
| **AWS Budgets** | $50 a month, filtered to the `project=methyl-flow` tag | Email at 80% and 100% of spend. |
| **CloudFormation / CDK (Cloud Development Kit)** | Every resource above | One Python app with tests, deployed with one command. |

Not AWS (Amazon Web Services): Nextflow and nf-core/methylseq (the pipeline), Seqera Platform (live run monitoring), Seqera Containers (pinned images for this repo's pipelines), and GitHub Actions.

## Outputs

Each run writes to `results/<pipeline>/<run ID>/` in the S3 (Amazon Simple Storage Service) bucket, where the run ID is the params file name plus a timestamp. Every run also writes Nextflow's interactive execution report and timeline to `pipeline_info/`.

**The beta table**, the contract with methyl-floor (a sibling repo that turns beta tables into a detection limit):

- `betas/GSE95654.parquet`: one row per CpG (cytosine followed by guanine) cytosine, with a `probe` column (`chr1:10497`, 1-based) and one float32 beta column per sample, named by GSM (GEO (Gene Expression Omnibus) sample) accession. A beta is missing where that sample had fewer than 10 reads. 5,276,298 rows at 20 million reads.
- `samples.tsv`: methyl-floor's 12 sample sheet columns, including `tissue` (tumor or normal), `batch` (read layout), and `patient`.

`tests/test_convert.py` loads both with methyl-floor's own loader when that repo is installed.

**The QC (quality control) outputs:**

- `samples_qc.tsv`: one row per sample with bisulfite conversion rate, duplicate rate, CpG (cytosine followed by guanine) sites covered, median reads per site, and the count and share of sites at 10 or more reads.
- `coverage_hist.tsv`: sites per read count, per sample.
- `plots/`: `coverage.png`, `methylation.png`, `pca.png`, and `pca.tsv` with the scores behind the PCA (principal component analysis) plot.
- `report.html`: everything above as one interactive page.

**The differential methylation outputs:**

- `dml.tsv.gz`: one row per tested CpG (cytosine followed by guanine) site with the test statistic, p-value, FDR (false discovery rate), and mean beta in normal and tumor.
- `dmrs.tsv`: one row per DMR (differentially methylated region), strongest first: position, length, number of CpG (cytosine followed by guanine) sites, area statistic (the sum of its sites' test statistics), and mean beta in normal and tumor.
- `dmr_samples.tsv`: mean beta over each DMR's (differentially methylated region's) sites, per sample, for the per-patient plots.
- `dmrs_annotated.tsv`: each DMR (differentially methylated region) with its CpG (cytosine followed by guanine) island context, whether it overlaps a promoter, the nearest protein-coding gene, and the distance to that gene's TSS (transcription start site).
- `annotation_enrichment.tsv`: the share of tested, significant, and DMR (differentially methylated region) sites in each CpG (cytosine followed by guanine) island and gene context, with fold change against all tested sites.
- `summary.tsv`: sites tested, significant sites, and DMRs (differentially methylated regions), by direction.
- `plots/`: `volcano.png`, `top_dmrs.png`, and `annotation.png`. `report.html`: an interactive version, with a sortable table of the 500 strongest DMRs (differentially methylated regions) and their nearest genes.
- `igv/igv_report.html`: a genome browser view (IGV, Integrative Genomics Viewer) of the 25 strongest DMRs (differentially methylated regions) in each direction, with tracks for mean normal and tumor methylation at each tested site, the DMRs, CpG (cytosine followed by guanine) islands, and genes. Built with igv-reports; it embeds only the data within 2,000 bases of each region.

## Results

From the 20 million read run. Full numbers per sample are in the [QC (quality control) report](docs/reports/gse95654_20m/qc_report.html).

| Metric | Range across 18 samples | Good? |
|---|---|---|
| Bisulfite conversion rate | 99.33% to 99.56% | Yes. Above the usual 99% bar everywhere, so false methylation from unconverted cytosines stays under 1%. |
| Mapping rate (Bismark) | 62.7% to 70.5% | Normal for RRBS (reduced representation bisulfite sequencing). |
| Median reads per CpG (cytosine followed by guanine) site | 4 to 7 | Thin. Most sites are covered, but few deeply. |
| Sites at 10 or more reads | 18.5% to 33.0% (1.2 to 2.7 million) | Enough for site-level beta values on millions of sites. |
| Duplicate rate (FastQC, a read quality checker) | 64% to 75% | Expected for RRBS (reduced representation bisulfite sequencing): reads start at the same enzyme cut sites. methylseq skips deduplication in this mode. |

![Share of each sample's CpG sites at each read count; the 10-read cutoff is marked](docs/images/coverage.png)

*Most sites have fewer than 10 reads. The two tumor curves that start highest are P15 and P16, with 27% to 30% of sites at a single read.*

![Beta value distribution per sample, with peaks near 0 and 1](docs/images/methylation.png)

*Beta values pile up near 0 and 1, as expected at CpG (cytosine followed by guanine) sites. The three lowest peaks near 1 are the P15, P16, and P50 tumors, the ones that lost the most methylation.*

PC1 (principal component 1) explains 41% of the variance and separates 8 of 9 tumors from the normals (top of this page). P42's tumor sits with the normals. Read layout doesn't separate samples, so the single-end and paired-end batch isn't what drives the split.

### Differential methylation

DSS (Dispersion Shrinkage for Sequencing data) models methylated reads out of total reads at each site with a beta-binomial model: a coin flip per read, plus extra sample-to-sample spread (dispersion) that DSS pulls toward the average across sites, which steadies the estimate with only 9 pairs. The model is `~ patient + tissue`, so each tumor is compared with its own patient's normal, and differences between patients, read layout included, drop out. FDR (false discovery rate) correction (Benjamini-Hochberg) keeps the expected share of false calls among the reported sites at 5%. DMRs (differentially methylated regions) are runs of at least 3 nearby FDR (false discovery rate)-significant sites. Full details are in the [DMR (differentially methylated region) report](docs/reports/gse95654_20m/dmr_report.html).

| | Total | Higher in tumor | Lower in tumor |
|---|---|---|---|
| CpG (cytosine followed by guanine) sites tested (5+ reads in all 18 samples) | 718,148 | | |
| Sites at FDR (false discovery rate) < 5% | 168,747 (23.5%) | 45,445 | 123,302 |
| DMRs (differentially methylated regions) | 10,947 | 2,604 | 8,343 |

![Volcano plot: methylation change against significance for 718,148 CpG sites](docs/images/volcano.png)

*Every tested site. Significant sites change a lot: median 0.30 in beta, and only 2.7% by less than 0.10. Nothing near zero change is called.*

A quarter of sites passing is a lot, so it was checked before being trusted. The p-value histogram is flat to slightly rising above p = 0.5, so the test isn't inflated; that flat part puts about 72% of sites at no real difference, which matches the 23.5% called. 93.1% of DMRs (differentially methylated regions) change in the same direction in at least 8 of 9 patients, and 59.1% in all 9.

![Normal and tumor beta per patient for the 12 strongest DMRs](docs/images/top_dmrs.png)

*The 12 strongest DMRs (differentially methylated regions) all gain methylation in tumor, from 0.21 to 0.63 on average: dense CpG (cytosine followed by guanine) clusters going from mostly unmethylated to mostly methylated. Losses are more common (8,343 of 10,947) but individually weaker. The tumor that gains least is P15 in all 12 panels; its tumor lost the most methylation overall (61.7% to 31.1% of CpG (cytosine followed by guanine) calls). P42 is among the two lowest in 7 panels and follows the DMR (differentially methylated region) direction in 80% of all DMRs, against 94% to 99% for every other patient; its tumor also sat with the normals in the PCA (principal component analysis).*

### Where the DMRs fall

Each DMR (differentially methylated region) was placed against GENCODE release 50 protein-coding genes and UCSC (University of California, Santa Cruz) hg38 CpG (cytosine followed by guanine) islands. A promoter is within 1,000 bases of a TSS (transcription start site); a shore is within 2,000 bases of an island, a shelf 2,000 to 4,000, and open sea beyond. RRBS (reduced representation bisulfite sequencing) already over-samples islands, so DMR sites are compared with all 718,148 tested sites, not with the genome.

| Sites | CpG island | Open sea | Promoter | Intergenic |
|---|---|---|---|---|
| All tested | 33.8% | 47.3% | 30.1% | 32.0% |
| In DMRs, higher in tumor (35,040) | 82.9% (2.45x) | 3.9% (0.08x) | 48.7% (1.62x) | 24.7% (0.77x) |
| In DMRs, lower in tumor (54,067) | 6.4% (0.19x) | 71.2% (1.51x) | 7.1% (0.24x) | 51.8% (1.62x) |

![Share of tested, significant, and DMR sites in each CpG island and gene context](docs/images/annotation.png)

*Gains in tumor sit in CpG (cytosine followed by guanine) islands and promoters; losses sit in open sea and between genes. That is the pattern expected in colorectal cancer, found here without being looked for: the test knew nothing about islands or genes. By region, 83.9% of the 2,604 DMRs (differentially methylated regions) that gain methylation are in islands and 51.7% overlap a promoter, against 6.6% and 8.0% of the 8,343 that lose it. 10 of the 12 strongest DMRs sit on a promoter; the nearest genes are in `dmrs_annotated.tsv` and the DMR (differentially methylated region) report.*

### Interactive reports

GitHub shows HTML (web page) files as source, so download them and open them in a browser. The QC (quality control), DMR (differentially methylated region), and IGV (Integrative Genomics Viewer) reports load their libraries, and the IGV report its genome sequence, over the network; the others are self-contained.

| Report | What it shows |
|---|---|
| [`qc_report.html`](docs/reports/gse95654_20m/qc_report.html) | This repo's QC (quality control) report: sortable per-sample table, then coverage, methylation, and PCA (principal component analysis) charts with hover and a tissue or read layout toggle |
| [`multiqc_report.html`](docs/reports/gse95654_20m/multiqc_report.html) | methylseq's MultiQC (combined quality control) report: read quality, trimming, alignment, and methylation per sample |
| [`methylseq_execution_report.html`](docs/reports/gse95654_20m/methylseq_execution_report.html), [`methylseq_execution_timeline.html`](docs/reports/gse95654_20m/methylseq_execution_timeline.html) | Nextflow's run time, CPU, and memory per task for the resumed methylseq run |
| [`qc_execution_report.html`](docs/reports/gse95654_20m/qc_execution_report.html), [`qc_execution_timeline.html`](docs/reports/gse95654_20m/qc_execution_timeline.html) | The same for the QC (quality control) run |
| [`dmr_report.html`](docs/reports/gse95654_20m/dmr_report.html) | The differential methylation report: counts, volcano, where the DMRs (differentially methylated regions) fall relative to CpG (cytosine followed by guanine) islands and genes, a sortable table of the 500 strongest DMRs with their nearest genes, and each DMR's normal and tumor values per patient |
| [`igv_report.html`](docs/reports/gse95654_20m/igv_report.html) | Genome browser (IGV, Integrative Genomics Viewer) view of the 25 strongest DMRs (differentially methylated regions) in each direction: pick a region from the table, then zoom out to see 2,000 bases either side |
| [`dss_execution_report.html`](docs/reports/gse95654_20m/dss_execution_report.html), [`dss_execution_timeline.html`](docs/reports/gse95654_20m/dss_execution_timeline.html) | The same for the DSS (Dispersion Shrinkage for Sequencing data) run |

## Run it

Requires [uv](https://docs.astral.sh/uv/), the AWS CLI (command-line interface) with credentials for the account, and the stack in `infra/aws/` deployed ([its README](infra/aws/README.md)). Nextflow runs inside Batch, so the laptop needs none. It bills your AWS (Amazon Web Services) account.

```bash
uv sync
uv run pytest
(cd r && Rscript tests/test_dss.R)   # R tests; renv installs DSS into r/renv on first use
cp .env.example .env   # fill in the AWS section from the stack outputs
```

Then one command per step, each waiting for the last to finish:

```bash
scripts/run.sh fetch_sra config/fetch_sra/gse95654_20m.yaml
scripts/run.sh methylseq config/methylseq/gse95654_20m.yaml
scripts/run.sh convert config/convert/gse95654_20m.yaml
scripts/run.sh qc config/qc/gse95654_20m.yaml
scripts/run.sh dss config/dss/gse95654_20m.yaml
```

The `convert`, `qc`, and `dss` params files name the exact upstream run they read, so after a new methylseq run, point them at its run ID. Add `--resume <session-id>` to pick up a failed run from cache. `scripts/run.sh methylseq config/methylseq/test.yaml` runs methylseq's bundled test data, a quick check that the pins and the stack work. `--compute local` (Docker, container software) and `--compute slurm` are there too, but they aren't the default.

`scripts/make_diagrams.py` redraws `docs/architecture.svg`.

## Limits

- **Downsampled.** 20 million read pairs per sample, of the 29.7 to 38.8 million each paired-end run has (58.9 to 70.4 million reads for the single-end runs). Median coverage is 4 to 7 reads per site.
- **Small.** 9 patients, 18 samples. Enough to show the pipeline and a tumor versus normal split, not enough to generalize.
- **RRBS (reduced representation bisulfite sequencing) is partial.** It reads CpG (cytosine followed by guanine)-rich regions such as promoters and CpG (cytosine followed by guanine) islands well and most of the genome not at all.
- **Tissue, not blood.** These are tumor and normal colon. MCED (multi-cancer early detection) tests read cell-free DNA (deoxyribonucleic acid) from blood, where tumor DNA (deoxyribonucleic acid) is a small fraction of the total; methyl-floor models that dilution.
- **One batch variable.** Read layout is the only batch recorded. Sequencing run and processing date aren't in the metadata.
- **Only sites covered in every sample are tested.** Requiring 5 reads in all 18 samples keeps 718,148 sites; the single-end patients cover the fewest, so they limit it most.
- **Annotation is by position.** Each DMR (differentially methylated region) is matched to the nearest protein-coding gene and the CpG (cytosine followed by guanine) island map. That says where a change sits, not what it does to the gene; no expression data was used.
- **No region-level error rate.** FDR (false discovery rate) controls false calls among sites; a DMR (differentially methylated region) is built from significant sites, but its own false call rate isn't estimated.

## Layout

```
scripts/run.sh        the one command: upload config and submit a run to AWS Batch
config/               params files per pipeline and dataset, the run manifest, compute profiles
pipelines/            this repo's Nextflow pipelines: fetch_sra, convert, qc, dss
src/methyl_flow/      conversion, QC table, plots, and the interactive reports
r/                    DSS differential methylation (R, its own renv project) and its tests
tests/                pytest tests on small fixture files, no network by default
infra/aws/            CDK stack for AWS Batch, S3, and the Nextflow head job
docs/                 walkthrough, software list, architecture diagram, images, reports
```

## Data citation

GSE95654 is public data from NCBI (National Center for Biotechnology Information) GEO (Gene Expression Omnibus) and SRA (Sequence Read Archive). If you use it, cite the study:

- Hanley, M. P., et al. "Genome-wide DNA methylation profiling reveals cancer-associated changes within early colonic neoplasia." *Oncogene*, 2017. [doi:10.1038/onc.2017.130](https://doi.org/10.1038/onc.2017.130)

The figures and reports in `docs/` are derived from that data.
