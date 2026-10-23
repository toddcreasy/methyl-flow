import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from stacks.site_stack import SiteStack


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App()
    return Template.from_stack(SiteStack(app, "TestSiteStack"))


def test_bucket_blocks_all_public_access(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
    )


def test_only_cloudfront_reads_the_bucket(template: Template) -> None:
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Action": "s3:GetObject",
                                "Effect": "Allow",
                                "Principal": {"Service": "cloudfront.amazonaws.com"},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_distribution_is_https_only_with_index(template: Template) -> None:
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "DefaultRootObject": "index.html",
                    "PriceClass": "PriceClass_100",
                    "DefaultCacheBehavior": Match.object_like(
                        {"ViewerProtocolPolicy": "redirect-to-https"}
                    ),
                }
            )
        },
    )
