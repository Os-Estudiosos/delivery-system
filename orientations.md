# Especificação do Sistema: Plataforma DijkFood

## 1. Visão Geral
A DijkFood é uma plataforma de delivery de comida que conecta clientes, restaurantes e entregadores. A aplicação é responsável por calcular as rotas mais curtas de entrega sobre grafos viários utilizando dados da OpenStreetMap através da biblioteca `osmnx`.
O sistema operará na nuvem da AWS, tendo como recursos base disponíveis: EC2, RDS, DynamoDB, ECS e S3. Além disso, a arquitetura deve obrigatoriamente aplicar conceitos de **Orquestração de Contêineres com Kubernetes (EKS)** de forma que contribua ativamente para os objetivos de escalabilidade do projeto.

---

## 2. Requisitos Funcionais e Ciclo de Vida

### 2.1. Gestão de Entidades (Administrador)
* Cadastrar clientes (nome, e-mail, telefone, localização geográfica).
* Cadastrar restaurantes (nome, tipo de cozinha, localização geográfica).
* Cadastrar entregadores (nome, tipo de veículo, localização geográfica inicial).
* Consultar histórico cronológico de pedidos de um cliente.
* Consultar histórico cronológico de eventos de um pedido.

### 2.2. Gestão de Pedidos (Clientes)
* Criar pedido informando o restaurante e a lista de itens. Esta criação deve ser atômica (garantir existência do cliente/restaurante e evitar estados parciais em caso de falha).
* Consultar o estado corrente de um pedido (status, entregador selecionado e posição atual).

### 2.3. Dinâmica de Entrega (Sistema e Entregadores)
* Ao receber um pedido, o sistema encontra o entregador mais adequado e calcula a rota.
* Um entregador não pode ser escolhido se já estiver em rota. Após finalizar a entrega, ele deve aguardar no mesmo local.
* Entregadores reportam sua posição continuamente desde o deslocamento para o restaurante até a casa do cliente.

### 2.4. Máquina de Estados do Pedido
O sistema possui uma ordem estrita e obrigatória de transição de status. Mudanças fora dessa sequência ou estados inválidos devem ser rejeitados:
1. `PREPARING`
2. `READY_FOR_PICKUP`
3. `PICKED_UP`
4. `IN_TRANSIT`
5. `DELIVERED`

### 2.5. Interface
* Todo o serviço deve ser acessível via **API REST**.
* Todas as entidades devem suportar operações CRUD referentes ao seu ciclo de vida.

---

## 3. Objetivo Principal: Escala para Múltiplas Cidades
O sistema deve ser capaz de operar simultaneamente em diversas cidades, garantindo isolamento de recursos e facilidade de expansão:
* Cada cidade possui um grafo viário, restaurantes, entregadores e clientes próprios.
* O processamento e a infraestrutura devem garantir que a demanda de uma cidade não interfira na performance (recursos) das outras.
* Deve ser criado um **Dashboard Administrativo** para registrar e incluir uma nova cidade sem nenhuma necessidade de alteração no código ou infraestrutura.
* A arquitetura precisa definir claramente quais microsserviços/componentes serão *replicados* por cidade e quais serão *compartilhados* globalmente.

---

## 4. Camada Analítica de Dados
Uma infraestrutura de dados separada deve ser construída para não impactar a operação transacional:
* **Ingestão e Persistência:** Todos os eventos da plataforma (criações de pedido, transições de estado, posições reportadas) devem ser persistidos em um armazenamento de dados durável.
* **Dashboard Analítico (Batch):** Exibir métricas agregadas da operação. Deve conter obrigatoriamente:
    * Volume de pedidos no tempo.
    * Tempo médio em cada etapa do ciclo de vida.
    * Distribuição de pedidos por região.
    * Heatmap de demanda (por horário/dia da semana).
    * Top 10 restaurantes por volume de vendas.
    * Histograma com o tempo total das entregas.

---

## 5. Requisitos Não-Funcionais e Desempenho

### 5.1. Carga Operacional Esperada
* **Operação normal:** 10 pedidos/segundo.
* **Pico (almoço/jantar):** 50 pedidos/segundo.
* **Evento especial:** 200 pedidos/segundo.
* *Condições globais:* A proporção é de 3 entregadores para cada 1 cliente cadastrado. Entregadores em trânsito atualizam a geolocalização a cada 100ms.

### 5.2. Escalabilidade, Resiliência e SLA
* **Isolamento:** A saturação ou pico em um componente (ex: cálculo pesado de rota) não pode aumentar a latência de outros serviços (ex: consulta de status).
* **Autoscaling:** Escalonamento horizontal e independente para cada componente, conforme o seu próprio workload.
* **Alta Disponibilidade:** Tolerância à falha de uma Zona de Disponibilidade inteira e capacidade de continuar respondendo ao cliente sem interrupção perceptível em caso de queda de uma instância de computação isolada.
* **Latência:** Consultas e registros via API devem responder em menos de 500ms (no percentil 95).

---

## 6. Automação, Implantação e Simulador de Carga

### 6.1. IaC e Deploy Automático
Deve existir um script (`deploy.py` ou ferramenta IaC pura, como Terraform) de ponta a ponta sem intervenção humana que execute:
1. A criação total dos recursos na AWS.
2. O deploy dos contêineres e banco de dados.
3. A execução do simulador de carga.
4. A destruição completa (`teardown`) ao finalizar.
*(Proibido manter credenciais hardcoded, deve-se usar `~/.aws/credentials`)*

### 6.2. Simulador de Carga Avançado
Um script Python capaz de validar os limites do sistema:
* Popular automaticamente entidades base via API.
* Emitir requisições que modelem as três fases de carga (Normal, Pico e Especial), coletando métricas de latência para validar o limite de 500ms e o throughput efetivo.
* Registrar simultaneamente todo o fluxo de entregas e atualizações massivas de GPS (100ms).
* Executar simulações regionais específicas do Objetivo 2 (aumento súbito de demanda num bairro específico, concentração de chamados num restaurante, escassez repentina de motoristas na região).

---

## 7. Entregáveis Técnicos Finais
* **Código fonte:** Sistema, Camada Analítica, Serviços Kubernetes, Infraestrutura como Código (IaC) e Simulador.
* **Relatório Arquitetural (PDF):** Diagrama completo de infra e fluxo de dados AWS, design pattern escolhido, justificativas das decisões de projeto, integração explicada do Kubernetes e relatórios extraídos das métricas do simulador.
* **Modelo de Custos:** Estimativa mensal (em USD para `us-east-1`) comparando o baseline de "Operação Normal" contra o burst de "Evento Especial".
* **Vídeo:** Gravação atestando que a execução do script provisiona a nuvem e que a plataforma suporta os requisitos perfeitamente.

## 8. Arquitetura SUGERIDA PELOS ALUNOS (NÃO OBRIGATÓRIA), aceitam-se outras abordagens
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

fique a vontade para sugerir melhorias de arquitetura, mas o importante é que a solução final atenda a todos os requisitos funcionais e não-funcionais descritos.