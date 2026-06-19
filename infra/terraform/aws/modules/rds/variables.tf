variable "db_username" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "db_instances" {
  type    = list(string)
  default = ["admin", "city-1", "city-2"]
}
