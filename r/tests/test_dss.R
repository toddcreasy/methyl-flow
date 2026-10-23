# Tests for dss.R on small synthetic Bismark coverage files. Run from r/, so renv activates:
#   cd r && Rscript tests/test_dss.R
# Base R only, so it runs in the same DSS container the pipeline uses.

source("dss.R")

PATIENTS <- sprintf("P%02d", 1:4)
SAMPLES <- as.vector(t(outer(PATIENTS, c("normal", "tumor"), paste, sep = "_")))

write_cov <- function(dir, sample, rows) {
  path <- file.path(dir, paste0(sample, "_1_val_1_bismark_bt2_pe.deduplicated.bismark.cov.gz"))
  con <- gzfile(path, "w")
  write.table(rows, con, sep = "\t", quote = FALSE, row.names = FALSE, col.names = FALSE)
  close(con)
  path
}

write_manifest <- function(dir) {
  path <- file.path(dir, "runs.tsv")
  fwrite(data.table(
    sample = SAMPLES,
    patient = rep(PATIENTS, each = 2),
    group = rep(c("normal", "tumor"), 4),
    layout = "paired",
    run = sprintf("SRR%d", seq_along(SAMPLES)),
    gsm = sprintf("GSM%d", seq_along(SAMPLES)),
    read_count = 1e6
  ), path, sep = "\t")
  path
}

# 300 background sites on chr2 and chr10 at beta ~0.5, plus 6 sites on chr2 where tumors are
# 90% methylated and normals 10%. Every site has 30 reads, so all pass a 5-read filter.
simulate <- function(dir, planted = TRUE, seed = 1) {
  set.seed(seed)
  sites <- rbind(
    data.table(chr = "chr10", pos = seq(1000, by = 37, length.out = 150)),
    data.table(chr = "chr2", pos = seq(1000, by = 41, length.out = 150)),
    data.table(chr = "chr2", pos = 50000 + c(0, 12, 30, 44, 61, 80))
  )
  in_dmr <- sites$chr == "chr2" & sites$pos >= 50000
  files <- vapply(SAMPLES, function(s) {
    p <- rep(0.5, nrow(sites))
    if (planted) p[in_dmr] <- if (endsWith(s, "tumor")) 0.9 else 0.1
    meth <- rbinom(nrow(sites), 30, p)
    rows <- rbindlist(list(
      data.table(sites$chr, sites$pos, sites$pos, 100 * meth / 30, meth, 30 - meth),
      # A low-coverage site and a mitochondrial site, both dropped by read_coverage
      list("chr2", 99, 99, 50, 1, 1),
      list("chrM", 5, 5, 0, 0, 40)
    ))
    write_cov(dir, s, rows)
  }, character(1))
  list(files = unname(files), manifest = write_manifest(dir))
}

tests <- list(
  read_coverage_filters_contig_and_depth = function() {
    dir <- tempfile(); dir.create(dir)
    path <- write_cov(dir, "S1", data.frame(
      c("chr1", "chr1", "chrM", "chr1_KI270706v1_random"), c(10, 20, 30, 40), c(10, 20, 30, 40),
      c(50, 0, 0, 0), c(3, 0, 0, 0), c(3, 4, 9, 9)
    ))
    dt <- read_coverage(path, 5)
    stopifnot(identical(dt$pos, 10L), dt$N == 6, dt$X == 3)
  },

  match_files_needs_exactly_one_file = function() {
    paths <- c("/x/P01_normal_1_val_1.cov.gz", "/x/P01_tumor_1_val_1.cov.gz")
    stopifnot(identical(unname(match_files(paths, "P01_tumor")), paths[2]))
    err <- tryCatch(match_files(paths, "P02_normal"), error = conditionMessage)
    stopifnot(grepl("expected one coverage file, found 0", err))
  },

  common_sites_keeps_shared_sites_in_genome_order = function() {
    a <- data.table(chr = c("chr10", "chr2", "chr2"), pos = c(5, 7, 9), N = 10, X = 1:3)
    b <- data.table(chr = c("chr2", "chr10", "chrX"), pos = c(9, 5, 1), N = 20, X = 4:6)
    out <- common_sites(list(a = a, b = b))
    stopifnot(
      identical(out$a$chr, c("chr2", "chr10")), identical(out$a$pos, c(9, 5)),
      identical(out$b$X, 4:5)
    )
  },

  paired_test_finds_the_planted_region = function() {
    dir <- tempfile(); dir.create(dir)
    sim <- simulate(dir)
    res <- run_dss(sim$files, sim$manifest, min_reads = 5)
    s <- setNames(as.numeric(res$summary$value), res$summary$metric)
    stopifnot(
      s[["sites_tested"]] == 306,
      s[["sites_significant"]] >= 4,
      s[["dmrs"]] >= 1, s[["dmrs_hyper"]] == s[["dmrs"]]
    )
    top <- res$dmrs[1]
    stopifnot(
      top$chr == "chr2", top$start >= 50000, top$end <= 50080,
      top$diff > 0.6, top$beta_tumor > 0.8, top$beta_normal < 0.2
    )
    # One row per DMR and sample, with the design attached
    stopifnot(nrow(res$dmr_samples) == nrow(res$dmrs) * 8, all(c("patient", "tissue") %in% names(res$dmr_samples)))
    out <- file.path(dir, "out")
    write_results(res, out)
    stopifnot(all(file.exists(file.path(out, c("dml.tsv.gz", "dmrs.tsv", "summary.tsv")))))
    stopifnot(nrow(fread(file.path(out, "dml.tsv.gz"))) == 306)
  },

  no_difference_gives_no_dmrs = function() {
    dir <- tempfile(); dir.create(dir)
    sim <- simulate(dir, planted = FALSE)
    res <- run_dss(sim$files, sim$manifest, min_reads = 5)
    stopifnot(nrow(res$dmrs) == 0, nrow(res$dmr_samples) == 0)
    write_results(res, file.path(dir, "out"))
  }
)

failed <- 0
for (name in names(tests)) {
  ok <- tryCatch({
    suppressMessages(tests[[name]]())
    TRUE
  }, error = function(e) {
    message("FAIL ", name, ": ", conditionMessage(e))
    FALSE
  })
  if (ok) message("ok   ", name)
  failed <- failed + !ok
}
if (failed) quit(status = 1)
