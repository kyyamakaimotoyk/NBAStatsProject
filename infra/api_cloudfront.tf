# =============================================================================
# CloudFront in front of the API (Week 3.3, reworked) — the public front line
# =============================================================================
# CloudFront is what the internet talks to (api.hoopmodel.com). It gives us:
#   - DDoS edge absorption (AWS Shield Standard, free) across ~600 edges,
#   - origin hiding (the ALB only accepts CloudFront's IPs; see api_alb.tf SG),
#   - a place to bolt on AWS WAF / rate-limiting later (web_acl_id).
# It is NOT used as a cache here: the API is dynamic (RDS-fresh per request), so
# we attach the managed CachingDisabled policy and forward everything to origin.
#
# HTTPS end-to-end. The trick for the CloudFront->ALB leg: CloudFront connects to
# the ALB using the name `api-origin.hoopmodel.com`, which the wildcard cert
# (*.hoopmodel.com) covers — so the origin TLS handshake validates cleanly.
# =============================================================================


# AWS-managed prefix list of CloudFront's origin-facing IP ranges (referenced by
# the ALB security group in api_alb.tf to lock the ALB to CloudFront only).
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# Managed policies (stable, AWS-provided):
#  - CachingDisabled: never cache (dynamic API; no stale predictions).
#  - AllViewer: forward all viewer headers/cookies/query strings to the origin
#    (so ?date=, ?days=, ?model=, and the CORS Origin header reach FastAPI).
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}


# api-origin.hoopmodel.com -> the ALB (CloudFront's origin name; wildcard-cert covered)
resource "aws_route53_record" "api_origin" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api-origin.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}


resource "aws_cloudfront_distribution" "api" {
  enabled     = true
  comment     = "${var.project} API — shields the ALB"
  price_class = "PriceClass_100" # US/Canada/Europe edges only (cheapest)
  aliases     = ["api.${var.domain_name}"]

  origin {
    origin_id   = "alb-api"
    domain_name = aws_route53_record.api_origin.fqdn

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only" # CloudFront -> ALB is HTTPS
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https" # viewers forced onto HTTPS
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  # Model-performance data only changes nightly, so cache it (~5 min) at the edge
  # instead of hitting RDS on every visit. The cache key includes the Origin header
  # (correct CORS per origin) and the days/model query strings (windows cache apart).
  ordered_cache_behavior {
    path_pattern             = "/api/performance/*"
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.api_perf.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.main.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # To add a WAF later: set web_acl_id = aws_wafv2_web_acl.<name>.arn
}


# Short-TTL cache policy for /api/performance/* — keeps the nightly-changing model
# data fresh-enough (~5 min) while collapsing repeat reads off RDS.
resource "aws_cloudfront_cache_policy" "api_perf" {
  name        = "${var.project}-api-perf"
  comment     = "Short-TTL cache for /api/performance/* (data changes nightly)"
  default_ttl = 300
  min_ttl     = 0
  max_ttl     = 3600

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "whitelist"
      headers {
        items = ["Origin"] # cache per-origin so the CORS allow-origin header is correct
      }
    }
    query_strings_config {
      query_string_behavior = "whitelist"
      query_strings {
        items = ["days", "model"]
      }
    }
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
  }
}


# api.hoopmodel.com -> CloudFront (the public name visitors and the frontend call)
resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.api.domain_name
    zone_id                = aws_cloudfront_distribution.api.hosted_zone_id
    evaluate_target_health = false
  }
}
