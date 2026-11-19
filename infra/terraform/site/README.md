# infra/terraform/site

Terraform for the public results site, plus the read-only role GitHub Actions uses to plan it. The
pipeline infrastructure stays in the CDK (Cloud Development Kit) app in `infra/aws/`.

| File | What it holds |
|---|---|
| `main.tf` | S3 (Amazon Simple Storage Service) bucket with all public access blocked, its policy (HTTPS (secure HTTP) only, read only by this distribution), Origin Access Control, security headers policy, CloudFront distribution |
| `github_oidc.tf` | `methyl-flow-github-terraform-plan`, an IAM (Identity and Access Management) role GitHub Actions assumes through OIDC (OpenID Connect) to run `terraform plan` |
| `outputs.tf` | `site_bucket_name`, `distribution_id`, `site_url`; `scripts/publish_site.sh` reads them |
| `versions.tf` | Terraform and AWS (Amazon Web Services) provider pins, S3 (Amazon Simple Storage Service) backend, default tags (`managed-by=terraform`) |
| `tests/site.tftest.hcl` | `terraform test` against a mocked provider: public access blocked, only CloudFront reads the bucket, HTTPS (secure HTTP) only with `index.html`, plan role trusts only this repo |

## State

State lives in `methyl-flow-tfstate-<account ID>` (versioned, encrypted, public access blocked),
key `site/terraform.tfstate`, locked with an S3 (Amazon Simple Storage Service) lockfile. The
bucket was made by hand, since Terraform can't create the bucket that holds its own state:

```bash
S=methyl-flow-tfstate-$(aws sts get-caller-identity --query Account --output text)
aws s3api create-bucket --bucket $S --region us-east-1
aws s3api put-public-access-block --bucket $S --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket $S --versioning-configuration Status=Enabled
```

The bucket name holds the account ID, so it stays out of the repo and goes in at init:

```bash
cd infra/terraform/site
export TF_VAR_state_bucket=methyl-flow-tfstate-$(aws sts get-caller-identity --query Account --output text)
terraform init -backend-config="bucket=$TF_VAR_state_bucket"
terraform test
terraform plan -out=site.tfplan
terraform apply site.tfplan
```

Applies run from a laptop. CI (continuous integration) only plans.

## CI (continuous integration)

`.github/workflows/ci.yml` has two Terraform jobs:

- `terraform`: `fmt -check`, `validate`, and `test`. No AWS (Amazon Web Services) credentials.
- `terraform-plan`: on pull requests from this repo and pushes to `main`, assumes the plan role
  through OIDC (OpenID Connect) and runs `terraform plan -detailed-exitcode` against the live state.
  On `main` a nonzero diff fails the job, which flags drift: a change made in the console, or a
  merge nobody applied.

GitHub mints a short-lived token per job; the role's trust policy accepts it only for
`repo:toddcreasy@5910177/methyl-flow@1419372528:pull_request` and `...:ref:refs/heads/main`. This
repo uses GitHub's immutable subject format, which carries the owner and repo IDs, so a recreated
repo with the same name gets no access.
Fork pull requests get no token, so they skip the plan. The role can read the site bucket's
configuration (not its objects), CloudFront, and its own IAM (Identity and Access Management)
definition, read the state file, and write only the lock file.

Repository secrets (secrets, not variables, so GitHub masks the account ID in public logs):

| Secret | Value |
|---|---|
| `TF_STATE_BUCKET` | the state bucket name |
| `TF_PLAN_ROLE_ARN` | the `github_plan_role_arn` output |

## Migration from CDK (Cloud Development Kit), 2026-11-19

The site used to be `MethylFlowSiteStack` in `infra/aws/`. It moved by import, so the bucket, its
contents, and the distribution's address (`d1m4tbm3vqx6m6.cloudfront.net`) stayed the same:

1. Wrote this config and ran `terraform plan` with `import` blocks for all eight resources while
   CloudFormation still owned them: 8 to import, 0 to destroy, changes limited to tags and names.
2. Set every resource in the CDK (Cloud Development Kit) stack to `RemovalPolicy.RETAIN` and turned
   off `auto_delete_objects`, which removed the Lambda that empties the bucket. Deployed; all 19
   objects survived.
3. Deleted the CloudFormation stack. The retained resources kept serving.
4. `terraform apply` of the saved plan: 8 imported, 2 added (the plan role), 5 changed, 0
   destroyed. A second plan showed no differences.

The `import` blocks are in the commit that did this; the next commit removed them, since they are
no-ops after the first apply and `terraform test` cannot import into a mocked provider.
