# =============================================================================
# Frontend: private S3 bucket + CloudFront (Week 3.5)
# =============================================================================
# The Next.js static export (web/out/) is uploaded to a PRIVATE S3 bucket. The
# public never touches S3 directly:
#   viewer ──HTTPS──> CloudFront ──(OAC, signed)──> private S3 bucket
# Origin Access Control (OAC) is the modern replacement for the old "public S3
# website" pattern — the bucket stays locked down and only this distribution can
# read it. A small CloudFront Function rewrites /accuracy/ -> /accuracy/index.html
# so the per-route HTML files from the static export resolve.
# =============================================================================


# -----------------------------------------------------------------------------
# S3 bucket — private storage for the built site
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "site" {
  bucket = "${var.project}-site-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


# -----------------------------------------------------------------------------
# Origin Access Control — lets CloudFront sign its requests to the private bucket
# -----------------------------------------------------------------------------
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.project}-site-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}


# -----------------------------------------------------------------------------
# CloudFront Function — directory-index rewrite for the static export
# -----------------------------------------------------------------------------
# S3 has no notion of "index.html for a folder". This viewer-request function
# turns "/" into "/index.html" and "/accuracy/" (or "/accuracy") into
# "/accuracy/index.html" so the exported HTML files are found.
resource "aws_cloudfront_function" "rewrite" {
  name    = "${var.project}-index-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Append index.html for directory / extensionless paths"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;
      if (uri.endsWith("/")) {
        request.uri = uri + "index.html";
      } else if (!uri.includes(".")) {
        request.uri = uri + "/index.html";
      }
      return request;
    }
  EOT
}


# Managed cache policy tuned for static assets (long TTLs, gzip/br).
data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}


# -----------------------------------------------------------------------------
# The distribution — hoopmodel.com + www
# -----------------------------------------------------------------------------
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${var.project} static site"
  price_class         = "PriceClass_100"
  aliases             = [var.domain_name, "www.${var.domain_name}"]

  origin {
    origin_id                = "s3-site"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.rewrite.arn
    }
  }

  # Serve the exported 404 page for missing paths.
  custom_error_response {
    error_code         = 404
    response_code      = 404
    response_page_path = "/404.html"
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
}


# -----------------------------------------------------------------------------
# Bucket policy — only THIS distribution (via OAC) may read objects
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "site_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site_bucket.json
}


# -----------------------------------------------------------------------------
# DNS — apex + www point at the site distribution
# -----------------------------------------------------------------------------
resource "aws_route53_record" "site_apex" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_www" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
