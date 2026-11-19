# Runs against a mocked AWS provider: no credentials, no real resources.
#   terraform test

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
  mock_data "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::site-bucket"
    }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn = "arn:aws:cloudfront::123456789012:distribution/EXAMPLE"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/methyl-flow-github-terraform-plan"
    }
  }
}

variables {
  state_bucket = "example-tfstate"
}

run "bucket_blocks_all_public_access" {
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.site.block_public_acls,
      aws_s3_bucket_public_access_block.site.block_public_policy,
      aws_s3_bucket_public_access_block.site.ignore_public_acls,
      aws_s3_bucket_public_access_block.site.restrict_public_buckets,
    ])
    error_message = "The site bucket must block every form of public access."
  }
}

run "only_cloudfront_reads_the_bucket" {
  assert {
    condition = anytrue([
      for s in jsondecode(aws_s3_bucket_policy.site.policy).Statement :
      s.Effect == "Allow" && s.Action == "s3:GetObject"
      && s.Principal == { Service = "cloudfront.amazonaws.com" }
      && s.Condition.StringEquals["AWS:SourceArn"] == aws_cloudfront_distribution.site.arn
    ])
    error_message = "The bucket policy must let this distribution, and only it, read objects."
  }

  assert {
    condition = length([
      for s in jsondecode(aws_s3_bucket_policy.site.policy).Statement : s
      if s.Effect == "Allow" && try(s.Principal.Service, "") != "cloudfront.amazonaws.com"
    ]) == 0
    error_message = "No principal other than CloudFront may be allowed on the bucket."
  }

  assert {
    condition     = toset(aws_cloudfront_distribution.site.origin[*].origin_access_control_id) == toset([aws_cloudfront_origin_access_control.site.id])
    error_message = "The distribution must reach the bucket through the Origin Access Control."
  }
}

run "distribution_is_https_only_with_index" {
  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "Viewers must be redirected to HTTPS."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.default_root_object == "index.html"
    error_message = "The root URL must serve index.html."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.price_class == "PriceClass_100"
    error_message = "The distribution should use the cheapest price class."
  }
}

run "plan_role_trusts_only_this_repo" {
  assert {
    condition = toset(jsondecode(aws_iam_role.github_plan.assume_role_policy).Statement[0].Condition.StringLike["token.actions.githubusercontent.com:sub"]) == toset([
      "repo:toddcreasy@5910177/methyl-flow@1419372528:pull_request",
      "repo:toddcreasy@5910177/methyl-flow@1419372528:ref:refs/heads/main",
    ])
    error_message = "Only this repo's pull requests and main branch may assume the plan role."
  }
}
