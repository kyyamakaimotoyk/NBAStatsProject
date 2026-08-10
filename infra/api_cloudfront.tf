# =============================================================================
# CloudFront in front of the API (Week 3.3, reworked) — the public front line
# =============================================================================
# CloudFront is what the internet talks to (api.hoopmodel.com). It gives us:
#   - DDoS edge absorption (AWS Shield Standard, free) across ~600 edges,
#   - origin hiding (the ALB only accepts CloudFront's IPs; see api_alb.tf SG),
#   - a place to bolt on AWS WAF / rate-limiting later (web_acl_id).
# It is ALSO the edge cache for every public read path (short 5-min TTL via the
# api_perf policy below — the data only changes when the ingest/prediction jobs
# run, a few times a day). Only /api/health (monitoring must see the live
# process) and /api/advisor (personalized POST) stay uncached, via the managed
# CachingDisabled policy on the default behavior.
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
#  - CachingDisabled: never cache (the default behavior: health + advisor).
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
  enabled = true
  comment = "${var.project} API — shields the ALB"
  # PriceClass_200 is the cheapest class that includes Tokyo/Osaka edges.
  # PriceClass_100 (US/CA/EU only) forced Japanese readers of this bilingual
  # site onto US edges: ~0.25s TLS + ~0.65s edge HITs measured from Tokyo,
  # vs ~0.03s once served locally. Below CloudFront's always-free tier
  # (1 TB + 10M req/mo) the class change costs nothing.
  price_class = "PriceClass_200"
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

  # Every public read path gets the ~5-min edge cache: the underlying data only
  # changes when the scheduled ingest/prediction jobs write (a few times a day),
  # so RDS-per-visit bought freshness nothing needs. The cache key includes the
  # Origin header (correct CORS per origin) and all query strings (each
  # window/feature/date/model variant caches separately).
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

  ordered_cache_behavior {
    path_pattern             = "/api/explore/*"
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.api_perf.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  # /api/predictions and /api/predictions/latest (no trailing slash on the
  # first, so the pattern has no / before the wildcard).
  ordered_cache_behavior {
    path_pattern             = "/api/predictions*"
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.api_perf.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  ordered_cache_behavior {
    path_pattern             = "/api/accuracy/*"
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.api_perf.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  ordered_cache_behavior {
    path_pattern             = "/api/players/*"
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.api_perf.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  # The advisor is the ONLY path that accepts POST (CloudFront only offers the
  # all-methods set once any write verb is needed). Never cached; the ALB
  # listener rule routes it to the separate Bedrock-capable service.
  ordered_cache_behavior {
    path_pattern             = "/api/advisor*"
    target_origin_id         = "alb-api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
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


# Short-TTL cache policy shared by every cached /api/* behavior — keeps the
# batch-produced data fresh-enough (~5 min) while collapsing repeat reads off
# RDS. The API now also sends Cache-Control (max-age=60, s-maxage=300), and
# CloudFront prefers s-maxage over these TTLs when present — so the effective
# edge TTL stays ~5 min either way; default_ttl is the no-header fallback.
resource "aws_cloudfront_cache_policy" "api_perf" {
  name        = "${var.project}-api-perf"
  comment     = "Short-TTL cache for public /api/* read paths (batch-produced data)"
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
      # Key on all query strings so every distinct request (days/model for
      # performance, feature/window/days for explore) caches separately.
      query_string_behavior = "all"
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
