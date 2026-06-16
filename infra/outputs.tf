# Think of your whole infra/ config like a function:
#  - variables.tf = the function's parameters (inputs you pass in: region, project name, CIDRs).
#  - The resource blocks = the function body (what it does: create VPC, RDS, etc.).
#  - outputs.tf = the function's return values (the results it hands back).
#
#  You already built the "inputs" side (variables). Outputs are the symmetric "results" side. A config without outputs is like a function that does work but
#  returns nothing — it ran, but it doesn't hand you back the useful values it computed.
#
#  What outputs technically do
#
#  When Terraform creates a resource, AWS computes a bunch of attributes at creation time that you couldn't know in advance — the RDS endpoint hostname, the
#  auto-generated secret's ARN, the ECR repository URL. These live inside Terraform's state file. Outputs are the declared, official way to surface specific
#  values from inside that state to the outside world, where you (or scripts) can read them with terraform output.
#
#  Without an output, the value still exists in state — but to get it you'd have to dig it out of the console or construct an AWS CLI query. Outputs pull the
#  handful that matter up to the surface, named clearly.
#
#  "Couldn't I just use the console or aws CLI?"
#
#  Yes — and this is the honest part: outputs are not strictly required. You could run aws rds describe-db-instances --query '...' to get the endpoint. But
#  outputs earn their place for four reasons:
#
#  1. Discoverability / one source of truth. terraform output gives you exactly the values that matter, with friendly names (rds_endpoint), instead of hunting
#  through console pages or memorizing CLI query syntax.
#  2. A stable interface. You reference terraform output rds_endpoint without needing to know it's internally aws_db_instance.main.address. If you later rename
#  or restructure resources, the output name stays the same — callers don't break.
#  3. Machine-readable for automation. terraform output -raw rds_endpoint or -json lets scripts and CI consume the values. In Week 4, your deploy pipeline will
#  pull the ECR URL and RDS endpoint programmatically this way instead of you pasting them.
#  4. Wiring configs together. If you split infra into modules or use remote state, one config's outputs become another config's inputs. That's the standard
#  way Terraform passes values between layers.
#
# Rather than dig each one out of the console three separate times, we declare them once and read them all with a single terraform output.
#
#  And to be clear about cost/risk
#
#  Outputs create nothing and cost nothing. The apply that "adds" them changes zero real resources — it just records the values into state and prints them.
#  (And the secret ARN is only a pointer/address to where the password lives — not the password itself — so it's safe to display.)


output "rds_endpoint" {
  description = "RDS hostname (becomes NBA_DB_HOST in the cloud)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  value = aws_db_instance.main.port
}

# Terraform / AWS CLI / Console Equivalent
#Terraform: terraform output rds_endpoint
#
#  AWS CLI:
#  # endpoint hostname
#  aws rds describe-db-instances --db-instance-identifier nba-game-predictor-db --query "DBInstances[0].Endpoint.Address" --output text
#  # port
#  aws rds describe-db-instances --db-instance-identifier nba-game-predictor-db --query "DBInstances[0].Endpoint.Port" --output text
#  # both at once (as JSON)
#  aws rds describe-db-instances --db-instance-identifier nba-game-predictor-db --query "DBInstances[0].Endpoint"
#
#  Console: RDS → Databases → click nba-game-predictor-db → Connectivity & security tab → "Endpoint" and "Port" are right at the top.


output "rds_master_secret_arn" {
  description = "Secrets Manager ARN holding the RDS-managed master password"
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

# Terraform: terraform output rds_master_secret_arn
#
#  AWS CLI:
#  aws rds describe-db-instances --db-instance-identifier nba-game-predictor-db --query "DBInstances[0].MasterUserSecret.SecretArn" --output text
#
#  Console: RDS → Databases → nba-game-predictor-db → Configuration tab → under "Master credentials..." there's a link to the secret in Secrets Manager. Or go
#  straight to Secrets Manager → Secrets and find the one named rds!db-....
#
#  Bonus (you'll use this in 2.4): the ARN is just a pointer. To fetch the actual username/password it holds:
#  aws secretsmanager get-secret-value --secret-id <the-arn> --query "SecretString" --output text
#  That returns JSON like {"username":"nbaadmin","password":"...."}. (Don't paste the result here — it's the real password. In the console it's Secrets Manager
#  → the secret → "Retrieve secret value".)

output "models_bucket" {
  value = aws_s3_bucket.models.bucket
}

#  Terraform: terraform output models_bucket
#
#  AWS CLI:
#  # all your buckets
#  aws s3 ls
#  # just this one (filtered)
#  aws s3api list-buckets --query "Buckets[?contains(Name, 'nba-game-predictor-models')].Name" --output text
#
#  Console: S3 → Buckets (S3 is global, so no region filter needed here) → nba-game-predictor-models-583686634997.

output "ecr_api_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_pipeline_url" {
  value = aws_ecr_repository.pipeline.repository_url
}

# --- ECS / Fargate (Week 2.5): the values `aws ecs run-task` needs ---
output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "pipeline_task_family" {
  description = "Task-definition family; run-task picks the latest active revision"
  value       = aws_ecs_task_definition.pipeline.family
}

output "app_security_group_id" {
  value = aws_security_group.app.id
}

output "public_subnet_ids" {
  description = "Run the Fargate task in one of these (needs a public IP; no NAT)"
  value       = aws_subnet.public[*].id
}

# --- DNS / TLS (Week 3.2) ---
output "acm_certificate_arn" {
  description = "Validated cert ARN; used by the ALB listener (3.3) and CloudFront (3.5)"
  value       = aws_acm_certificate_validation.main.certificate_arn
}

output "route53_zone_id" {
  value = data.aws_route53_zone.main.zone_id
}

# --- API load balancer (Week 3.3) ---
output "alb_dns_name" {
  description = "ALB's AWS hostname (api.hoopmodel.com aliases to this)"
  value       = aws_lb.main.dns_name
}

output "api_url" {
  description = "Public HTTPS base URL for the API once DNS propagates"
  value       = "https://api.${var.domain_name}"
}

output "api_cloudfront_domain" {
  description = "CloudFront distribution domain fronting the API (api.hoopmodel.com aliases here)"
  value       = aws_cloudfront_distribution.api.domain_name
}

# --- Static site (Week 3.5) ---
output "site_bucket" {
  description = "S3 bucket holding the built site; aws s3 sync web/out here"
  value       = aws_s3_bucket.site.bucket
}

output "site_cloudfront_id" {
  description = "Site distribution id; used for cache invalidations after a deploy"
  value       = aws_cloudfront_distribution.site.id
}

output "site_url" {
  value = "https://${var.domain_name}"
}

# --- CI/CD (Week 3.6) ---
output "github_deploy_role_arn" {
  description = "Role GitHub Actions assumes via OIDC (set as repo variable AWS_ROLE_ARN)"
  value       = aws_iam_role.github_deploy.arn
}

# Terraform: terraform output ecr_api_url (and ecr_pipeline_url)
#
#  AWS CLI:
#  # one repo's push URL
#  aws ecr describe-repositories --repository-names nba-game-predictor-api --query "repositories[0].repositoryUri" --output text
#  # both at once
#  aws ecr describe-repositories --query "repositories[].repositoryUri" --output text
#
#  Console: ECR → Repositories → the repositoryUri shows in the list; click a repo → View push commands for the exact docker push sequence (we'll use that in
#  2.5).

