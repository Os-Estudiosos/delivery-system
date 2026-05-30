terraform {
  required_providers {
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.14"
    }

    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

locals {
  city_services = ["clients", "couriers", "matching", "orders", "restaurants"]

  city_manifests = {
    for pair in setproduct(var.cities, local.city_services) :
    "${pair[0]}-${pair[1]}" => {
      city    = pair[0]
      service = pair[1]
    }
  }
}

# Serviços da aplicação
locals {
  services = {
    admin       = { port = 4000, context = "../../../admin" }
    clients     = { port = 4001, context = "../../../clients" }
    couriers    = { port = 4002, context = "../../../couriers" }
    matching    = { port = 4003, context = "../../../matching" }
    orders      = { port = 4004, context = "../../../orders" }
    restaurants = { port = 4005, context = "../../../restaurants" }
  }
}

resource "docker_image" "services" {
  for_each = local.services
  name     = "delivery-system/${each.key}:latest"

  build {
    context = each.value.context
  }
}

resource "kubectl_manifest" "admin_namespace" {
  yaml_body = file("${var.k8s_path}/admin/namespace.yaml")
}

resource "kubectl_manifest" "admin" {
  yaml_body  = file("${var.k8s_path}/admin/admin.yaml")
  depends_on = [
    kubectl_manifest.admin_namespace,
    docker_image.services
  ]
}

resource "kubectl_manifest" "city_namespaces" {
  for_each = toset(var.cities)

  yaml_body = replace(
    file("${var.k8s_path}/city/namespace-template.yaml"),
    "city-example-namespace",
    "city-${each.value}-namespace"
  )
}

resource "kubectl_manifest" "city_manifests" {
  for_each = local.city_manifests

  yaml_body = replace(
    file("${var.k8s_path}/city/${each.value.service}.yaml"),
    "city-example-namespace",
    "city-${each.value.city}-namespace"
  )

  depends_on = [
    kubectl_manifest.city_namespaces,
    docker_image.services
  ]
}