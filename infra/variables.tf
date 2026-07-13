#  providers.tf is going to reference a variable — the region — instead of hardcoding "us-east-1". But Terraform only lets you use var.aws_region if that variable is declared somewhere
#  first, or validate errors with "undeclared variable." Good habit: declare your inputs, then use them.
variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region used for all resources"
}

variable "project" {
  type        = string
  default     = "nba-game-predictor"
  description = "Short description; used as a prefix and tag on resources"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16" # Classless Inter-Domain Routing (CIDR) represent IP Addresses along with number of bits reserved for the network portion
  # /16 means the first 16 bits (first 2 octets) are reserved for network ID - we are subnetting
  # CIDR 10.0.0.0/16 means 10.0 is reserved, last two octets can go from 0-2^8
  # subnet 1 could be 10.0.1.0/24 (2^8 'free' IP'
  # subnet 2 could be 10.0.2.0/24
  description = "IP range for the VPC"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
  description = "CIDRs for the public subnets (one per AZ)"
}

variable "private_subnet_cidrs" {
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
  description = "CIDRs for private subnets (one per AZ)"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t4g.micro"
  description = "RDS instance size"
}

variable "db_name" {
  type        = string
  default     = "nba_data"
  description = "Initial schema name"
}

variable "db_username" {
  type        = string
  default     = "nbaadmin"
  description = "RDS master username"
}
variable "turnstile_secret_arn" {
  type        = string
  default     = ""
  description = "Secrets Manager ARN holding the Cloudflare Turnstile secret key. Empty disables Turnstile verification on the advisor. Create the secret manually (never inline the key)."
}
