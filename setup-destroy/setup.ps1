# Build das imagens Docker
docker build -t delivery-system/admin:latest ./admin
docker build -t delivery-system/clients:latest ./clients
docker build -t delivery-system/couriers:latest ./couriers
docker build -t delivery-system/matching:latest ./matching
docker build -t delivery-system/orders:latest ./orders
docker build -t delivery-system/restaurants:latest -f restaurants/Dockerfile .

# Subir infraestrutura local
docker compose up -d

# Criar fila SQS no LocalStack
docker exec -it localstack awslocal sqs create-queue --queue-name courier-locations

# Configurar contexto Kubernetes
kubectl config use-context docker-desktop

# Instalar NGINX Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

# Aguardar controlador ficar pronto
kubectl wait `
  --namespace ingress-nginx `
  --for=condition=ready pod `
  --selector=app.kubernetes.io/component=controller `
  --timeout=300s

# Namespaces
kubectl apply -f infra/k8s/admin/namespace.yaml
kubectl apply -f infra/k8s/city/namespace-template.yaml

# ConfigMaps e Secrets
kubectl apply -f infra/k8s/config/local/admin-configmap.yaml
kubectl apply -f infra/k8s/config/local/admin-secret.yaml
kubectl apply -f infra/k8s/config/local/city-configmap.yaml
kubectl apply -f infra/k8s/config/local/city-secret.yaml

# Deployments
kubectl apply -f infra/k8s/admin/admin.yaml
kubectl apply -f infra/k8s/city/clients.yaml
kubectl apply -f infra/k8s/city/couriers.yaml
kubectl apply -f infra/k8s/city/matching.yaml
kubectl apply -f infra/k8s/city/orders.yaml
kubectl apply -f infra/k8s/city/restaurants.yaml

# Services
kubectl apply -f infra/k8s/admin/service-local.yaml
kubectl apply -f infra/k8s/city/service-local.yaml

Write-Host "Ambiente local configurado com sucesso!"

