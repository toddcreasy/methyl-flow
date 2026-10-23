# Differential methylation between tumor and normal with DSS, paired by patient.
#
# Reads Bismark coverage files (chrom, start, end, percent, methylated, unmethylated), keeps
# CpG cytosines with at least `min_reads` reads in every sample, fits DSS's beta-binomial model
# ~ patient + tissue, and tests the tissue coefficient at each site. DMRs are runs of nearby
# sites whose p-value is at or below the largest p-value among sites with FDR < `fdr_level`, so every
# DMR is built only from FDR-significant sites.
#
# The two cytosines of a CpG, one per strand, stay separate sites, as in convert.py.

suppressPackageStartupMessages({
  library(data.table)
  library(DSS)
})

CHROMOSOMES <- paste0("chr", c(1:22, "X", "Y"))

# Two warnings DSS always raises on this input, both harmless:
# - makeBSseqData merges samples with base merge(), which sorts positions as text, then warns and
#   re-sorts each chromosome numerically.
# - callDMR averages two-group means (mu1, mu2) that a multifactor test doesn't produce, so they
#   come out NA. Group means are computed here instead.
KNOWN_WARNINGS <- "is not ordered\\. Reorder CG sites|argument is not numeric or logical"

quiet <- function(expr) {
  withCallingHandlers(expr, warning = function(w) {
    if (grepl(KNOWN_WARNINGS, conditionMessage(w))) invokeRestart("muffleWarning")
  })
}

read_coverage <- function(path, min_reads) {
  dt <- fread(
    cmd = paste("gzip -dc", shQuote(path)),
    header = FALSE,
    select = c(1, 2, 5, 6),
    col.names = c("chr", "pos", "methylated", "unmethylated")
  )
  dt <- dt[chr %in% CHROMOSOMES]
  dt[, N := methylated + unmethylated]
  dt[N >= min_reads, .(chr, pos, N, X = methylated)]
}

match_files <- function(paths, samples) {
  files <- vapply(samples, function(s) {
    hits <- paths[startsWith(basename(paths), paste0(s, "_"))]
    if (length(hits) != 1) stop(sprintf("%s: expected one coverage file, found %d", s, length(hits)))
    hits
  }, character(1))
  setNames(files, samples)
}

# Keep sites present in every table, in the same order in each.
common_sites <- function(tables) {
  keys <- Reduce(function(a, b) fintersect(a, b), lapply(tables, function(t) t[, .(chr, pos)]))
  keys[, chr := factor(chr, levels = CHROMOSOMES)]
  setorder(keys, chr, pos)
  keys[, chr := as.character(chr)]
  lapply(tables, function(t) t[keys, on = .(chr, pos)])
}

# Per-sample beta values (sites x samples) from the aligned tables.
beta_matrix <- function(tables) {
  do.call(cbind, lapply(tables, function(t) t$X / t$N))
}

group_means <- function(betas, tissue) {
  normal <- rowMeans(betas[, tissue == "normal", drop = FALSE])
  tumor <- rowMeans(betas[, tissue == "tumor", drop = FALSE])
  data.table(beta_normal = normal, beta_tumor = tumor, diff = tumor - normal)
}

# Mean beta per sample over each DMR's sites; one row per DMR and sample.
dmr_sample_betas <- function(dmrs, sites, betas, design) {
  if (!nrow(dmrs)) {
    return(data.table(
      sample = character(), dmr_id = character(), beta = numeric(),
      sample_id = character(), patient = character(), tissue = character()
    ))
  }
  sites <- copy(sites)[, row := .I]
  hits <- sites[dmrs, on = .(chr, pos >= start, pos <= end), .(dmr_id = i.dmr_id, row = x.row)]
  per_dmr <- hits[, as.list(colMeans(betas[row, , drop = FALSE])), by = dmr_id]
  long <- melt(per_dmr, id.vars = "dmr_id", variable.name = "sample", value.name = "beta")
  long[, sample := as.character(sample)]
  merge(long, design[, .(sample, sample_id, patient, tissue)], by = "sample")[order(dmr_id, sample)]
}

run_dss <- function(coverage, manifest, min_reads = 5, fdr_level = 0.05, min_cg = 3) {
  design <- fread(manifest)[, .(sample, sample_id = gsm, patient, tissue = group, layout)]
  files <- match_files(coverage, design$sample)
  tables <- lapply(setNames(design$sample, design$sample), function(s) {
    t <- read_coverage(files[[s]], min_reads)
    message(sprintf("%s: %d sites at >= %d reads", s, nrow(t), min_reads))
    t
  })
  tables <- common_sites(tables)
  sites <- tables[[1]][, .(chr, pos)]
  message(sprintf("%d sites with >= %d reads in all %d samples", nrow(sites), min_reads, nrow(design)))

  bs <- quiet(makeBSseqData(lapply(tables, as.data.frame), design$sample))
  model <- data.frame(
    patient = factor(design$patient),
    tissue = factor(design$tissue, levels = c("normal", "tumor"))
  )
  fit <- DMLfit.multiFactor(bs, design = model, formula = ~ patient + tissue)
  test <- as.data.table(DMLtest.multiFactor(fit, coef = "tissuetumor"))

  betas <- beta_matrix(tables)
  colnames(betas) <- design$sample
  dml <- cbind(sites, group_means(betas, design$tissue))[test, on = .(chr, pos)]
  dml <- dml[, .(chr, pos, stat, pval = pvals, fdr = fdrs, beta_normal, beta_tumor, diff)]

  significant <- dml[!is.na(fdr) & fdr < fdr_level]
  p_threshold <- if (nrow(significant)) max(significant$pval) else NA_real_
  dmrs <- empty_dmrs()
  if (!is.na(p_threshold)) {
    # callDMR keeps sites with p < cutoff. Under Benjamini-Hochberg every site with a smaller
    # p-value than a significant one is also significant, so the smallest non-significant p-value
    # is the cutoff that keeps exactly the FDR-significant sites.
    cutoff <- min(c(dml[is.na(fdr) | fdr >= fdr_level, pval], 1.1))
    called <- quiet(callDMR(as.data.frame(test), p.threshold = cutoff, minCG = min_cg))
    if (!is.null(called)) {
      dmrs <- as.data.table(called)[, .(
        chr,
        start = as.integer(start), end = as.integer(end), length = as.integer(length),
        n_cpg = as.integer(nCG), area_stat = areaStat
      )]
    }
  }
  dmrs <- dmrs[order(-abs(area_stat))]
  dmrs[, dmr_id := sprintf("DMR%04d", .I)]
  per_sample <- dmr_sample_betas(dmrs, sites, betas, design)
  means <- per_sample[, .(
    beta_normal = mean(beta[tissue == "normal"]),
    beta_tumor = mean(beta[tissue == "tumor"])
  ), by = dmr_id]
  dmrs <- merge(dmrs, means, by = "dmr_id", all.x = TRUE)[order(dmr_id)]
  dmrs[, diff := beta_tumor - beta_normal]
  setcolorder(dmrs, "dmr_id")

  summary <- data.table(
    metric = c(
      "samples", "patients", "min_reads", "min_cg", "sites_tested", "fdr", "p_threshold",
      "sites_significant", "sites_hyper", "sites_hypo", "dmrs", "dmrs_hyper", "dmrs_hypo"
    ),
    value = c(
      nrow(design), uniqueN(design$patient), min_reads, min_cg, nrow(dml), fdr_level, p_threshold,
      nrow(significant), sum(significant$stat > 0), sum(significant$stat < 0),
      nrow(dmrs), sum(dmrs$area_stat > 0), sum(dmrs$area_stat < 0)
    )
  )
  list(dml = dml, dmrs = dmrs, dmr_samples = per_sample, summary = summary, design = design)
}

empty_dmrs <- function() {
  data.table(
    chr = character(), start = integer(), end = integer(), length = integer(),
    n_cpg = integer(), area_stat = numeric()
  )
}

write_results <- function(res, out) {
  dir.create(out, showWarnings = FALSE, recursive = TRUE)
  fwrite(res$dml, file.path(out, "dml.tsv.gz"), sep = "\t")
  fwrite(res$dmrs, file.path(out, "dmrs.tsv"), sep = "\t")
  fwrite(res$dmr_samples, file.path(out, "dmr_samples.tsv"), sep = "\t")
  fwrite(res$summary, file.path(out, "summary.tsv"), sep = "\t")
  fwrite(res$design, file.path(out, "design.tsv"), sep = "\t")
}
