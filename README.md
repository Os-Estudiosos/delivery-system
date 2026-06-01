# Delivery System
Esse repositorio contem a infraestrutura Kubernetes de um aplicativo de delivery idealizado para a AWS.

![Infraestrutura](images/infra.svg)

## Visao geral

- Local: imagens Docker locais + Docker Compose + Kubernetes do Docker Desktop.
- Producao: EKS + ECR + kubectl apply (sem depender de imagens locais).

## Requisitos

- Docker Desktop (com Kubernetes habilitado)
- kubectl
- AWS CLI (para AWS/EKS/ECR)
- Terraform (para infraestrutura AWS)

## Desenvolvimento local

### 1) Build das imagens locais

```sh
docker build -t delivery-system/admin:latest ./admin
docker build -t delivery-system/clients:latest ./clients
docker build -t delivery-system/couriers:latest ./couriers
docker build -t delivery-system/matching:latest ./matching
docker build -t delivery-system/orders:latest ./orders
docker build -t delivery-system/restaurants:latest ./restaurants
```

### 2) Subir infraestrutura local (Postgres, LocalStack, DynamoDB admin, positions)

```sh
docker compose up -d
```

### 3) Criar fila SQS no LocalStack

```sh
docker exec -it localstack awslocal sqs create-queue --queue-name courier-locations
```

### 4) Criar tabela DynamoDB no LocalStack

```sh
docker exec -it localstack awslocal dynamodb create-table --table-name courier_positions --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=courier_id,AttributeType=N AttributeName=timestamp,AttributeType=S AttributeName=delivery_id,AttributeType=S --key-schema AttributeName=courier_id,KeyType=HASH AttributeName=timestamp,KeyType=RANGE --global-secondary-indexes "IndexName=gsi-delivery,KeySchema=[{AttributeName=delivery_id,KeyType=HASH},{AttributeName=timestamp,KeyType=RANGE}],Projection={ProjectionType=ALL}"
```

Verificacao rapida:

```sh
docker exec -it localstack awslocal dynamodb list-tables
docker exec -it localstack awslocal dynamodb describe-table --table-name courier_positions
```

### 5) Selecionar contexto do Kubernetes local

```sh
kubectl config use-context docker-desktop
```

### 6) Instalar NGINX Ingress Controller (local)

```sh
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=300s
```

### 7) Aplicar manifests locais

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

### 8) Testes de saude

```sh
curl http://localhost:30040/health
curl http://localhost:30041/health
curl http://localhost:30042/health
curl http://localhost:30044/health
curl http://localhost:30045/health
```

### 9) Atualizacao de codigo local

Quando alterar o codigo de um servico, rebuilde a imagem e reinicie o deployment.

```sh
# Exemplo: orders
docker build -t delivery-system/orders:latest ./orders
kubectl rollout restart deployment/orders -n city-sp-namespace
kubectl rollout status deployment/orders -n city-sp-namespace
```

Para o consumer positions (Docker Compose):

```sh
docker compose up -d --build positions
```

### 10) Cleanup local

```sh
kubectl delete -f infra/k8s/admin/admin.yaml
kubectl delete -f infra/k8s/city/clients.yaml
kubectl delete -f infra/k8s/city/couriers.yaml
kubectl delete -f infra/k8s/city/matching.yaml
kubectl delete -f infra/k8s/city/orders.yaml
kubectl delete -f infra/k8s/city/restaurants.yaml
kubectl delete -f infra/k8s/admin/service-local.yaml
kubectl delete -f infra/k8s/city/service-local.yaml

kubectl delete -f infra/k8s/config/local/admin-configmap.yaml
kubectl delete -f infra/k8s/config/local/admin-secret.yaml
kubectl delete -f infra/k8s/config/local/city-configmap.yaml
kubectl delete -f infra/k8s/config/local/city-secret.yaml

kubectl delete -f infra/k8s/admin/namespace.yaml
kubectl delete -f infra/k8s/city/namespace-template.yaml
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
docker compose down -v
```

## Producao (AWS / EKS + ECR)

### Pré requisito
Você deve ter em seu computador o CLI da AWS instalado e configurado com seu id e chave secreta (e se você usar uma conta AWS Learner Lab, também informe seu token temporário)

### 1) Provisionar infraestrutura com Terraform

```sh
cd infra/terraform/aws
terraform init
terraform apply -var-file="prod.tfvars"
```

Se voce usa roles diferentes para o EKS, ajuste estas variaveis no `prod.tfvars`:

- `eks_cluster_role_arn`
- `eks_node_role_arn`
- `eks_attach_ecr_readonly` (mantem permissao de pull no ECR)

### 2) Configurar kubeconfig do EKS

```sh
aws eks update-kubeconfig --name <cluster_name> --region us-east-1
```

> Dica: o output do Terraform inclui um comando pronto para atualizar o kubeconfig.

### 3) Preencher ConfigMaps e Secrets de producao

- Atualize o endpoint do RDS em [infra/k8s/config/prod/admin-configmap.yaml](infra/k8s/config/prod/admin-configmap.yaml).
- Atualize o endpoint do RDS em [infra/k8s/config/prod/city-configmap.yaml](infra/k8s/config/prod/city-configmap.yaml).
- Preencha as credenciais em `infra/k8s/config/prod/*-secret.yaml` (arquivos ignorados pelo git).

### 4) Login no ECR

```sh
$AWS_REGION = "us-east-1"
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$ECR_REGISTRY = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
$TAG = "latest"

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
```

### 5) Build e push das imagens para o ECR

```sh
# admin
docker build -t delivery-system/admin:$TAG ./admin
docker tag delivery-system/admin:$TAG $ECR_REGISTRY/delivery-system/admin:$TAG
docker push $ECR_REGISTRY/delivery-system/admin:$TAG

# clients
docker build -t delivery-system/clients:$TAG ./clients
docker tag delivery-system/clients:$TAG $ECR_REGISTRY/delivery-system/clients:$TAG
docker push $ECR_REGISTRY/delivery-system/clients:$TAG

# couriers
docker build -t delivery-system/couriers:$TAG ./couriers
docker tag delivery-system/couriers:$TAG $ECR_REGISTRY/delivery-system/couriers:$TAG
docker push $ECR_REGISTRY/delivery-system/couriers:$TAG

# matching
docker build -t delivery-system/matching:$TAG ./matching
docker tag delivery-system/matching:$TAG $ECR_REGISTRY/delivery-system/matching:$TAG
docker push $ECR_REGISTRY/delivery-system/matching:$TAG

# orders
docker build -t delivery-system/orders:$TAG ./orders
docker tag delivery-system/orders:$TAG $ECR_REGISTRY/delivery-system/orders:$TAG
docker push $ECR_REGISTRY/delivery-system/orders:$TAG

# restaurants
docker build -t delivery-system/restaurants:$TAG ./restaurants
docker tag delivery-system/restaurants:$TAG $ECR_REGISTRY/delivery-system/restaurants:$TAG
docker push $ECR_REGISTRY/delivery-system/restaurants:$TAG
```

### 6) Aplicar manifests de producao

```sh
kubectl apply -f infra/k8s/admin/namespace.yaml
kubectl apply -f infra/k8s/city/namespace-template.yaml

kubectl apply -f infra/k8s/config/prod/admin-configmap.yaml
kubectl apply -f infra/k8s/config/prod/admin-secret.yaml
kubectl apply -f infra/k8s/config/prod/city-configmap.yaml
kubectl apply -f infra/k8s/config/prod/city-secret.yaml

kubectl apply -f infra/k8s/admin/admin.yaml
kubectl apply -f infra/k8s/city/clients.yaml
kubectl apply -f infra/k8s/city/couriers.yaml
kubectl apply -f infra/k8s/city/matching.yaml
kubectl apply -f infra/k8s/city/orders.yaml
kubectl apply -f infra/k8s/city/restaurants.yaml
kubectl apply -f infra/k8s/admin/service-prod.yaml
kubectl apply -f infra/k8s/city/service-prod.yaml
```

Se o seu IngressClass nao for `nginx`, ajuste o campo `spec.ingressClassName` nos manifests de Ingress.

Os hosts dos Ingresses sao `.local`. Para producao, substitua os hosts por dominios reais ou use `curl -H "Host: ..."` durante os testes.

### 7) Atualizar imagens para o ECR

```sh
kubectl set image deployment/admin admin=$ECR_REGISTRY/delivery-system/admin:$TAG -n admin-namespace
kubectl set image deployment/clients clients=$ECR_REGISTRY/delivery-system/clients:$TAG -n city-example-namespace
kubectl set image deployment/couriers couriers=$ECR_REGISTRY/delivery-system/couriers:$TAG -n city-example-namespace
kubectl set image deployment/matching matching=$ECR_REGISTRY/delivery-system/matching:$TAG -n city-example-namespace
kubectl set image deployment/orders orders=$ECR_REGISTRY/delivery-system/orders:$TAG -n city-example-namespace
kubectl set image deployment/restaurants restaurants=$ECR_REGISTRY/delivery-system/restaurants:$TAG -n city-example-namespace
```

Sempre que reaplicar os manifests dos deployments, execute novamente os comandos de `kubectl set image`.

### 8) Verificar pods

```sh
kubectl get pods -n admin-namespace
kubectl get pods -n city-example-namespace
kubectl describe pods -n admin-namespace
kubectl describe pods -n city-example-namespace
```

### 9) Instalar NGINX Ingress Controller no EKS

```sh
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/aws/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=300s
```

### 10) Obter URL publica

```sh
kubectl get svc -n ingress-nginx
```

Use o EXTERNAL-IP do `ingress-nginx-controller` e aponte um dominio/hosts para esse IP. Para testar sem DNS:

```sh
curl -H "Host: admin.admin-namespace.local" http://<EXTERNAL-IP>/health
```

### 11) Atualizar versoes (ECR)

1. Build e push com nova tag:

```sh
$TAG = "v1"
# repita os comandos de build e push do passo 5
```

2. Aplique a nova tag nos deployments:

```sh
kubectl set image deployment/admin admin=$ECR_REGISTRY/delivery-system/admin:$TAG -n admin-namespace
kubectl set image deployment/clients clients=$ECR_REGISTRY/delivery-system/clients:$TAG -n city-example-namespace
kubectl set image deployment/couriers couriers=$ECR_REGISTRY/delivery-system/couriers:$TAG -n city-example-namespace
kubectl set image deployment/matching matching=$ECR_REGISTRY/delivery-system/matching:$TAG -n city-example-namespace
kubectl set image deployment/orders orders=$ECR_REGISTRY/delivery-system/orders:$TAG -n city-example-namespace
kubectl set image deployment/restaurants restaurants=$ECR_REGISTRY/delivery-system/restaurants:$TAG -n city-example-namespace
kubectl rollout status deployment/admin -n admin-namespace
```

### 12) Destruir infraestrutura (EKS)

```sh
kubectl delete -f infra/k8s/admin/admin.yaml
kubectl delete -f infra/k8s/city/clients.yaml
kubectl delete -f infra/k8s/city/couriers.yaml
kubectl delete -f infra/k8s/city/matching.yaml
kubectl delete -f infra/k8s/city/orders.yaml
kubectl delete -f infra/k8s/city/restaurants.yaml
kubectl delete -f infra/k8s/admin/service-prod.yaml
kubectl delete -f infra/k8s/city/service-prod.yaml

kubectl delete -f infra/k8s/config/prod/admin-configmap.yaml
kubectl delete -f infra/k8s/config/prod/admin-secret.yaml
kubectl delete -f infra/k8s/config/prod/city-configmap.yaml
kubectl delete -f infra/k8s/config/prod/city-secret.yaml

kubectl delete -f infra/k8s/admin/namespace.yaml
kubectl delete -f infra/k8s/city/namespace-template.yaml
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/aws/deploy.yaml

cd infra/terraform/aws
terraform destroy -var-file=prod.tfvars
```

> Observacao: se o destroy falhar por causa de imagens no ECR, apague as imagens ou defina `ecr_force_delete=true` e reaplique antes do destroy.

## Alternativas para build e push das imagens

- Terraform (nao recomendado): reduz passos manuais, mas torna o `terraform apply` mais lento, fragil e dependente de Docker/credenciais locais.
- Scripts de deploy (recomendado aqui): simples, explicito, controle total do processo e facil de rodar em qualquer ambiente.
- CI/CD (recomendado para times): automatiza build, tag e push com politicas de aprovacao e auditoria; requer configuracao de secrets/OIDC e esteira.
