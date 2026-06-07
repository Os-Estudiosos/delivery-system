output "db_endpoint" {
  value       = aws_db_instance.dijkfood.endpoint
  description = "Endpoint do RDS (host:port) — usado na JDBC URL do Glue"
}

output "db_name" {
  value = aws_db_instance.dijkfood.db_name
}
