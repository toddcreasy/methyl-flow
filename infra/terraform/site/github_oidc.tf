# Read-only role GitHub Actions assumes through OIDC to run `terraform plan`. No stored AWS keys:
# GitHub issues a short-lived token per job, and the trust policy accepts it only from this repo's
# pull requests and main branch. Applies still run from a laptop.

locals {
  github_repo = "toddcreasy/methyl-flow"
  state_key   = "site/terraform.tfstate"
}

variable "state_bucket" {
  description = "Name of the S3 bucket that holds this config's state (same value as -backend-config bucket)."
  type        = string
}

data "aws_caller_identity" "current" {}

# Created once per account; another project already owns it
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_plan" {
  name        = "methyl-flow-github-terraform-plan"
  description = "GitHub Actions runs terraform plan for infra/terraform/site"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "repo:${local.github_repo}:pull_request",
            "repo:${local.github_repo}:ref:refs/heads/main",
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_plan" {
  name = "terraform-plan-read-only"
  role = aws_iam_role.github_plan.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadSiteBucketConfig"
        Effect   = "Allow"
        Action   = ["s3:GetBucket*", "s3:GetEncryptionConfiguration", "s3:GetLifecycleConfiguration", "s3:GetReplicationConfiguration", "s3:GetAccelerateConfiguration", "s3:ListBucket"]
        Resource = aws_s3_bucket.site.arn
      },
      {
        Sid      = "ReadCloudFront"
        Effect   = "Allow"
        Action   = ["cloudfront:Get*", "cloudfront:List*"]
        Resource = "*"
      },
      {
        Sid    = "ReadOwnIamConfig"
        Effect = "Allow"
        Action = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:GetOpenIDConnectProvider"]
        Resource = [
          aws_iam_role.github_plan.arn,
          data.aws_iam_openid_connect_provider.github.arn,
        ]
      },
      {
        Sid      = "ListState"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = "arn:aws:s3:::${var.state_bucket}"
      },
      {
        Sid      = "ReadState"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${var.state_bucket}/${local.state_key}"
      },
      {
        # Plan takes the state lock, a small object beside the state file
        Sid      = "HoldStateLock"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::${var.state_bucket}/${local.state_key}.tflock"
      },
    ]
  })
}

output "github_plan_role_arn" {
  description = "Set as the TF_PLAN_ROLE_ARN repository variable."
  value       = aws_iam_role.github_plan.arn
}
