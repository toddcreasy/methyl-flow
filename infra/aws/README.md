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
- `ami_id` (pinned in `cdk.json`): Batch instance AMI (Amazon Machine Image). A new AMI rolls every
  instance and stops running jobs after 30 minutes, so change it only when the queues are idle.
  Remove it to resolve the latest ECS (Elastic Container Service) optimized Amazon Linux 2023 AMI.
- `seqera_external_id` (in `cdk.context.json`): external ID Seqera generated for the
  `methyl-flow-aws-role` credential. Without it the `methyl-flow-seqera` role falls back to a
  placeholder and Seqera loses access on the next deploy.

## Seqera Platform

`methyl-flow-seqera` is the IAM (Identity and Access Management) role behind the Seqera Platform
credential `methyl-flow-aws-role` and the manual compute environment `methyl-flow-aws-batch`
(head queue `methyl-flow-ondemand`, compute queue `methyl-flow-spot`, head job role from the
`HeadJobRoleArn` output, 2 CPUs and 6144 MiB (mebibytes) for the head job). Only Seqera Cloud's
`SeqeraPlatformCloudAccessRole` can assume it, and only with the external ID. It submits and
watches jobs on the two queues, passes the head job role, and reads logs and the bucket; it
creates no Batch or IAM resources.

Seqera generates the external ID when the credential is saved, which needs the role's ARN
(Amazon Resource Name) first. So the first deploy uses a placeholder; save the credential with the
`SeqeraRoleArn` output, then redeploy with `-c seqera_external_id=<id>` and keep that value in
`cdk.context.json`.

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

## Results site

`MethylFlowSiteStack` (`stacks/site_stack.py`) is separate from the Batch stack so the data bucket
stays private. It has one bucket with all public access blocked, read only by CloudFront through
Origin Access Control, HTTPS (secure HTTP) only, security headers, and the cheapest price class
(North America and Europe edges). `scripts/publish_site.sh` fills it; the bucket is emptied and
deleted with the stack, since its contents are rebuilt on every publish.

```bash
cdk deploy MethylFlowSiteStack
```

Outputs: `SiteUrl`, `SiteBucketName`, `DistributionId`. The publish script reads them itself.

## Repo traffic

GitHub keeps repo views and clones for 14 days. `MethylFlowTrafficStack` (`stacks/traffic_stack.py`,
ported from glia-nav) runs the `methyl-flow-github-traffic` Lambda at 12:00 UTC (Coordinated
Universal Time). It writes the raw API response to `snapshots/<date>.json` in the
`TrafficBucketName` bucket, merges the daily counts into `history.json` there, and emails a summary
through the `methyl-flow-traffic` SNS (Simple Notification Service) topic to `traffic_email`. A
failed run alarms through the same topic (`methyl-flow-github-traffic-errors`).

The traffic API needs a fine-grained PAT (personal access token) with Administration read on this
repo, stored in the `methyl-flow/github-traffic-token` secret. glia-nav's PAT covers both repos, so
the value is copied from `glia-nav/github-traffic-token`; when it expires, renew it once and copy it
to both secrets.

```bash
cdk deploy MethylFlowTrafficStack -c traffic_email=<you@example.com>
```

Keep `"traffic_email"` in `cdk.context.json` (gitignored): the app builds every stack on each
`cdk` command, so deploys of the other stacks need it too. Clone counts include every CI
(continuous integration) checkout and the bots that clone new public repos; read views, not clones.

## Teardown

```bash
cdk destroy MethylFlowBatchStack
```

The bucket has `RemovalPolicy.RETAIN`, so it survives `cdk destroy` and has to be emptied and
deleted by hand.
