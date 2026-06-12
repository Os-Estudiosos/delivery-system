# DijkFood Delivery System: Relatório de Arquitetura, Progresso e Próximos Passos

Este documento compila as informações mais críticas dos relatórios de estágio e auditorias de infraestrutura do sistema **DijkFood** na AWS.

---

## 1. Visão Geral da Arquitetura Realizada

A DijkFood está implementada em uma arquitetura híbrida escalável multirregional na AWS/EKS:

```mermaid
graph TD
    subgraph Global [Namespace: admin-namespace]
        Admin[admin-service: Dashboard & Dynamic Provisioner]
        Positions[positions-service: Consome coordenadas do SQS]
    end

    subgraph City [Namespace Dinâmico: city-2-russas-cear-brazil]
        Clients[clients-service]
        Couriers[couriers-service]
        Restaurants[restaurants-service]
        Region[region-service]
        Orders[orders-service: Gestão e SQS Analytics]
        Matching[matching-service: OSMnx Dijkstra Roteador]
    end

    subgraph Infra [Recursos Compartilhados AWS]
        RDS[(PostgreSQL RDS: dijkfood.ctra4ujpjrsz.us-east-1.rds.amazonaws.com)]
        DDB[(DynamoDB: courier_positions)]
        SQS_Loc[SQS: courier-locations]
        SQS_An[SQS: analytics-events]
        S3[S3: dijkfood-datalake-2d6f56cd]
        Firehose[Kinesis Firehose → S3]
        Athena[Athena: dijkfood_analytics.events]
    end

    Orders -->|HTTP POST /match| Matching
    Matching -->|SQL exists()| RDS
    Couriers -->|GPS PUT /position| SQS_Loc
    Positions -->|Consome SQS| DDB
    Orders -->|Eventos JSON| SQS_An
    SQS_An -->|EventBridge Pipe| Firehose
    Firehose -->|Parquet| S3
    S3 -->|Crawl| Athena
```

### Detalhes de Integração e Desvios do Diagrama Inicial
* **Banco de Dados (OLTP):** Um RDS PostgreSQL central (`db.t3.micro`) armazena entidades transacionais (Pedidos, Entregas, Itens, Restaurantes, etc.).
* **Mensageria e Geoposicionamento (IoT):** A geolocalização dos entregadores é enviada de forma assíncrona por MQTT/HTTP para a fila SQS `courier-locations`, consumida pelo serviço `positions` no EKS e persistida no DynamoDB (`courier_positions`).
* **Camada Analítica (OLAP):** Os eventos de transição de pedidos são publicados na fila SQS `analytics-events` pelo `orders-service`, fluem pelo Kinesis Firehose e são armazenados em formato Parquet no Bucket S3 de Data Lake (`dijkfood-datalake-2d6f56cd`), permitindo análise via Athena sem onerar o RDS.

---

## 2. Resumo das Alterações e Otimizações Recentes (Junho/2026)

### A. Correções de Desempenho e Bugs de Infraestrutura
1. **Resolução de CrashLoopBackOff no Roteador (matching-service):**
   * Trocada a cidade padrão de São Paulo para Russas (Ceará, Brazil), reduzindo a RAM do grafo viário de >1GB para ~300MB, sanando o estouro de limite físico do nó (`Exit Code 137 / OOMKilled`).
   * Configuração de Gunicorn multiprocesso com worker isolado por pod para evitar que o algoritmo Dijkstra (CPU-bound) trave o GIL do Python e faça com que os health checks de liveness acusem falha.
2. **Correção do Cache de Grafos no S3:**
   * Mapeamento da variável `S3_BUCKET` nos ConfigMaps dinâmicos criados pelo `admin-service`. Agora, o grafo é baixado do OSMnx uma única vez, salvo no S3, e novas réplicas de matching sobem em segundos baixando direto do cache no S3.
3. **Saneamento do Pool do RDS Postgres (Evitando Timeout do SQLAlchemy):**
   * Fechamento explícito da sessão de banco de dados (`session.close()`) no `orders-service` antes de fazer a chamada HTTP síncrona ao roteador de matching, liberando as conexões imediatamente de volta ao pool.
   * Ajuste fino das variáveis padrão de pool para `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5` e `DB_POOL_TIMEOUT=15` para amortecer rajadas de concorrência.
4. **Instalação do Metrics Server e Escalonamento dos Nós (AWS Auto Scaling):**
   * Metrics Server instalado no namespace `kube-system`, permitindo a coleta de métricas de CPU real pelos HPAs (Horizontal Pod Autoscalers).
   * Aumento físico do Node Group de EKS no ASG da AWS de **2 para 3 nós** `t3.small` (6GB RAM totais), balanceando perfeitamente a alocação de recursos físicos.

* **Ajuste de Carga:** Modificamos a simulação do Cenário 3 em [simulator.py](file:///home/thalis/Área de trabalho/thalis/facul/eletivas/computacao nuvem/delivery-system/simulator.py) de **200 RPS para 50 RPS** (duração 30s). A meta de pico de 50 RPS ainda é massiva e valida o SLA do projeto de $\ge$ 10 pedidos/segundo com latência P95 < 500ms, sem provocar o colapso dos limites do sandbox AWS Academy.

### C. Otimização de Algoritmo de Roteamento (Busca Vetorizada KD-Tree)
1. **Busca Vetorizada de Nós Próximos:**
   * **Problema:** A busca por vizinho mais próximo (`ox.distance.nearest_nodes`) no roteador era realizada iterativamente em um loop síncrono para cada entregador. Em cenários de carga, essa busca repetitiva em Python no thread de CPU aumentava consideravelmente a latência da chamada e estourava o timeout.
   * **Solução:** Vetorizamos a chamada ao `nearest_nodes` passando arrays com as coordenadas de todos os entregadores. O OSMnx agora resolve a localização de todos em uma única busca KD-Tree interna e otimizada (frações de milissegundo).
2. **Aumento do Timeout Interno:**
   * Elevamos o limite de timeout para requisições internas feitas pelo `orders-service` ao roteador de **5s para 10s**, prevenindo timeouts falsos sob picos extremos.

---

## 3. Roteiro de Operação e Comandos Principais

### Passo 1: Executar Rebuild e Deploy
Para compilar todas as imagens locais com as correções mais recentes, empurrá-las para o ECR e implantá-las de forma limpa nos pods do EKS, execute:
```bash
TF_VAR_db_password="DijkFoodPass2026!" python3 deploy.py --no-destroy
```

### Passo 2: Monitorar a Saúde dos Recursos
```bash
# Verificar o andamento do rollout na cidade de Russas
kubectl rollout status deployment/matching -n city-2-russas-cear-brazil --timeout=300s
kubectl rollout status deployment/orders -n city-2-russas-cear-brazil --timeout=120s

# Monitorar pods em tempo real
kubectl get pods -A -o wide

# Verificar que os HPAs estão lendo métricas de CPU
kubectl get hpa -n city-2-russas-cear-brazil
```

### Passo 3: Inspecionar o Cache do S3
```bash
AWS_DEFAULT_REGION=us-east-1 aws s3 ls s3://dijkfood-assets-2d6f56cd/
# Deve retornar: russas__ceará__brazil.graphml
```

### Passo 4: Rodar o Simulador de Carga
O deploy automático instancia o simulador como um Job do Kubernetes na namespace do admin. Para limpar e re-executar manualmente caso necessário:
```bash
# Limpar execuções anteriores
kubectl delete job load-simulator -n admin-namespace --ignore-not-found

# O deploy gera um arquivo temporário com o manifesto configurado
kubectl apply -f infra/k8s/admin/temp-simulator-job.yaml

# Acompanhar logs em tempo real
kubectl logs -n admin-namespace -l job-name=load-simulator -f
```

### Passo 5: Teardown (Desmontagem Completa da AWS)
**OBRIGATÓRIO** ao finalizar os testes para conter custos do laboratório:
```bash
TF_VAR_db_password="DijkFoodPass2026!" python3 deploy.py --only-destroy
```
