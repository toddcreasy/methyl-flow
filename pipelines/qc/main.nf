/*
 * QC summary and plots for a methylseq Bismark run and its converted beta table.
 *
 * Writes to params.outdir:
 *   samples_qc.tsv       one row per sample: conversion rate, duplicate rate, coverage
 *   coverage_hist.tsv    sites per read count, per sample
 *   plots/               coverage.png, methylation.png, pca.png, pca.tsv
 *   report.html          interactive version of the table and plots
 *
 * The work is src/methyl_flow/qc.py, plots.py, and report.py, tested in tests/test_qc.py,
 * test_plots.py, and test_report.py.
 */

params.samples           = null   // samples.tsv from a convert run
params.betas             = null   // betas/<study>.parquet from the same convert run
params.splitting_reports = null   // glob of Bismark *_splitting_report.txt from methylseq
params.coverage          = null   // glob of Bismark .cov.gz files from methylseq
params.fastqc            = null   // multiqc_fastqc.txt from methylseq's MultiQC data folder
params.min_coverage      = 10
params.max_bin           = 100
params.outdir            = null   // set by scripts/run.sh

process QC_TABLE {
    publishDir params.outdir, mode: 'copy'

    input:
    path src
    path samples
    path fastqc
    path reports
    path coverage

    output:
    path 'samples_qc.tsv', emit: table
    path 'coverage_hist.tsv', emit: hist

    script:
    """
    PYTHONPATH=${src} python -m methyl_flow.qc \\
        --samples ${samples} \\
        --fastqc ${fastqc} \\
        --splitting-reports ${reports} \\
        --coverage ${coverage} \\
        --min-coverage ${params.min_coverage} \\
        --max-bin ${params.max_bin} \\
        --out .
    """
}

process QC_PLOTS {
    publishDir params.outdir, mode: 'copy'

    input:
    path src
    path table
    path hist
    path betas

    output:
    path 'plots/*'
    path 'report.html'

    script:
    """
    PYTHONPATH=${src} python -m methyl_flow.plots \\
        --samples ${table} \\
        --coverage-hist ${hist} \\
        --betas ${betas} \\
        --min-coverage ${params.min_coverage} \\
        --max-bin ${params.max_bin} \\
        --out plots \\
        --report report.html \\
        --title '${workflow.runName}'
    """
}

workflow {
    if (!params.samples || !params.betas || !params.splitting_reports || !params.coverage || !params.fastqc) {
        error "Set samples, betas, splitting_reports, coverage, and fastqc in the params file"
    }

    src = file("${projectDir}/../../src", checkIfExists: true)
    QC_TABLE(
        src,
        file(params.samples, checkIfExists: true),
        file(params.fastqc, checkIfExists: true),
        Channel.fromPath(params.splitting_reports, checkIfExists: true).collect(),
        Channel.fromPath(params.coverage, checkIfExists: true).collect(),
    )
    QC_PLOTS(src, QC_TABLE.out.table, QC_TABLE.out.hist, file(params.betas, checkIfExists: true))
}
