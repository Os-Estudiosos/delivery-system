terraform {
  required_providers {
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.14"
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

resource "kubectl_manifest" "admin_namespace" {
  yaml_body = file("${var.k8s_path}/admin/namespace.yaml")
}

resource "kubectl_manifest" "admin" {
  yaml_body  = file("${var.k8s_path}/admin/admin.yaml")
  depends_on = [kubectl_manifest.admin_namespace]
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

  depends_on = [kubectl_manifest.city_namespaces]
}