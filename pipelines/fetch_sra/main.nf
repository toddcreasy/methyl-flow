/*
 * Fetch SRA runs with full-quality base scores, downsample them, and fetch the reference.
 *
 * Writes to params.data_dir:
 *   fastq/<sample>_R1.fastq.gz (and _R2 for paired-end)
 *   references/<fasta file name>
 *   samplesheet.csv   nf-core/methylseq input (sample,fastq_1,fastq_2,genome)
 *
 * nf-core/fetchngs covers downloading, but it does not force SRA Normalized (full-quality)
 * files, cannot downsample, and cannot write a methylseq samplesheet, so this pipeline
 * does those three steps.
 */

params.runs      = null   // TSV: sample, patient, group, layout, run, gsm, read_count
params.reads     = 5000000
params.seed      = 42
params.fasta     = null   // URL of the reference FASTA
params.fasta_md5 = null
params.data_dir  = null   // where the fetched data goes, e.g. s3://bucket/data/gse95654
params.outdir    = null   // run reports (set by scripts/run.sh)

process FETCH_AND_SAMPLE {
    tag "${meta.sample}"
    publishDir "${params.data_dir}/fastq", mode: 'copy'

    input:
    val meta

    output:
    tuple val(meta), path("${meta.sample}_R*.fastq.gz")

    script:
    def run = meta.run
    def mates = meta.layout == 'paired' ? '1 2' : '1'
    """
    # SRA Lite replaces every base quality with a constant; trimming and Bismark need real ones
    export HOME=\$PWD
    vdb-config --simplified-quality-scores no
    prefetch --max-size u ${run}
    if [ ! -f ${run}/${run}.sra ]; then
        echo "${run}: no full-quality .sra file, got: \$(ls ${run})" >&2
        exit 1
    fi

    fasterq-dump --split-3 --threads ${task.cpus} ${run}/${run}.sra
    rm -rf ${run}

    for m in ${mates}; do
        if [ "${meta.layout}" = paired ]; then fq=${run}_\$m.fastq; else fq=${run}.fastq; fi
        # Same seed on R1 and R2 keeps read pairs in sync
        seqtk sample -2 -s ${params.seed} \$fq ${params.reads} | gzip -1 > ${meta.sample}_R\$m.fastq.gz
        rm \$fq
    done
    """
}

process FETCH_REFERENCE {
    tag "${fasta.name}"
    publishDir "${params.data_dir}/references", mode: 'copy'

    input:
    path fasta

    output:
    path fasta

    script:
    """
    echo "${params.fasta_md5}  ${fasta}" | md5sum -c -
    """
}

workflow {
    if (!params.runs || !params.data_dir || !params.fasta || !params.fasta_md5) {
        error "Set runs, data_dir, fasta, and fasta_md5 in the params file"
    }

    runs = Channel.fromPath(params.runs, checkIfExists: true)
        .splitCsv(header: true, sep: '\t')

    FETCH_AND_SAMPLE(runs)
    FETCH_REFERENCE(file(params.fasta))

    FETCH_AND_SAMPLE.out
        .map { meta, _fastqs ->
            def base = "${params.data_dir}/fastq/${meta.sample}"
            def r2 = meta.layout == 'paired' ? "${base}_R2.fastq.gz" : ''
            "${meta.sample},${base}_R1.fastq.gz,${r2},"
        }
        .collectFile(
            name: 'samplesheet.csv',
            storeDir: params.data_dir,
            seed: 'sample,fastq_1,fastq_2,genome',
            newLine: true,
            sort: true,
        )
}
