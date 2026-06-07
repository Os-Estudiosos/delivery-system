variable "data_lake_bucket" {
  type        = string
  description = "Nome do bucket S3 do data lake (ex: dijkfood-data-lake)"
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
