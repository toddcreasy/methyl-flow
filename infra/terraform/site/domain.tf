# Custom domain for the results site. The Route 53 zone is delegated from the parent domain and
# managed in project-template's ops/dns, so it is looked up here, never created.

variable "domain_name" {
  description = "Public name of the results site; also the name of its Route 53 zone."
  type        = string
  default     = "methyl-flow.pilotbio.io"
}

data "aws_route53_zone" "site" {
  name = var.domain_name
}

# CloudFront reads certificates only from us-east-1, which is this provider's region
resource "aws_acm_certificate" "site" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# One name, so one validation record
resource "aws_route53_record" "cert_validation" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = one(aws_acm_certificate.site.domain_validation_options).resource_record_name
  type    = one(aws_acm_certificate.site.domain_validation_options).resource_record_type
  records = [one(aws_acm_certificate.site.domain_validation_options).resource_record_value]
  ttl     = 300
}

resource "aws_acm_certificate_validation" "site" {
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [aws_route53_record.cert_validation.fqdn]
}

resource "aws_route53_record" "site" {
  for_each = toset(["A", "AAAA"])
  zone_id  = data.aws_route53_zone.site.zone_id
  name     = var.domain_name
  type     = each.key

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
