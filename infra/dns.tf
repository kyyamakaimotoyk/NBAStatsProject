# =============================================================================
# DNS + TLS certificate (Week 3.2)
# =============================================================================
# The domain is registered out-of-band in the Route 53 console. Registration
# auto-creates the public hosted zone, so we DON'T manage the registration or the
# zone in Terraform — we look the zone up with a data source and manage the
# records + the ACM cert here.
#
# IMPORTANT: this cert lives in us-east-1 (our provider's region). That's
# mandatory for CloudFront (it only accepts certs from us-east-1), and an ALB in
# us-east-1 can use the very same cert — so one cert serves both tiers.
# =============================================================================

variable "domain_name" {
  type        = string
  default     = "hoopmodel.com"
  description = "Registered domain (Route 53)"
}

# Look up the hosted zone that registration created. (Plan will error with
# "no matching Route 53 Zone found" until the domain finishes registering — that's
# expected; apply this file only after the zone exists.)
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# DNS-validated cert covering the apex + ANY subdomain via wildcard.
#   domain_name = hoopmodel.com          -> the apex (CloudFront/static site)
#   SAN         = *.hoopmodel.com         -> www, api, anything else (one cert)
# A wildcard does NOT cover the apex, which is why the apex is the domain_name and
# the wildcard is the SAN — together they cover both.
resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project}-cert"
  }
}

# ACM emits one validation CNAME per distinct name on the cert. We write each into
# the hosted zone; ACM then sees them and flips the cert to "issued".
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id         = data.aws_route53_zone.main.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

# Gate that blocks dependents (ALB listener, CloudFront) until validation lands.
# It creates no real resource — it just waits for ACM to report "issued".
resource "aws_acm_certificate_validation" "main" {
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
