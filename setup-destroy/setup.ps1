# admin (contexto é a raiz)
docker build -t delivery-system/admin:latest -f admin/Dockerfile .

# serviços que usam shared — contexto é a raiz
docker build -t delivery-system/clients:latest   -f clients/Dockerfile   .
docker build -t delivery-system/couriers:latest  -f couriers/Dockerfile  .
docker build -t delivery-system/matching:latest  -f matching/Dockerfile  .
docker build -t delivery-system/orders:latest    -f orders/Dockerfile    .
docker build -t delivery-system/restaurants:latest -f restaurants/Dockerfile .
docker build -t delivery-system/region:latest    -f region/Dockerfile    .

# Load images into Kind cluster if running local kind
if (Get-Command kind -ErrorAction SilentlyContinue) {
  Write-Host "Loading images into Kind cluster..."
  kind load docker-image delivery-system/admin:latest --name docker-desktop
  kind load docker-image delivery-system/matching:latest --name docker-desktop
  kind load docker-image delivery-system/orders:latest --name docker-desktop
  kind load docker-image delivery-system/clients:latest --name docker-desktop
  kind load docker-image delivery-system/couriers:latest --name docker-desktop
  kind load docker-image delivery-system/restaurants:latest --name docker-desktop
  kind load docker-image delivery-system/region:latest --name docker-desktop
} elseif (Test-Path "./bin/kind") {
  Write-Host "Loading images into Kind cluster using local binary..."
  ./bin/kind load docker-image delivery-system/admin:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/matching:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/orders:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/clients:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/couriers:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/restaurants:latest --name docker-desktop
  ./bin/kind load docker-image delivery-system/region:latest --name docker-desktop
}

# Subir infraestrutura local
docker compose up -d

# Criar fila SQS no LocalStack
docker exec -it localstack awslocal sqs create-queue --queue-name courier-locations

# Configurar contexto Kubernetes
kubectl config use-context docker-desktop

# Instalar NGINX Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# Aguardar controlador ficar pronto
kubectl wait `
  --namespace ingress-nginx `
  --for=condition=ready pod `
  --selector=app.kubernetes.io/component=controller `
  --timeout=300s

# Namespaces
kubectl apply -f infra/k8s/admin/namespace.yaml
kubectl apply -f infra/k8s/city/namespace-template.yaml

# Discover container IPs dynamically to prevent failures on different hosts/runs
$DB_IP = docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' database
if (-not $DB_IP) { $DB_IP = "172.18.0.2" }
$LOCALSTACK_IP = docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' localstack
if (-not $LOCALSTACK_IP) { $LOCALSTACK_IP = "172.18.0.3" }

Write-Host "Using container IPs: DB=$DB_IP, LocalStack=$LOCALSTACK_IP"

# ConfigMaps e Secrets
(Get-Content infra/k8s/config/local/admin-configmap.yaml) -replace "172.18.0.2", $DB_IP -replace "172.18.0.3", $LOCALSTACK_IP | kubectl apply -f -
kubectl apply -f infra/k8s/config/local/admin-secret.yaml

(Get-Content infra/k8s/config/local/city-configmap.yaml) -replace "172.18.0.2", $DB_IP -replace "172.18.0.3", $LOCALSTACK_IP | kubectl apply -f -
kubectl apply -f infra/k8s/config/local/city-secret.yaml

# Deployments
kubectl apply -f infra/k8s/admin/admin.yaml
kubectl apply -f infra/k8s/city/clients.yaml
kubectl apply -f infra/k8s/city/couriers.yaml
kubectl apply -f infra/k8s/city/matching.yaml
kubectl apply -f infra/k8s/city/orders.yaml
kubectl apply -f infra/k8s/city/restaurants.yaml
kubectl apply -f infra/k8s/city/region.yaml

# Services
kubectl apply -f infra/k8s/admin/service-local.yaml
kubectl apply -f infra/k8s/city/service-local.yaml

Write-Host "Ambiente local configurado com sucesso!"

