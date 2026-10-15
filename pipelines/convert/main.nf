/*
 * Convert methylseq's Bismark coverage files into methyl-floor's beta table and sample sheet.
 *
 * Writes to params.outdir:
 *   samples.tsv               one row per sample, methyl-floor's sample sheet columns
 *   betas/<study>.parquet     one row per CpG cytosine, one beta column per sample
 *
 * The conversion itself is src/methyl_flow/convert.py, tested in tests/test_convert.py.
 */

params.coverage      = null   // glob of Bismark .cov.gz files from a methylseq run
params.manifest      = null   // TSV: sample, patient, group, layout, run, gsm, read_count
params.study         = null
params.disease_state = null
params.pipeline      = null   // pipeline and version that made the coverage files
params.min_coverage  = 10
params.outdir        = null   // set by scripts/run.sh

process CONVERT {
    publishDir params.outdir, mode: 'copy'

    input:
    path script
    path manifest
    path coverage

    output:
    path 'samples.tsv'
    path 'betas/*.parquet'

    script:
    """
    python ${script} ${coverage} \\
        --manifest ${manifest} \\
        --study '${params.study}' \\
        --disease-state '${params.disease_state}' \\
        --pipeline '${params.pipeline}' \\
        --min-coverage ${params.min_coverage} \\
        --out .
    """
}

workflow {
    if (!params.coverage || !params.manifest || !params.study || !params.disease_state || !params.pipeline) {
        error "Set coverage, manifest, study, disease_state, and pipeline in the params file"
    }

    CONVERT(
        file("${projectDir}/../../src/methyl_flow/convert.py", checkIfExists: true),
        file(params.manifest, checkIfExists: true),
        Channel.fromPath(params.coverage, checkIfExists: true).collect(),
    )
}
