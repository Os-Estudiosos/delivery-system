# Analytics Layer

## Objetivo

Implementar uma camada analítica capaz de gerar indicadores agregados da operação do sistema de delivery.

## Indicadores

### 1. Volume de pedidos ao longo do tempo

Quantidade de pedidos agrupados por dia, semana ou mês.

### 2. Tempo médio por etapa do ciclo de vida

Tempo médio gasto entre os estados:

* CONFIRMED
* PREPARING
* READY_FOR_PICKUP
* PICKED_UP
* IN_TRANSIT
* DELIVERED

### 3. Distribuição de pedidos por região

Quantidade de pedidos agrupados pela região associada ao restaurante.

### 4. Heatmap de demanda

Distribuição de pedidos por:

* Dia da semana
* Hora do dia

### 5. Top 10 restaurantes

Ranking de restaurantes por volume de pedidos.

### 6. Histograma de tempo total de entrega

Distribuição do tempo entre:

CONFIRMED → DELIVERED

---

## Roadmap

### Fase 1 - Geração de Dados

Criar simulador capaz de popular:

* regiões
* usuários
* restaurantes
* itens
* entregadores
* pedidos
* entregas
* eventos

com dados sintéticos.

### Fase 2 - Dashboard Local

Construir dashboard utilizando Streamlit conectado diretamente ao PostgreSQL.

### Fase 3 - Camada Analítica AWS

Implementar arquitetura analítica baseada em:

* S3
* Athena
* Glue
* Dashboard

seguindo a arquitetura proposta do projeto.

---

## Observações

Atualmente o modelo SQLAlchemy representa a fonte de verdade do schema.

O arquivo DDL.sql encontra-se desatualizado e deve ser sincronizado com:

shared/database/models.py

principalmente em relação à entidade Region.

