terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

resource "docker_network" "dijkfood" {
  name = "dijkfood"
}

# LocalStack
resource "docker_image" "localstack" {
  name = "localstack/localstack:latest"
}

resource "docker_container" "localstack" {
  name  = "localstack"
  image = docker_image.localstack.image_id

  env = [
    "SERVICES=sqs,dynamodb,s3",
    "DEFAULT_REGION=us-east-1",
    "EAGER_SERVICE_LOADING=1",
  ]

  ports {
    internal = 4566
    external = 4566
  }

  networks_advanced {
    name = docker_network.dijkfood.name
  }

  healthcheck {
    test         = ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
    interval     = "5s"
    timeout      = "3s"
    retries      = 10
  }
}

# Postgres
resource "docker_image" "postgres" {
  name = "postgres:16"
}

resource "docker_container" "postgres" {
  name  = "postgres"
  image = docker_image.postgres.image_id

  env = [
    "POSTGRES_USER=postgres",
    "POSTGRES_PASSWORD=postgres",
    "POSTGRES_DB=dijkfood",
  ]

  ports {
    internal = 5432
    external = 5432
  }

  volumes {
    volume_name    = docker_volume.postgres_data.name
    container_path = "/var/lib/postgresql/data"
  }

  networks_advanced {
    name = docker_network.dijkfood.name
  }
}

resource "docker_volume" "postgres_data" {
  name = "postgres_data"
}

# DynamoDB Admin (UI local)
resource "docker_image" "dynamodb_admin" {
  name = "aaronshaf/dynamodb-admin:latest"
}

resource "docker_container" "dynamodb_admin" {
  name  = "dynamodb_admin"
  image = docker_image.dynamodb_admin.image_id

  env = [
    "DYNAMO_ENDPOINT=http://localstack:4566",
    "AWS_ACCESS_KEY_ID=test",
    "AWS_SECRET_ACCESS_KEY=test",
    "AWS_REGION=us-east-1",
  ]

  ports {
    internal = 8001
    external = 8002
  }

  networks_advanced {
    name = docker_network.dijkfood.name
  }

  depends_on = [docker_container.localstack]
}

# Serviços da aplicação
locals {
  services = {
    admin       = { port = 4000, context = "../../admin" }
    clients     = { port = 4001, context = "../../clients" }
    couriers    = { port = 4002, context = "../../couriers" }
    matching    = { port = 4003, context = "../../matching" }
    orders      = { port = 4004, context = "../../orders" }
    restaurants = { port = 4005, context = "../../restaurants" }
  }
}

resource "docker_image" "services" {
  for_each = local.services
  name     = "dijkfood-${each.key}:local"

  build {
    context = each.value.context
  }
}

resource "docker_container" "services" {
  for_each = local.services
  name     = each.key
  image    = docker_image.services[each.key].image_id

  env = [
    "PORT=${each.value.port}",
    "DB_HOST=postgres",
    "DB_PORT=5432",
    "DB_USER=postgres",
    "DB_PASSWORD=postgres",
    "DB_NAME=dijkfood",
  ]

  ports {
    internal = each.value.port
    external = each.value.port
  }

  networks_advanced {
    name = docker_network.dijkfood.name
  }

  depends_on = [docker_container.postgres]
}

# Positions consumer
resource "docker_image" "positions" {
  name = "dijkfood-positions:local"
  build {
    context = "../../positions"
  }
}

resource "docker_container" "positions" {
  name  = "positions"
  image = docker_image.positions.image_id

  env = [
    "SQS_ENDPOINT=http://localstack:4566",
    "SQS_QUEUE_URL=http://localstack:4566/000000000000/courier-locations",
    "DYNAMODB_ENDPOINT=http://localstack:4566",
    "AWS_ACCESS_KEY_ID=test",
    "AWS_SECRET_ACCESS_KEY=test",
    "AWS_DEFAULT_REGION=us-east-1",
  ]

  networks_advanced {
    name = docker_network.dijkfood.name
  }

  depends_on = [docker_container.localstack]
}