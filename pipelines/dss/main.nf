/*
 * Differential methylation, tumor against matched normal, with DSS on methylseq's Bismark
 * coverage files.
 *
 * Writes to params.outdir:
 *   dml.tsv.gz          one row per tested CpG site: test statistic, p-value, FDR, group means
 *   dmrs.tsv            DMRs built from FDR-significant sites, strongest first
 *   dmr_samples.tsv     mean beta over each DMR's sites, per sample
 *   summary.tsv         sites tested, significant sites, and DMRs, by direction
 *   design.tsv          the samples and model terms used
 *   plots/              volcano.png, top_dmrs.png
 *   report.html         interactive version of the above
 *
 * The statistics are r/dss.R (tested in r/tests/test_dss.R); the plots and report are
 * src/methyl_flow/dmr_report.py (tested in tests/test_dmr_report.py).
 */

params.coverage  = null   // glob of Bismark .cov.gz files from a methylseq run
params.manifest  = null   // TSV: sample, patient, group, layout, run, gsm, read_count
params.min_reads = 5      // a site is tested only if every sample has this many reads
params.fdr       = 0.05
params.min_cg    = 3      // fewest significant CpG sites in a DMR
params.outdir    = null   // set by scripts/run.sh

process DSS_TEST {
    publishDir params.outdir, mode: 'copy'

    input:
    path r_dir
    path manifest
    path coverage

    output:
    path '*.tsv', emit: tables
    path 'dml.tsv.gz', emit: dml

    script:
    """
    Rscript --no-init-file ${r_dir}/run_dss.R \\
        --manifest ${manifest} \\
        --min-reads ${params.min_reads} \\
        --fdr ${params.fdr} \\
        --min-cg ${params.min_cg} \\
        --out . \\
        ${coverage}
    """
}

process DSS_REPORT {
    publishDir params.outdir, mode: 'copy'

    input:
    path src
    path tables, stageAs: 'dss/*'
    path dml, stageAs: 'dss/*'

    output:
    path 'plots/*'
    path 'report.html'

    script:
    """
    PYTHONPATH=${src} python -m methyl_flow.dmr_report --dss dss --out . --title '${workflow.runName}'
    """
}

workflow {
    if (!params.coverage || !params.manifest) {
        error "Set coverage and manifest in the params file"
    }

    DSS_TEST(
        file("${projectDir}/../../r", checkIfExists: true),
        file(params.manifest, checkIfExists: true),
        Channel.fromPath(params.coverage, checkIfExists: true).collect(),
    )
    DSS_REPORT(file("${projectDir}/../../src", checkIfExists: true), DSS_TEST.out.tables, DSS_TEST.out.dml)
}
