variable "data_lake_bucket" {
  type        = string
  description = "Bucket S3 onde estão os Parquets (mesmo do Glue)"
}

variable "athena_results_bucket" {
  type        = string
  description = "Bucket S3 onde o Athena salva os resultados das queries"
}

variable "glue_db_name" {
  type        = string
  description = "Nome do database no Glue Catalog (usado pelo Athena)"
  default     = "dijkfood_analytics"
}

variable "workgroup_name" {
  type    = string
  default = "dijkfood-analytics"
}

variable "bytes_scanned_limit" {
  type        = number
  description = "Limite de bytes por query (proteção de custo). Default: 1 GB"
  default     = 1073741824
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
