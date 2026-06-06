# Delivery System (Linux + Kind)

Este documento descreve o fluxo de desenvolvimento local utilizando Linux + Kind em vez do Kubernetes embutido do Docker Desktop.

## Visao geral

* Local: imagens Docker locais + Docker Compose + Kubernetes via Kind.
* Producao: EKS + ECR + kubectl apply (sem depender de imagens locais).

## Diferencas em relacao ao Docker Desktop

No Docker Desktop, o Kubernetes consegue enxergar automaticamente as imagens criadas pelo Docker local.

No Kind, o cluster Kubernetes roda dentro de containers separados. Por isso, apos cada build de imagem, e necessario carregar manualmente a imagem para dentro do cluster utilizando:

```sh
kind load docker-image <imagem> --name delivery-system
```

Caso isso nao seja feito, os pods entrarao em estado:

```text
ImagePullBackOff
ErrImagePull
```

pois o Kubernetes tentara baixar as imagens do Docker Hub.

## Requisitos

* Docker Engine
* kubectl
* kind
* AWS CLI (para AWS/EKS/ECR)
* Terraform (para infraestrutura AWS)

Verifique a instalacao:

```sh
which docker
which kubectl
which kind
```

## Desenvolvimento local

### 1) Criar cluster Kubernetes local

Criar o cluster:

```sh
kind create cluster --name delivery-system
```

Verificar:

```sh
kubectl get nodes
```

Selecionar contexto:

```sh
kubectl config use-context kind-delivery-system
```

Confirmar:

```sh
kubectl config get-contexts
kubectl cluster-info
```

### 2) Build das imagens locais

```sh
docker build -t delivery-system/admin:latest ./admin
docker build -t delivery-system/clients:latest ./clients
docker build -t delivery-system/couriers:latest ./couriers
docker build -t delivery-system/matching:latest ./matching
docker build -t delivery-system/orders:latest ./orders
docker build -t delivery-system/restaurants:latest ./restaurants
```

Caso necessario para restaurants:

```sh
docker build \
  -f restaurants/Dockerfile \
  -t delivery-system/restaurants:latest \
  .
```

### 3) Carregar imagens para o Kind

Este passo substitui o comportamento automatico do Docker Desktop.

```sh
kind load docker-image delivery-system/admin:latest --name delivery-system
kind load docker-image delivery-system/clients:latest --name delivery-system
kind load docker-image delivery-system/couriers:latest --name delivery-system
kind load docker-image delivery-system/matching:latest --name delivery-system
kind load docker-image delivery-system/orders:latest --name delivery-system
kind load docker-image delivery-system/restaurants:latest --name delivery-system
```

### 4) Subir infraestrutura local (Postgres, LocalStack, DynamoDB admin, positions)

```sh
docker compose up -d
```

Verificar:

```sh
docker ps
```

### 5) Criar fila SQS no LocalStack

```sh
docker exec -it localstack awslocal sqs create-queue --queue-name courier-locations
```

### 6) Criar tabela DynamoDB no LocalStack

```sh
docker exec -it localstack awslocal dynamodb create-table --table-name courier_positions --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=courier_id,AttributeType=N AttributeName=timestamp,AttributeType=S AttributeName=delivery_id,AttributeType=S --key-schema AttributeName=courier_id,KeyType=HASH AttributeName=timestamp,KeyType=RANGE --global-secondary-indexes "IndexName=gsi-delivery,KeySchema=[{AttributeName=delivery_id,KeyType=HASH},{AttributeName=timestamp,KeyType=RANGE}],Projection={ProjectionType=ALL}"
```

Verificacao rapida:

```sh
docker exec -it localstack awslocal dynamodb list-tables

docker exec -it localstack awslocal dynamodb describe-table \
  --table-name courier_positions
```

### 7) Instalar NGINX Ingress Controller

```sh
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

kubectl wait \
  --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=300s
```

Verificar:

```sh
kubectl get pods -n ingress-nginx
```

### 8) Aplicar manifests locais

```sh
kubectl apply -f infra/k8s/admin/namespace.yaml
kubectl apply -f infra/k8s/city/namespace-template.yaml

kubectl apply -f infra/k8s/config/local/admin-configmap.yaml
kubectl apply -f infra/k8s/config/local/admin-secret.yaml
kubectl apply -f infra/k8s/config/local/city-configmap.yaml
kubectl apply -f infra/k8s/config/local/city-secret.yaml

kubectl apply -f infra/k8s/admin/admin.yaml
kubectl apply -f infra/k8s/city/clients.yaml
kubectl apply -f infra/k8s/city/couriers.yaml
kubectl apply -f infra/k8s/city/matching.yaml
kubectl apply -f infra/k8s/city/orders.yaml
kubectl apply -f infra/k8s/city/restaurants.yaml

kubectl apply -f infra/k8s/admin/service-local.yaml
kubectl apply -f infra/k8s/city/service-local.yaml
```

### 9) Verificar deploys

Verificar pods:

```sh
kubectl get pods -A
```

Todos os servicos devem estar:

```text
READY   1/1
STATUS  Running
```

Verificar deployments:

```sh
kubectl get deployments -A
```

Verificar services:

```sh
kubectl get svc -A
```

### 10) Testes de saude

Como o Kind nao expoe automaticamente os NodePorts da mesma forma que o Docker Desktop, utilize port-forward.

Abrir os forwards:

```sh
kubectl port-forward -n admin-namespace svc/admin 4000:4000 >/tmp/admin.log 2>&1 &

kubectl port-forward -n city-example-namespace svc/clients 4001:4001 >/tmp/clients.log 2>&1 &

kubectl port-forward -n city-example-namespace svc/couriers 4002:4002 >/tmp/couriers.log 2>&1 &

kubectl port-forward -n city-example-namespace svc/matching 4003:4003 >/tmp/matching.log 2>&1 &

kubectl port-forward -n city-example-namespace svc/orders 4004:4004 >/tmp/orders.log 2>&1 &

kubectl port-forward -n city-example-namespace svc/restaurants 4005:4005 >/tmp/restaurants.log 2>&1 &
```

Executar os health checks:

```sh
curl http://localhost:4000/health
curl http://localhost:4001/health
curl http://localhost:4002/health
curl http://localhost:4003/health
curl http://localhost:4004/health
curl http://localhost:4005/health
```

Resultado esperado:

```json
{"status":"ok"}
```

para todos os servicos.

### 11) Atualizacao de codigo local

Sempre que reconstruir uma imagem:

```sh
docker build -t delivery-system/orders:latest ./orders
```

Carregar novamente para o Kind:

```sh
kind load docker-image delivery-system/orders:latest --name delivery-system
```

Reiniciar deployment:

```sh
kubectl rollout restart deployment/orders -n city-example-namespace

kubectl rollout status deployment/orders -n city-example-namespace
```

O mesmo procedimento vale para qualquer servico.

### Atualizando admin

```sh
docker build -t delivery-system/admin:latest ./admin

kind load docker-image delivery-system/admin:latest --name delivery-system

kubectl rollout restart deployment/admin -n admin-namespace

kubectl rollout status deployment/admin -n admin-namespace
```

### Atualizando restaurants

```sh
docker build -t delivery-system/restaurants:latest ./restaurants

kind load docker-image delivery-system/restaurants:latest --name delivery-system

kubectl rollout restart deployment/restaurants -n city-example-namespace

kubectl rollout status deployment/restaurants -n city-example-namespace
```

### Atualizando positions

```sh
docker compose up -d --build positions
```

## Cleanup local

Remover workloads:

```sh
kubectl delete -f infra/k8s/admin/admin.yaml
kubectl delete -f infra/k8s/city/clients.yaml
kubectl delete -f infra/k8s/city/couriers.yaml
kubectl delete -f infra/k8s/city/matching.yaml
kubectl delete -f infra/k8s/city/orders.yaml
kubectl delete -f infra/k8s/city/restaurants.yaml

kubectl delete -f infra/k8s/admin/service-local.yaml
kubectl delete -f infra/k8s/city/service-local.yaml
```

Remover configuracoes:

```sh
kubectl delete -f infra/k8s/config/local/admin-configmap.yaml
kubectl delete -f infra/k8s/config/local/admin-secret.yaml
kubectl delete -f infra/k8s/config/local/city-configmap.yaml
kubectl delete -f infra/k8s/config/local/city-secret.yaml
```

Remover namespaces:

```sh
kubectl delete -f infra/k8s/admin/namespace.yaml
kubectl delete -f infra/k8s/city/namespace-template.yaml
```

Remover ingress:

```sh
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
```

Parar infraestrutura Docker:

```sh
docker compose down -v
```

Remover cluster Kind:

```sh
kind delete cluster --name delivery-system
```

