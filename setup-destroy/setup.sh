#!/usr/bin/env bash
set -euo pipefail

echo "Building images with repo root context..."
docker build -t delivery-system/admin:latest -f admin/Dockerfile .
docker build -t delivery-system/matching:latest -f matching/Dockerfile .
docker build -t delivery-system/orders:latest -f orders/Dockerfile .
docker build -t delivery-system/clients:latest -f clients/Dockerfile .
docker build -t delivery-system/couriers:latest -f couriers/Dockerfile .
docker build -t delivery-system/restaurants:latest -f restaurants/Dockerfile .
docker build -t delivery-system/region:latest -f region/Dockerfile .

# Load images into Kind cluster if kind is used
if command -v kind &> /dev/null; then
  echo "Loading images into Kind cluster..."
  kind load docker-image delivery-system/admin:latest --name docker-desktop
  kind load docker-image delivery-system/matching:latest --name docker-desktop
  kind load docker-image delivery-system/orders:latest --name docker-desktop
  kind load docker-image delivery-system/clients:latest --name docker-desktop
  kind load docker-image delivery-system/couriers:latest --name docker-desktop
  kind load docker-image delivery-system/restaurants:latest --name docker-desktop
  kind load docker-image delivery-system/region:latest --name docker-desktop
elif [ -f "./bin/kind" ]; then
  echo "Loading images into Kind cluster using local binary..."
  ./bin/kind load docker-image delivery-system/admin:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/matching:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/orders:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/clients:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/couriers:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/restaurants:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/region:latest --name docker-desktop
fi

echo "Starting compose services..."
docker compose up -d

echo "Creating SQS queue in LocalStack..."
docker exec -it localstack awslocal sqs create-queue --queue-name courier-locations || true

echo "Configuring kubectl context and installing ingress..."
kubectl config use-context docker-desktop

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

echo "Waiting for ingress controller to be ready..."
kubectl wait \
  --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=300s

echo "Applying namespaces and config..."
kubectl apply -f infra/k8s/admin/namespace.yaml
kubectl apply -f infra/k8s/city/namespace-template.yaml

# Discover container IPs dynamically to prevent failures on different hosts/runs
DB_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' database || echo "172.18.0.2")
LOCALSTACK_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' localstack || echo "172.18.0.3")

echo "Using container IPs: DB=$DB_IP, LocalStack=$LOCALSTACK_IP"

sed "s/172.18.0.2/$DB_IP/g; s/172.18.0.3/$LOCALSTACK_IP/g" infra/k8s/config/local/admin-configmap.yaml | kubectl apply -f -
kubectl apply -f infra/k8s/config/local/admin-secret.yaml

sed "s/172.18.0.2/$DB_IP/g; s/172.18.0.3/$LOCALSTACK_IP/g" infra/k8s/config/local/city-configmap.yaml | kubectl apply -f -
kubectl apply -f infra/k8s/config/local/city-secret.yaml

echo "Applying service deployments..."
kubectl apply -f infra/k8s/admin/admin.yaml
kubectl apply -f infra/k8s/city/clients.yaml
kubectl apply -f infra/k8s/city/couriers.yaml
kubectl apply -f infra/k8s/city/matching.yaml
kubectl apply -f infra/k8s/city/orders.yaml
kubectl apply -f infra/k8s/city/restaurants.yaml
kubectl apply -f infra/k8s/city/region.yaml

kubectl apply -f infra/k8s/admin/service-local.yaml
kubectl apply -f infra/k8s/city/service-local.yaml

echo "Ambiente local configurado com sucesso!"
