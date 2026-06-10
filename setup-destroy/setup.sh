#!/usr/bin/env bash
set -euo pipefail

echo "Building images with per-service contexts..."
# admin, matching, orders build from their service directories (their Dockerfiles expect service-local files at context root)
docker build -t delivery-system/admin:latest -f admin/Dockerfile admin
docker build -t delivery-system/matching:latest -f matching/Dockerfile matching
docker build -t delivery-system/orders:latest -f orders/Dockerfile orders

# services that rely on the monorepo `shared` package use repo root as context
docker build -t delivery-system/clients:latest -f clients/Dockerfile .
docker build -t delivery-system/couriers:latest -f couriers/Dockerfile .
docker build -t delivery-system/restaurants:latest -f restaurants/Dockerfile .
docker build -t delivery-system/region:latest -f region/Dockerfile .

echo "Starting compose services..."
docker compose up -d

echo "Creating SQS queue in LocalStack..."
docker exec -it localstack awslocal sqs create-queue --queue-name courier-locations || true

echo "Configuring kubectl context and installing ingress..."
kubectl config use-context docker-desktop

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

echo "Waiting for ingress controller to be ready..."
kubectl wait \
  --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=300s

echo "Applying namespaces and config..."
kubectl apply -f infra/k8s/admin/namespace.yaml
kubectl apply -f infra/k8s/city/namespace-template.yaml

kubectl apply -f infra/k8s/config/local/admin-configmap.yaml
kubectl apply -f infra/k8s/config/local/admin-secret.yaml
kubectl apply -f infra/k8s/config/local/city-configmap.yaml
kubectl apply -f infra/k8s/config/local/city-secret.yaml

echo "Applying service deployments..."
kubectl apply -f infra/k8s/admin/admin.yaml
kubectl apply -f infra/k8s/city/clients.yaml
kubectl apply -f infra/k8s/city/couriers.yaml
kubectl apply -f infra/k8s/city/matching.yaml
kubectl apply -f infra/k8s/city/orders.yaml
kubectl apply -f infra/k8s/city/restaurants.yaml

kubectl apply -f infra/k8s/admin/service-local.yaml
kubectl apply -f infra/k8s/city/service-local.yaml

echo "Ambiente local configurado com sucesso!"
