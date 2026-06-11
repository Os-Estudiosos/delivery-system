#!/usr/bin/env bash
set -euo pipefail

echo "Deletando deployments..."
kubectl delete -f infra/k8s/admin/admin.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/clients.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/couriers.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/matching.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/orders.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/restaurants.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/region.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/admin/service-local.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/service-local.yaml --ignore-not-found=true

echo "Deletando ConfigMaps e Secrets..."
kubectl delete -f infra/k8s/config/local/admin-configmap.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/config/local/admin-secret.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/config/local/city-configmap.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/config/local/city-secret.yaml --ignore-not-found=true

echo "Deletando namespaces..."
kubectl delete -f infra/k8s/admin/namespace.yaml --ignore-not-found=true
kubectl delete -f infra/k8s/city/namespace-template.yaml --ignore-not-found=true

# Also delete any dynamically created namespaces by the admin service
kubectl get ns -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep '^city-' | xargs -r kubectl delete ns || true

echo "Deletando NGINX Ingress Controller..."
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml --ignore-not-found=true

echo "Parando e limpando infraestrutura local (compose)..."
docker compose down -v

echo "Ambiente local destruído com sucesso!"
