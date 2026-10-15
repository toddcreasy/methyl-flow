# infra/aws

CDK (Cloud Development Kit) app, in Python, that provisions the AWS (Amazon Web Services) Batch
infrastructure the `aws` profile in `config/methylseq/compute.config` expects: an S3 (Amazon Simple
Storage Service) bucket for the work dir and results, a VPC (virtual private cloud) with no NAT
(network address translation) gateway, and two Batch job queues, `methyl-flow-spot` and
`methyl-flow-ondemand`. It also runs the Nextflow head process itself, as a Batch job, so a
laptop only submits runs:

- `methyl-flow-nextflow-head` job definition: `nextflow/nextflow:25.04.0`, 2 vCPUs (virtual CPUs),
  6 GiB (gibibytes), on the on-demand queue. A Spot reclaim of the head job would kill the whole run.
- Head job role with the Batch, EC2 (Elastic Compute Cloud), ECS (Elastic Container Service), and
  logs actions Nextflow's awsbatch executor needs (https://docs.seqera.io/nextflow/aws), plus
  read/write on the bucket.
- `methyl-flow/tower-access-token` secret for Seqera Platform, injected as `TOWER_ACCESS_TOKEN`.
  Only the head job's execution role can read it.
- `methyl-flow-monthly` budget: $50, filtered to the `project=methyl-flow` cost allocation tag,
  email alerts at 80% and 100% actual and 100% forecast. Created only when `alert_email` is set
  in context.

Adapted from nf-multiomics' `infra/aws`. Differences: queue names, every resource tagged
`project=methyl-flow`, `env=dev`, `managed-by=cdk`, a 256 vCPU (virtual CPU) ceiling (raised from 64 on 2026-10-15 when 18 parallel alignments queued behind it),
and a 200 GB (gigabyte) root volume instead of 500.

## Deploy

Needs the AWS CDK CLI (command-line interface), `uv`, and credentials for the account
(`aws sso login`). The account is already bootstrapped (`CDKToolkit` stack).

```bash
cd infra/aws
uv sync
uv run pytest
cdk deploy MethylFlowBatchStack -c alert_email=<you@example.com> --outputs-file cdk-outputs.json
```

To keep the budget on later deploys, put `"alert_email": "<you@example.com>"` in
`cdk.context.json` (gitignored).

After the first deploy, set the Seqera token. This reads it from the repo `.env`, so the value is
never typed or printed:

```bash
aws secretsmanager put-secret-value --secret-id methyl-flow/tower-access-token \
  --secret-string "$(grep '^TOWER_ACCESS_TOKEN=' ../../.env | cut -d= -f2- | tr -d '"')" \
  --query VersionId --output text
```

Context defaults (override with `cdk deploy -c max_vcpus=128`):

- `max_vcpus` (default `256`): ceiling for each compute environment
- `root_volume_gb` (default `200`): root EBS (Elastic Block Store) volume on Batch instances
- `bucket_name` (default unset): use an existing bucket instead of creating one

## Wire it into the repo

Copy the outputs into the repo root `.env`:

```
AWS_REGION=<Region output>
BATCH_QUEUE=<SpotQueue output>
AWS_HEAD_QUEUE=<OnDemandQueue output>
AWS_HEAD_JOB_DEFINITION=<HeadJobDefinitionName output>
AWS_S3_WORKDIR=<WorkDir output>
AWS_S3_OUTDIR=<OutDir output>
AWS_S3_RUNDIR=s3://<BucketName output>/runs
```

Then `scripts/run.sh <pipeline> <params-file>` (AWS is the default compute) uploads `config/` and
`pipelines/` to `$AWS_S3_RUNDIR/<run name>/`, submits the head job, and exits.

## Cost

Idle cost is close to zero: no NAT gateway, and both compute environments have `minvCpus=0`, so
they scale to no running instances between jobs. Compute is billed only while jobs run, at Spot or
on-demand rates. The `work/` prefix expires after 30 days; anything under `results/` stays until
deleted. Tags let Cost Explorer show this stack's spend under `project=methyl-flow`.

## Teardown

```bash
cdk destroy MethylFlowBatchStack
```

The bucket has `RemovalPolicy.RETAIN`, so it survives `cdk destroy` and has to be emptied and
deleted by hand.
