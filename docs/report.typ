
#set text(font: "Atkinson Hyperlegible", size: 12pt)
#set par(justify: true, leading: 0.65em)
#set heading(numbering: "1.1")


#align(center + top)[
  FGV EMAp
  
  Computação na nuvem - Thiago Araújo
]

#align(horizon + center)[
  #text(20pt)[
   DijkFood
  ]
  
  #text(14pt)[
    Alex Júnio Maia de Oliveira

    Bruno Ferreira Salvi

    João Pedro Jerônimo de Oliveira

    Thalis Ambrosim Falqueto
  ]
]

#align(bottom + center)[
  Rio de Janeiro

  $2026$
]

#pagebreak()


= Introdução

O presente relatório detalha a arquitetura, as decisões de projeto e os resultados de implantação da plataforma DijkFood. O sistema foi desenvolvido para gerenciar o ciclo de vida de pedidos de delivery, calculando rotas no grafo viário de São Paulo através da biblioteca `osmnx` e hospedado de forma totalmente automatizada na nuvem AWS.

= Fluxo de Dados

A arquitetura foi projetada para garantir separação de responsabilidades, alta disponibilidade e resiliência a picos de tráfego:

1. O *Application Load Balancer (ALB)* recebe o tráfego da Internet e distribui as requisições HTTP de forma balanceada.
2. O *Amazon ECS (Fargate)* hospeda os contêineres da aplicação (FastAPI), isolados em instâncias independentes.
3. *Rotas Transacionais (Pedidos, Cadastros):* A aplicação se comunica com um banco de dados relacional *Amazon RDS (PostgreSQL)* configurado em Multi-AZ para garantir a persistência atômica das entidades.
4. *Rotas de Telemetria (Rastreio $100$ms):* A posição do entregador é desviada para uma tabela NoSQL no *Amazon DynamoDB*, evitando gargalos de I/O no banco relacional.
5. *Cache do Grafo:* Durante a inicialização, as instâncias ECS acessam o *Amazon S3* para realizar o download rápido do grafo `.graphml`, mitigando tempos de inicialização lentos.

= Decisões de Projeto e Cumprimento de Requisitos

== Modelagem de Dados e Telemetria (RDS vs. DynamoDB)
- *Requisito:* O projeto exige consistência transacional na criação de pedidos, mas suporta telemetria de entregadores a cada $100$ms.
- *Alternativa Considerada:* Utilizar exclusivamente o RDS PostgreSQL para todas as operações.
- *Mudança de escolha:* Resolvemos trocar para uma persistência fazendo o uso de dois bancos (RDS + DynamoDB).
- *Justificativa:* Operações de rastreamento de posição exigem alta vazão de escrita. No cenário de evento especial ($200$ pedidos/segundo com atualizações a cada $100$ms), um banco relacional sofreria forte contenção de escritas ao mesmo tempo. O DynamoDB absorve essa carga isoladamente com latência previsível, impedindo que a saturação da telemetria degrade a leitura de dados transacionais pelos usuários e administradores, portanto a melhor escola seria integrar dois bancos de dados.

== Computação Serverless vs. Instâncias Gerenciadas (ECS Fargate vs. EC2)
- *Requisito:* O serviço deve escalar horizontalmente e tolerar falhas de instâncias de computação.
- *Alternativa Considerada:* Provisionar instâncias EC2 gerenciadas via Auto Scaling Group.
- *Opção Escolhida:* Amazon ECS operando no modo AWS Fargate.
- *Justificativa:* O Fargate abstrai a camada do sistema operacional, eliminando a necessidade de gerenciamento de AMI e patching. A escalabilidade baseada em tarefas atende de forma mais ágil os picos de almoço/jantar. Além disso, integra-se perfeitamente às restrições do Learner Lab (uso exclusivo da `LabRole` de estudante).

== Gestão de Inicialização e Cálculos de Rota
- *Requisito:* O algoritmo deve calcular as rotas utilizando caminhos mínimos sobre a rede real sem travar a API.
- *Alternativa Considerada:* O contêiner realizar o download em tempo real via API externa do OpenStreetMap.
- *Opção Escolhida:* Cache do grafo de São Paulo no Amazon S3 e implementação nativa do Algoritmo de Dijkstra.
- *Justificativa:* O download via OSMnx pode levar minutos, o que faria o Load Balancer identificar a nova instância ECS como defeituosa e encerrá-la. Ao criar um cache de backup no S3, o contêiner inicializa o grafo em disco em poucos segundos, permitindo que a API atenda os pedidos atômicos sem impacto de latência.

= Validação dos Requisitos Funcionais

A API REST implementada atende estritamente às regras de negócio mapeadas:
- *Cadastros e Validações:* Restrições de chaves estrangeiras, `CheckConstraints` (preços não negativos) e o controle de bloqueio de entregadores ocupados foram implementados.
- *Máquina de Estados de Entrega:* O fluxo `CONFIRMED -> PREPARING -> READY_FOR_PICKUP -> PICKED_UP -> IN_TRANSIT -> DELIVERED` possui transições blindadas em código, retornando erro `409 Conflict` para saltos inválidos.
- *Atribuição de Entregador:* A alocação ocorre utilizando coordenadas geográficas mapeadas em arestas do OSMnx para determinar a distância real do entregador em relação ao restaurante.

= Resultados Experimentais de Carga

Os testes foram executados utilizando um simulador assíncrono desenvolvido com a biblioteca `aiohttp`, orquestrando requisições simultâneas para validação do limite de 500ms no percentil 95 (P95). O *seed* do banco de dados e a geração de tráfego foram executados logo após o provisionamento sem intervenção manual.

#align(center)[
  #table(
    columns: (auto, auto, auto, auto),
    inset: 10pt,
    align: center,
    [*Cenário*], [*Taxa Demandada*], [*Latência Média*], [*Latência P95*],
    [Operação normal], [10 Pedidos/s], [141.64 ms], [152.17 ms],
    [Pico (Almoço/Jantar)], [50 Pedidos/s], [138.63 ms], [139.31 ms],
    [Evento Especial], [200 Pedidos/s], [193.54 ms], [198.24 ms],
  )
]

Os resultados demonstram eficiência no isolamento das cargas. O estrangulamento da computação causado pelo Dijkstra não propagou latência para o cadastro e a gravação atômica da entrega, atendendo os requisitos não-funcionais com margem segura sob condições de estresse elevado.

= Modelo de Custos (Região us-east-1)

A tabela abaixo projeta os custos mensais estimados (em USD) operando ininterruptamente, demonstrando a elasticidade de custos entre o dimensionamento para a operação base e o auto-scaling em picos estressantes.

#align(center)[
  #table(
    columns: (auto, auto, auto),
    inset: 10pt,
    align: center,
    [*Recurso AWS*], [*Operação Normal (Mensal)*], [*Evento Especial (Mensal)*],
    [ALB (Application Load Balancer)], [\$ 22.50], [\$ 25.00],
    [ECS Fargate (0.5 vCPU, 1GB)], [\$ 16.50 (2 Tasks)], [\$ 82.50 (10 Tasks)],
    [RDS PostgreSQL (db.t3.micro Multi-AZ)], [\$ 36.00], [\$ 36.00],
    [DynamoDB (Prov. 50 RCU, 200 WCU)], [\$ 28.00], [\$ 115.00 (Escalado)],
    [Amazon S3 (Armazenamento / Transf.)], [\$ 0.10], [\$ 0.30],
    [*Custo Total Estimado*], [*\$ 103.10*], [*\$ 258.80*],
  )
]

*Nota de Resiliência:* O valor constante no RDS se deve ao provisionamento fixo com `MultiAZ=True`. A alta disponibilidade sacrifica a redução de custo base para garantir sobrevivência à queda de zonas, conforme o edital do projeto.