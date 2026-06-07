# ── Gerais ────────────────────────────────────────────────────
variable "aws_region" {
  default = "us-east-1"
}

variable "aws_access_key_id" {
  default = ""
}

variable "aws_secret_access_key" {
  default   = ""
  sensitive = true
}

variable "aws_session_token" {
  default   = ""
  sensitive = true
}

# ── RDS ───────────────────────────────────────────────────────
variable "db_username" {
  default = "dijkfood"
}

variable "db_password" {
  sensitive = true
}

# ── EKS ───────────────────────────────────────────────────────
variable "eks_cluster_name" {
  default = "dijkfood"
}

variable "eks_cluster_role_arn" {
  default = "arn:aws:iam::043830376165:role/c213967a5408241l15083359t1w043830-LabEksClusterRole-UZqtrw4Ps35H"
}

variable "eks_node_role_arn" {
  default = "arn:aws:iam::043830376165:role/c213967a5408241l15083359t1w043830376-LabEksNodeRole-2x8ymceYyHcW"
}

variable "eks_attach_ecr_readonly" {
  type    = bool
  default = false
}

# ── ECR ───────────────────────────────────────────────────────
variable "ecr_repo_prefix" {
  default = "delivery-system"
}

variable "ecr_repositories" {
  type    = list(string)
  default = ["admin", "clients", "couriers", "matching", "orders", "restaurants"]
}

variable "ecr_force_delete" {
  type    = bool
  default = false
}

variable "ecr_scan_on_push" {
  type    = bool
  default = true
}

# ── Glue ──────────────────────────────────────────────────────
variable "glue_role_arn" {
  type        = string
  description = "ARN do IAM Role com permissões: AWSGlueServiceRole + S3 + RDS + CloudWatch"
  # Em ambientes de lab, use o LabRole existente:
  # arn:aws:iam::<account_id>:role/LabRole
  default = ""
}

variable "glue_schedule" {
  type        = string
  description = "Cron para execução do ETL (UTC). Default: 3h diário"
  default     = "cron(0 3 * * ? *)"
}

variable "glue_db_name" {
  type    = string
  default = "dijkfood_analytics"
}

# ── Athena ────────────────────────────────────────────────────
variable "athena_workgroup_name" {
  type    = string
  default = "dijkfood-analytics"
}

variable "athena_bytes_scanned_limit" {
  type        = number
  description = "Limite de bytes por query no Athena (proteção de custo). Default: 1 GB"
  default     = 1073741824
}

# ── EC2 ───────────────────────────────────────────────────────────────────────
variable "ec2_instance_profile" {
  type        = string
  description = "IAM Instance Profile com permissões Athena + S3 (disponível no AWS Academy)"
  default     = "LabInstanceProfile"
}
