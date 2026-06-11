variable "datalake_bucket_name" {
  type = string
}

variable "datalake_bucket_arn" {
  type = string
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
