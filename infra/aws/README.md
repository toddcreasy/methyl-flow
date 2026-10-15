# infra/aws

CDK (Cloud Development Kit) app, in Python, that provisions the AWS (Amazon Web Services) Batch
infrastructure the `aws` profile in `config/methylseq/compute.config` expects: an S3 (Amazon Simple
Storage Service) bucket for the work dir and results, a VPC (virtual private cloud) with no NAT
(network address translation) gateway, and two Batch job queues, `methyl-flow-spot` and
`methyl-flow-ondemand`.

Adapted from nf-multiomics' `infra/aws`. Differences: queue names, every resource tagged
`project=methyl-flow`, `env=dev`, `managed-by=cdk`, a 64 vCPU (virtual CPU) ceiling instead of 256,
and a 200 GB (gigabyte) root volume instead of 500.

## Deploy

Needs the AWS CDK CLI (command-line interface), `uv`, and credentials for the account
(`aws sso login`). The account is already bootstrapped (`CDKToolkit` stack).

```bash
cd infra/aws
uv sync
uv run pytest
cdk deploy MethylFlowBatchStack --outputs-file cdk-outputs.json
```

Context defaults (override with `cdk deploy -c max_vcpus=128`):

- `max_vcpus` (default `64`): ceiling for each compute environment
- `root_volume_gb` (default `200`): root EBS (Elastic Block Store) volume on Batch instances
- `bucket_name` (default unset): use an existing bucket instead of creating one

## Wire it into the repo

Copy the `EnvSnippet` output into the repo root `.env`:

```
AWS_REGION=<Region output>
AWS_BATCH_QUEUE=<SpotQueue output>
AWS_S3_WORKDIR=<WorkDir output>
AWS_S3_OUTDIR=<OutDir output>
```

Then `scripts/run_methylseq.sh <params-file> --compute aws` picks it up.

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
