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
 *   dmrs_annotated.tsv  each DMR's CpG island context, promoter overlap, and nearest gene
 *   annotation_enrichment.tsv  CpG island and gene context of tested, significant, and DMR sites
 *   plots/              volcano.png, top_dmrs.png, annotation.png
 *   report.html         interactive version of the above
 *   igv/igv_report.html genome browser view (IGV, Integrative Genomics Viewer) of the strongest
 *                       DMRs, with normal and tumor methylation, DMR, CpG island, and gene tracks
 *
 * The statistics are r/dss.R (tested in r/tests/test_dss.R); the annotation is
 * src/methyl_flow/annotate.py (tests/test_annotate.py); the plots and report are
 * src/methyl_flow/dmr_report.py (tests/test_dmr_report.py); the IGV tracks are
 * src/methyl_flow/igv_tracks.py (tests/test_igv_tracks.py), rendered by igv-reports.
 */

params.coverage  = null   // glob of Bismark .cov.gz files from a methylseq run
params.manifest  = null   // TSV: sample, patient, group, layout, run, gsm, read_count
params.min_reads = 5      // a site is tested only if every sample has this many reads
params.fdr       = 0.05
params.min_cg    = 3      // fewest significant CpG sites in a DMR
params.gtf             = null   // GENCODE GTF URL or path, gzipped
params.gtf_md5         = null
params.cpg_islands     = null   // UCSC cpgIslandExt.txt.gz URL or path
params.cpg_islands_content_md5 = null   // MD5 after gunzip
params.igv_per_direction = 25   // strongest DMRs shown in each direction
params.igv_flank         = 2000 // bases loaded either side of each DMR
params.igv_twobit        = 'https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.2bit'
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

process ANNOTATE {
    publishDir params.outdir, mode: 'copy'

    input:
    path src
    path tables, stageAs: 'dss/*'
    path dml, stageAs: 'dss/*'
    path gtf
    path cpg_islands

    output:
    path '*.tsv'

    script:
    """
    PYTHONPATH=${src} python -m methyl_flow.annotate \\
        --dss dss \\
        --gtf ${gtf} --gtf-md5 ${params.gtf_md5} \\
        --cpg-islands ${cpg_islands} --cpg-islands-content-md5 ${params.cpg_islands_content_md5} \\
        --fdr ${params.fdr} \\
        --out .
    """
}

process IGV_TRACKS {
    input:
    path src
    path dml, stageAs: 'dss/*'
    path annotation, stageAs: 'dss/*'
    path gtf
    path cpg_islands

    output:
    path 'tracks/*'

    script:
    """
    PYTHONPATH=${src} python -m methyl_flow.igv_tracks \\
        --dss dss \\
        --gtf ${gtf} \\
        --cpg-islands ${cpg_islands} \\
        --per-direction ${params.igv_per_direction} \\
        --flank ${params.igv_flank} \\
        --out tracks
    """
}

process IGV_REPORT {
    publishDir "${params.outdir}/igv", mode: 'copy'

    input:
    path tracks

    output:
    path 'igv_report.html'

    script:
    """
    create_report sites.tsv \\
        --sequence 1 --begin 2 --end 3 \\
        --twobit ${params.igv_twobit} \\
        --track-config tracks.json \\
        --flanking ${params.igv_flank} \\
        --info-columns dmr_id direction nearest_gene tss_distance cpg_context n_cpg beta_normal beta_tumor diff \\
        --title '${workflow.runName}: strongest DMRs' \\
        --output igv_report.html
    # igv-reports' default template labels the table "Variants"
    sed -i 's|class="lbl-toggle">Variants<|class="lbl-toggle">DMRs (differentially methylated regions)<|' igv_report.html
    grep -q 'lbl-toggle">DMRs' igv_report.html
    """
}

process DSS_REPORT {
    publishDir params.outdir, mode: 'copy'

    input:
    path src
    path tables, stageAs: 'dss/*'
    path dml, stageAs: 'dss/*'
    path annotation, stageAs: 'dss/*'

    output:
    path 'plots/*'
    path 'report.html'

    script:
    """
    PYTHONPATH=${src} python -m methyl_flow.dmr_report --dss dss --out . --title '${workflow.runName}'
    """
}

workflow {
    if (!params.coverage || !params.manifest || !params.gtf || !params.cpg_islands) {
        error "Set coverage, manifest, gtf, and cpg_islands in the params file"
    }
    src = file("${projectDir}/../../src", checkIfExists: true)

    DSS_TEST(
        file("${projectDir}/../../r", checkIfExists: true),
        file(params.manifest, checkIfExists: true),
        Channel.fromPath(params.coverage, checkIfExists: true).collect(),
    )
    ANNOTATE(
        src,
        DSS_TEST.out.tables,
        DSS_TEST.out.dml,
        file(params.gtf, checkIfExists: true),
        file(params.cpg_islands, checkIfExists: true),
    )
    DSS_REPORT(src, DSS_TEST.out.tables, DSS_TEST.out.dml, ANNOTATE.out)
    IGV_TRACKS(
        src,
        DSS_TEST.out.dml,
        ANNOTATE.out,
        file(params.gtf, checkIfExists: true),
        file(params.cpg_islands, checkIfExists: true),
    )
    IGV_REPORT(IGV_TRACKS.out)
}
