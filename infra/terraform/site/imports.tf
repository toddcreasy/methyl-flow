# Adopts the resources CloudFormation created for the CDK MethylFlowSiteStack. They were set to
# retain before that stack was destroyed, so they kept running and the distribution kept its URL.
# After the first apply these blocks are no-ops.

import {
  to = aws_s3_bucket.site
  id = "methylflowsitestack-sitebucket397a1860-bqrtx87vedwq"
}

import {
  to = aws_s3_bucket_public_access_block.site
  id = "methylflowsitestack-sitebucket397a1860-bqrtx87vedwq"
}

import {
  to = aws_s3_bucket_ownership_controls.site
  id = "methylflowsitestack-sitebucket397a1860-bqrtx87vedwq"
}

import {
  to = aws_s3_bucket_server_side_encryption_configuration.site
  id = "methylflowsitestack-sitebucket397a1860-bqrtx87vedwq"
}

import {
  to = aws_s3_bucket_policy.site
  id = "methylflowsitestack-sitebucket397a1860-bqrtx87vedwq"
}

import {
  to = aws_cloudfront_origin_access_control.site
  id = "E2KU6VECNJ9INT"
}

import {
  to = aws_cloudfront_response_headers_policy.security
  id = "6e0fa011-a57e-497d-ac6b-ffab652f808f"
}

import {
  to = aws_cloudfront_distribution.site
  id = "EOC3OL7SQKXWQ"
}
