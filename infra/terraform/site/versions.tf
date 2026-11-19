terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
  }

  # Partial config: the bucket name holds the account ID, so it comes from
  # `terraform init -backend-config="bucket=..."` (TF_STATE_BUCKET in CI) and stays out of the repo.
  backend "s3" {
    key          = "site/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      project    = "methyl-flow"
      env        = "dev"
      managed-by = "terraform"
    }
  }
}
