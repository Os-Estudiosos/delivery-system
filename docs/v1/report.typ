
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

    João Pedro Jerônimo de Oliveir

    Thalis Ambrosim Falqueto
  ]
]

#align(bottom + center)[
  Rio de Janeiro

  $2026$
]

#pagebreak()


= Introdução

O presente relatório detalha a arquitetura, as decisões de projeto e os resultados de implantação da plataforma DijkFood. O sistema foi desenvolvido para gerenciar o ciclo de vida de pedidos de delivery, calculando rotas no grafo viário de várias cidades através da biblioteca `osmnx` e hospedado de forma totalmente automatizada na nuvem AWS, tendo como base o serviço de Kubernetes da AWS (EKS). O projeto foi implementado utilizando uma arquitetura de microsserviços, com foco em escalabilidade, resiliência e observabilidade, atendendo aos requisitos funcionais e não-funcionais estabelecidos.

= Arquitetura

== Apenas uma cidade

Em resumo, a arquitetura proposta para comportar o sistema de delivery em apenas uma cidade é composta por um Application Load Balancer (ALB) que distribui as requisições dos usuários para um cluster Amazon ECS (que contém os conteiners dos serviços) operando no modo Fargate, juntamente com Auto Scaling para gerenciar a capacidade de execução. A persistência de dados é realizada por um banco relacional Amazon RDS (PostgreSQL) para as operações transacionais, enquanto a telemetria de entregadores é armazenada em uma tabela NoSQL do Amazon DynamoDB. O grafo viário é pré-processado e armazenado no Amazon S3, permitindo inicialização rápida das instâncias ECS. Por fim, os logs e métricas são coletados utilizando o Amazon CloudWatch, garantindo monitoramento e observabilidade contínuos do serviço. Abaixo se encontra um diagrama de alto nível da arquitetura utilizada:

#align(center)[
  #image("diagrams/Diagrama Dijksfood.png", height: 47%)
]

== Várias cidades

A arquitetura para comportar o sistema de delivery em várias cidades possui muitas diferenças em relação à arquitetura para apenas uma cidade.

Dividimos o fluxo de dados em dois caminhos distintos: um para as rotas transacionais (pedidos, cadastros) de clientes genéricos e outro para as rotas de telemetria (rastreio de posição do entregador). 

O caminho dos clientes genéricos é composto por um Application Load Balancer (ALB) que distribui as requisições dos usuários para um cluster Amazon EKS, que contém os namespaces do administrador e das cidades e os deployments dos serviços de clientes, de entregadores, de restaurantes, de pedidos e de correspondêcia de pedidos para os entregadores, juntamente com Auto Scaling para gerenciar a capacidade de execução. A persistência de dados é realizada por um banco relacional Amazon RDS (PostgreSQL) para as operações transacionais para cada cidade, enquanto a telemetria de entregadores é armazenada em uma tabela NoSQL do Amazon DynamoDB particionado para cada cidade. Os grafos viários são pré-processados e armazenados em buckets Amazon S3. Por fim, os logs e métricas são coletados utilizando o Amazon CloudWatch, garantindo monitoramento e observabilidade contínuos do serviço. 

Já o segundo caminho é constituído de uma requisição do entregador para o IOT Core (através do protocolo MQTT) para uma fila SQS, que é consumida constantemente por em ECS e armazenada no DynamoDB.

Por fim, para a camada analítica do administrador, optamos por armazenar os dados em uma fila de prioridade FIFO, utilizando o Amazon SQS. Para processar agrupar os dados em batches, usamos o Kinesis Firehose e jogamos tais dados processados em um bucket do Amazon S3. Seguindo, usamos o AWS Glue para fazer o processo de ETL e usamos o Athena para consultas SQL automatizadas, gerarando insights sobre o desempenho do delivery por meio de um dashboard.

Tal arquitetura foi projetada para atender a requisitos funcionais rigorosos, como latência máxima de 500ms no percentil 95 (P95) sob carga de até 200 pedidos por segundo, e requisitos não-funcionais relacionados à escalabilidade, resiliência e segurança. Abaixo se encontra um diagrama de alto nível da arquitetura utilizada:

#align(center)[
  #image("diagrams/Diagrama Dijksfood v2.svg")
]

= Fluxo de dados atual

A arquitetura foi projetada para garantir separação de responsabilidades, alta disponibilidade e resiliência a picos de tráfego em diferentes cidades:

== Clientes gerais
1. O *Application Load Balancer (ALB)* recebe o tráfego dos clientes e distribui as requisições HTTP de forma balanceada para cada serviço de cada cidade.
2. O *Amazon EKS (Kubernetes)* hospeda, em um cluster, os namespaces de cada cidade e os serviços de clientes, pedidos, restaurantes, entregadores e matching.
3. *Serviços:* cada serviço é uma API separada, implementada em *FastAPI*, que se comunica com o banco relacional *Amazon RDS (PostgreSQL)* de cada cidade, garantindo a persistência atômica das entidades.
4. *RDS, DynamoDB e S3:* A posição do entregador é desviada para uma tabela NoSQL no *Amazon DynamoDB*, evitando gargalos de I/O no banco relacional, enquanto os dados transacionais (pedidos, restaurantes, clientes) são armazenados no RDS de cada cidade. Além disso, os grafos viários pré-processados são armazenados no *Amazon S3* para inicialização rápida das instâncias.

== Entregadores

1. O *IoT Core* recebe o tráfego das requisições MQTT de forma balanceada dos entregadores.
2. O *Amazon SQS* armazena as requisições de telemetria dos entregadores, garantindo a entrega confiável das mensagens.
3. *Amazon ECS:* consome constantemente as mensagens da fila SQS e atualiza a posição do entregador no *Amazon DynamoDB*.
4. *DynamoDB:* armazena a posição do entregador, permitindo consultas rápidas e escaláveis sem impactar o banco relacional.

== Camada analítica

1. O *Amazon SQS* recebe o tráfego da Internet e distribui as requisições HTTP de forma balanceada.
2. O *Amazon Kinesis Firehose* hospeda os contêineres da aplicação (FastAPI), isolados em instâncias independentes.
3. *Amazon S3:* A aplicação se comunica com um banco de dados relacional *Amazon RDS (PostgreSQL)* configurado em Multi-AZ para garantir a persistência atômica das entidades.
4. *AWS Glue:* A posição do entregador é desviada para uma tabela NoSQL no *Amazon DynamoDB*, evitando gargalos de I/O no banco relacional.
5. *Amazon Athena:* A posição do entregador é desviada para uma tabela NoSQL no *Amazon DynamoDB*, evitando gargalos de I/O no banco relacional.
6. *Dashboard:* A posição do entregador é desviada para uma tabela NoSQL no *Amazon DynamoDB*, evitando gargalos de I/O no banco relacional.

= Decisões de Projeto e Cumprimento de Requisitos

== Modelagem de Dados e Telemetria (RDS vs. DynamoDB)
- *Requisito:* O projeto exige consistência transacional na criação de pedidos, mas suporta telemetria de entregadores a cada $100$ms.
- *Alternativa Considerada:* Utilizar exclusivamente um RDS PostgreSQL para todas as operações.
- *Mudança de escolha:* Resolvemos trocar para uma persistência fazendo o uso de dois bancos (RDS para cada cidade + DynamoDB).
- *Justificativa:* Operações de rastreamento de posição exigem alta vazão de escrita. No cenário de evento especial ($200$ pedidos/segundo com atualizações a cada $100$ms para cada cidade), um banco relacional sofreria forte contenção de escritas ao mesmo tempo. O DynamoDB absorve essa carga isoladamente com latência previsível, impedindo que a saturação da telemetria degrade a leitura de dados transacionais pelos usuários e administradores, portanto a melhor escola seria integrar dois bancos de dados.

== Computação Serverless vs. Instâncias Gerenciadas (ECS Fargate vs. EKS)
- *Requisito*: O serviço deve suportar escalabilidade horizontal e apresentar tolerância a falhas em instâncias de computação, garantindo alta disponibilidade e resiliência da aplicação.
- *Alternativa considerada*: Em vez de provisionar instâncias Amazon EC2 gerenciadas por um Auto Scaling Group, foi avaliada a utilização do Amazon ECS no modo AWS Fargate, permitindo a execução de containers sem a necessidade de gerenciar servidores subjacentes.
- *Opção escolhida*: Utilização do Amazon EKS, com isolamento lógico por meio de namespaces dedicados para cada cidade, além de um namespace exclusivo para o módulo administrativo.
- *Justificativa*: O Amazon EKS oferece abstração da camada de sistema operacional, reduzindo a sobrecarga operacional associada ao gerenciamento de AMIs, atualizações e aplicação de patches. Sua arquitetura baseada em Kubernetes proporciona escalabilidade horizontal eficiente, permitindo resposta rápida a variações de carga ao longo do dia. Além disso, a adoção do EKS oferece maior controle sobre a orquestração de workloads, maior flexibilidade na alocação de recursos e melhor interoperabilidade com ambientes multi-cloud e integrações externas, como serviços hospedados no Microsoft Azure.

== Gestão de Inicialização e Cálculos de Rota
- *Requisito:* O algoritmo deve calcular as rotas utilizando caminhos mínimos sobre a rede real sem travar a API.
- *Alternativa Considerada:* O contêiner realizar o download em tempo real via API externa do OpenStreetMap.
- *Opção Escolhida:* Cache dos grafos viários no Amazon S3 e implementação nativa do Algoritmo de Dijkstra.
- *Justificativa:* O download via OSMnx pode levar minutos, o que faria o Load Balancer identificar a nova instância ECS como defeituosa e encerrá-la. Ao criar um cache de backup no S3, o contêiner inicializa o grafo em disco em poucos segundos, permitindo que a API atenda os pedidos atômicos sem impacto de latência.

== Divisão das rotas
- *Requisitos:* O projeto exige consistência transacional na criação de pedidos, mas suporta telemetria de entregadores a cada $100$ms e O serviço deve escalar horizontalmente e tolerar falhas de instâncias de computação.
- *Alternativa Considerada:* Colocar todas as rotas (clientes, entregadores, restaurantes, pedidos e matching) em um único serviço.
- *Opção Escolhida:* Dividir as rotas em dois serviços distintos: um para clientes, restaurantes e pedidos, e outro exclusivamente para a telemetria de entregadores.
- *Justificativa:* A divisão das rotas em serviços distintos permite otimizar a escalabilidade e a resiliência de cada componente. O serviço de telemetria de entregadores pode ser dimensionado independentemente para lidar com a alta frequência de atualizações, enquanto o serviço de clientes, restaurantes e pedidos pode ser otimizado para garantir a consistência transacional necessária. Essa abordagem também facilita a manutenção e a evolução futura do sistema, permitindo que cada serviço evolua de forma independente conforme as necessidades do negócio.

== Utilização da arquitetura PubSub para telemetria de entregadores
- *Requisito:* O serviço deve escalar horizontalmente e tolerar falhas de instâncias de computação.
- *Alternativa Considerada:* O serviço de telemetria de entregadores poderia ser implementado como um serviço síncrono, onde os entregadores enviariam suas atualizações de posição diretamente para a API, que processaria as informações em tempo real.
- *Opção Escolhida:* Implementação de uma arquitetura PubSub utilizando o Amazon SQS para a telemetria de entregadores.
- *Justificativa:* A arquitetura PubSub permite desacoplar a produção e o consumo de mensagens, proporcionando maior escalabilidade e resiliência. O Amazon SQS oferece uma solução de fila gerenciada que garante a entrega confiável das mensagens, mesmo em cenários de alta carga. Ao utilizar o SQS, o serviço de telemetria pode processar as atualizações de posição dos entregadores de forma assíncrona, evitando sobrecarga na API e permitindo que o sistema escale horizontalmente para lidar com picos de tráfego sem comprometer a performance.


== Refatoração da Infraestrutura de Python para Terraform
- *Opção escolhida*: Refatoração do processo de provisionamento de infraestrutura, anteriormente implementado por meio de scripts em Python, para uma abordagem baseada em Terraform, adotando o paradigma de Infrastructure as Code (IaC).
- *Justificativa*: A adoção do Terraform proporciona uma definição declarativa da infraestrutura, tornando o código mais legível, modular e de fácil manutenção. Diferentemente da implementação imperativa em Python, em que a lógica de criação e atualização de recursos precisa ser explicitamente programada, o Terraform permite descrever apenas o estado desejado da infraestrutura, delegando à ferramenta a responsabilidade de calcular e aplicar as mudanças necessárias. Além disso, o uso de arquivos de configuração versionáveis facilita auditoria, reprodutibilidade e colaboração entre equipes. Outro benefício relevante é o gerenciamento de estado (state management), que possibilita rastrear os recursos provisionados e minimizar inconsistências entre ambientes, reduzindo a chance de drift de configuração e simplificando futuras evoluções da arquitetura.

== Aquecimento preventivo (Pre-warming) para Auto Scaling
- *Requisito:* O serviço deve escalar horizontalmente e tolerar falhas de instâncias de computação.
- *Alternativa Considerada:* Configurar o Auto Scaling para responder reativamente a picos de tráfego, permitindo que novas instâncias sejam provisionadas automaticamente quando a carga ultrapassar um determinado limiar.
- *Opção escolhida:* Implementação de estratégias preventivas de Pre-warming, provisionando antecipadamente as tasks necessárias para suportar a carga inicial sem degradação do serviço.
- *Justificativa:* O Auto Scaling é projetado para responder a variações de carga ao longo do tempo, mas pode levar alguns minutos para provisionar novas instâncias em resposta a picos repentinos de tráfego. Em cenários de estresse intenso e de curta duração, como os testes realizados, o Auto Scaling pode não ser capaz de reagir rapidamente o suficiente para evitar degradação do serviço. Ao adotar estratégias de Pre-warming, é possível garantir que as instâncias necessárias estejam prontas para lidar com a carga inicial, proporcionando uma experiência mais consistente e evitando falhas durante picos de tráfego inesperados. Essa abordagem é especialmente importante para garantir a disponibilidade e a performance do serviço durante eventos de alta demanda, onde a latência e a confiabilidade são críticas para a satisfação do cliente.

== Segurança e Isolamento de Rede (Security Groups)
- *Requisito:* Os bancos de dados não devem estar expostos publicamente, e a comunicação deve ser restrita e controlada.
- *Decisão:* Implementação de Security Groups em cascata.
- *Justificativa:* O Application Load Balancer atua como o único ponto de entrada acessível via Internet. Os contêineres ECS aceitam tráfego exclusivamente originado pelo Security Group do ALB. Da mesma forma, a instância do RDS PostgreSQL foi configurada para não possuir IP público (`PubliclyAccessible=False`) e seu Security Group aceita conexões apenas do Security Group do ECS na porta 5432. Esse isolamento mitiga vetores de ataque externos direto à camada de dados.

= Validação dos Requisitos Funcionais

A API REST implementada atende estritamente às regras de negócio mapeadas:
- *Cadastros e Validações:* Restrições de chaves estrangeiras, `CheckConstraints` (preços não negativos) e o controle de bloqueio de entregadores ocupados foram implementados.
- *Máquina de Estados de Entrega:* O fluxo `CONFIRMED -> PREPARING -> READY_FOR_PICKUP -> PICKED_UP -> IN_TRANSIT -> DELIVERED` possui transições blindadas em código, retornando erro `409 Conflict` para saltos inválidos.
- *Atribuição de Entregador:* A alocação ocorre utilizando coordenadas geográficas mapeadas em arestas do OSMnx para determinar a distância real do entregador em relação ao restaurante.

= Resultados Experimentais de Carga

------------------

= Desafios Encontrados e Soluções

Durante a fase de implantação e testes de estresse, dois desafios arquiteturais se destacaram, exigindo adaptações na infraestrutura como código (IaC):

1. *Configuração e Deploy*: Enfrentamos desafios significativos na refatoração da infraestrutura para integração com o Terraform, especialmente na transição de configurações previamente definidas em código para uma abordagem declarativa de Infrastructure as Code. Além disso, a configuração do ambiente baseado em Kubernetes — incluindo definição de pods, deployments e ajuste do número de workers — exigiu diversas iterações para garantir a orquestração eficiente dos microsserviços de cada cidade, preservando isolamento lógico e uso adequado dos recursos computacionais.
2. *Refatoração das Rotas*: A adaptação das rotas das APIs para um cenário multi-cidade trouxe desafios relacionados ao roteamento e à distribuição eficiente das requisições. Foi necessário revisar a estrutura de endpoints e a lógica de encaminhamento para melhorar, ainda que modestamente, a atuação do AWS Elastic Load Balancing (Load Balancer) e da fila Amazon SQS, reduzindo gargalos e melhorando o balanceamento entre os serviços responsáveis pelo processamento assíncrono.
3. *Escalabilidade*: O principal desafio técnico esteve na configuração da escalabilidade automática dentro do cluster Kubernetes, especialmente para lidar com cenários de alta volumetria de requisições e falhas parciais de serviços. Foi necessário ajustar políticas de autoscaling, limites de recursos e estratégias de recuperação para garantir resiliência do sistema. O objetivo central foi assegurar que, mesmo sob picos de carga ou indisponibilidade de componentes, a aplicação mantivesse latência inferior a 500 ms no percentil de 95%, atendendo aos requisitos de desempenho estabelecidos.
4. *Alinhamento de Chaves no DynamoDB*: Houve um desacoplamento entre o design da aplicação (`courier_id` como Partition Key numérico) e o script de criação da tabela. A divergência causava falhas no SDK Boto3 ao injetar eventos em alta frequência. A infraestrutura foi refatorada para refletir exatamente os tipos (`N` e `S`) esperados pela API, além de aplicarmos o cast (`Decimal`) para compatibilizar os tipos `float` do Python com a exigência estrita do DynamoDB.

= Modelo de Custos (Região us-east-1)

A tabela abaixo projeta os custos mensais estimados (em USD) operando ininterruptamente, demonstrando a elasticidade de custos entre o dimensionamento para a operação base e o auto-scaling em picos estressantes.

Dividimos os custos em duas categorias: "Operação Normal", que representa o custo mensal para manter a infraestrutura operando com uma carga média de 50 requisições por segundo, e "Evento Especial", que representa o custo mensal durante um pico de tráfego de 200 requisições por segundo.

Considere $P$ como sendo o número de cidades polo (cidades grandes como São Paulo e Rio de Janeiro) e $C$ como o número de cidades satélites (cidades menores). O custo total é calculado como:

#align(center)[
  #table(
    columns: (auto, auto, auto),
    inset: 10pt,
    align: center,
    [*Recurso AWS*], [*Operação Normal (Mensal)*], [*Evento Especial (Mensal)*],
    [*Application Load Balancer* (1 segundo por conexão e e regra por solicitação) aaaaaaaaaaaaaaa], [\$ *28.11* (1 TB/mês, 50 novas conexões e 50 solicitações por segundo)], [\$ *221.23* (25 TB/mês, 200 novas conexões e 200 solicitações por segundo)],
    [*ECS Fargate*], [\$ *144.16* (2 Tasks, 4vCPU, 8GB)], [\$ *864.96* (6 Tasks, 8vCPU, 16GB)],
    [*RDS PostgreSQL* (db.t3.micro Multi-AZ, on-demand, com Proxy e com 20GB de armazenamento e de backup) aaaaaaaaaa], [\$ *54.68*], [\$ *54.68*],
    [*DynamoDB* (Standard com 200 bytes por item)], [\$ *140.34* (200GB de armazenamento e 50 gravações e 50 leituras por segundo)], [\$ *617.35* (1TB de armazenamento e 200 gravações e 200 leituras por segundo)],
    [*Amazon S3* (Standard e com 20GB de armazenamento)], [\$ *0.23 x ($P + C$)*], [\$ *0.23 x ($P + C$)*],
    [*Amazon EKS*],[\$ *73.00* (suporte padrão)],[\$ *73.00* (suporte padrão)],
    [*IoT Core* (1 dispositivo MQTT e conectividade sem pausa)],[\$ *10.00* (10000000 de mensagens/mês)],[\$ *120.00* (120000000 de mensagens/mês)],
    [*Amazon SQS* (38.88 milhões de solicitações/mês)],[\$ *19.44* x ($P + C$)],[\$ *19.44* x ($P + C$)],
    [*Kinesis Firehose* (conexão direta e tamanho máximo de 2kB por registro)],[\$ *23.19*],[\$ *92.77*],
    [*AWS Glue* (10 DPUs e 100 horas/mês de execução direta)],[\$ *440.00*],[\$ *440.00*],
    [*Amazon Athena* (100 consultas por dia e até 2GB de dados por consulta)],[\$ *29.71*],[\$ *29.71*],
    [*Custo Total Estimado*], [*\$ 317.77*], [*\$ 1190.38*],
  )
]

*Nota:* O valor constante no RDS se deve ao provisionamento fixo com `MultiAZ=True`. A alta disponibilidade sacrifica a redução de custo base para garantir sobrevivência à queda de zonas, conforme o requisito do projeto.


= Considerações Finais

Ao longo do desenvolvimento e da validação do DijkFood, a arquitetura evoluiu significativamente de uma solução inicialmente centrada em serviços isolados para uma plataforma distribuída baseada em microsserviços orquestrados por Kubernetes no Amazon EKS. Essa transição permitiu atender de forma mais robusta aos requisitos de escalabilidade, resiliência e isolamento lógico necessários para suportar operações simultâneas em múltiplas cidades.

A adoção do Amazon EKS, combinada com a segmentação da infraestrutura em namespaces dedicados para cada cidade e para o módulo administrativo, proporcionou maior flexibilidade na alocação de recursos e melhor controle operacional sobre os serviços. Essa decisão arquitetural permitiu escalar componentes de maneira independente, evitando que o aumento de carga em uma cidade impactasse diretamente as demais. Além disso, o desacoplamento entre rotas transacionais e fluxos de telemetria, com uso de Amazon SQS e DynamoDB, reduziu contenções de I/O e aumentou a capacidade de absorção de picos de carga.

A migração do provisionamento manual em Python para uma abordagem declarativa com Terraform também representou um avanço importante na maturidade da infraestrutura. Apesar dos benefícios em reprodutibilidade, modularidade e automação, essa refatoração introduziu desafios significativos de configuração, especialmente na integração entre recursos da AWS e componentes do cluster Kubernetes, como pods, deployments, políticas de escalabilidade e gerenciamento de workers.

Entre os principais desafios técnicos enfrentados, destacou-se a configuração da escalabilidade automática no Kubernetes. Ajustar corretamente métricas de CPU, limites de memória, réplicas mínimas e máximas, além das políticas de Horizontal Pod Autoscaler (HPA), mostrou-se mais complexo do que inicialmente previsto. Em cenários de alta carga — particularmente sob volumes próximos de 200 requisições por segundo — observou-se que o escalonamento reativo nem sempre ocorria com rapidez suficiente para absorver picos abruptos, especialmente devido à latência inerente na coleta e agregação de métricas.

Outro aprendizado relevante foi que, em sistemas distribuídos de baixa latência, a escalabilidade não depende apenas da capacidade de provisionar novas instâncias, mas também da eficiência do roteamento interno, do balanceamento de carga e da distribuição assíncrona de eventos. A refatoração das rotas para suportar múltiplas cidades evidenciou que pequenas decisões de roteamento podem impactar significativamente a atuação do Load Balancer e o throughput de filas assíncronas como o SQS.

Por fim, o projeto demonstrou que arquiteturas modernas baseadas em Kubernetes oferecem grande poder de abstração e escalabilidade, mas introduzem complexidades operacionais consideráveis. A principal lição obtida foi que sistemas distribuídos em larga escala exigem não apenas recursos elásticos, mas também planejamento cuidadoso de observabilidade, políticas de recuperação e estratégias preventivas de capacidade. Para cenários com picos repentinos de tráfego, abordagens híbridas — combinando autoscaling, pre-warming e particionamento inteligente de workloads — mostraram-se mais adequadas para garantir o cumprimento do requisito de manter latência inferior a 500 ms no percentil 95, mesmo diante de falhas parciais ou aumentos súbitos de demanda.