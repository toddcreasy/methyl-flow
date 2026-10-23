# Command line for dss.R:
#
#   Rscript run_dss.R --manifest runs.tsv --out <dir> [--min-reads 5] [--fdr 0.05] [--min-cg 3] \
#       <coverage .cov.gz files>
#
# Writes dml.tsv.gz, dmrs.tsv, dmr_samples.tsv, summary.tsv, and design.tsv to --out.

args <- commandArgs(trailingOnly = TRUE)
script_dir <- dirname(normalizePath(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE))))
source(file.path(script_dir, "dss.R"))

opts <- list(min_reads = "5", fdr = "0.05", min_cg = "3")
coverage <- character()
i <- 1
while (i <= length(args)) {
  if (startsWith(args[i], "--")) {
    opts[[gsub("-", "_", sub("^--", "", args[i]))]] <- args[i + 1]
    i <- i + 2
  } else {
    coverage <- c(coverage, args[i])
    i <- i + 1
  }
}
if (is.null(opts$manifest) || is.null(opts$out) || !length(coverage)) {
  stop("usage: Rscript run_dss.R --manifest runs.tsv --out <dir> <coverage files>")
}

res <- run_dss(
  coverage,
  opts$manifest,
  min_reads = as.integer(opts$min_reads),
  fdr_level = as.numeric(opts$fdr),
  min_cg = as.integer(opts$min_cg)
)
write_results(res, opts$out)
print(res$summary)
