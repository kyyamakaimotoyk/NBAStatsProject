# =============================================================================
# Inbound email: contact@hoopmodel.com -> personal inbox via ImprovMX (free tier)
# =============================================================================
# The site's /contact page publishes contact@hoopmodel.com (required-ish for
# AdSense review — see docs/ad_monetization_plan.md). There is no mail server:
# ImprovMX receives mail for the domain and forwards it. Confirm the values
# below against the ImprovMX dashboard after adding the domain there; these
# are its documented defaults.
#
# Route 53 allows ONE record set per (name, type). Every apex TXT value —
# SPF now, Google Search Console verification / DMARC-style tokens later —
# must live in apex_txt_values below, not in a second TXT resource.

variable "apex_txt_values" {
  type        = list(string)
  description = "All TXT values for the zone apex (SPF + any verification tokens)"
  default = [
    # SPF: authorises ImprovMX to send (forward) mail on the domain's behalf.
    "v=spf1 include:spf.improvmx.com ~all",
    # Add e.g. "google-site-verification=..." here when verifying Search Console.
  ]
}

resource "aws_route53_record" "apex_mx" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "MX"
  ttl     = 3600
  records = [
    "10 mx1.improvmx.com",
    "20 mx2.improvmx.com",
  ]
}

resource "aws_route53_record" "apex_txt" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "TXT"
  ttl     = 3600
  records = var.apex_txt_values
}
