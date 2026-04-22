# Sistema de Delivery (DijkFood)
Repositório direcionado a uma simulção de um sistema de delivery utilizando recursos da nuvem da AWS.

O seguinte projeto foi parte da avaliação do curso **Computação na Nuvem**, lecionado pelo professor Thiago Pinheiro de Araújo e oferecido pela Fundação Getulio Vargas.

## Introdução
O objetivo é projetar, implementar e implantar a plataforma DijkFood, um serviço de delivery de comida capaz de calcular rotas sobre o grafo viário de São Paulo, registrar o ciclo de vida completo de cada pedido e atender aos requisitos disponibilidade, escalabilidade automática e otimização de custo.

Dentro do mundo simulado, existem clientes que fazem pedidos, restaurantes que realizam os pedidos dos clientes, entregadores que vão até as casas dos clientes com o pedido e administradores que são capazes de criar, atualizar e deletar restaurantes, pedidos e clientes.

O serviço é fornecido através de uma API REST, junto com dois bancos de dados (PostgreSQL para dados estruturados e DynamoDB para dados não estruturados). Tais serviços serão construídos na AWS, populados e destruídos logo em seguida.

## Relatório
O relatório completo do projeto pode ser encontrado em *docs/report.pdf*.

## Árvore do repositório
```bash
├───database
│       connection.py
│       create_graph.py
│       dynamo_table.py
│       models.py
│       __init__.py
│       
├───docs
│   │   report.pdf
│   │   
│   ├───diagrams
│   │       Diagrama Dijksfood.png
│   │       not_relational_schema.json
│   │       relational_schema.png
│   │       
│   └───images
│           Resultados 10ps.jpeg
│       
├───infranova
│      compute.py
│      config.py
│      databases.py
│      network.py
│           
├───routes
│       courier.py
│       delivery.py
│       item.py
│       kitchen.py
│       order.py
│       restaurant.py
│       user.py
│       __init__.py
│       
├───test
│   └───e2e
│           conftest.py
│           test_routes_e2e.py
│           
├───utils
│       aws_credentials.py
│       cheapest_path.py
│       __init__.py
│
├───deploy.py
├───destroy.py
├───docker-compose.yml
├───env-template
├───main.py
├───README.md
├───simulator.py
```

## Configurando o ambiente
Execute o seguinte passo a passo no seu terminal
```bash
# Clonando o projeto
git clone https://github.com/Os-Estudiosos/delivery-system.git # HTML
ou
git clone git@github.com:Os-Estudiosos/delivery-system.git # SSH

# Entrando do repositório
cd delivery-system

# Instalando o uv (Powershell)
irm https://astral.sh/uv/install.ps1 | iex
$env:Path += ";$HOME\.local\bin"

# Instalando o uv (Linux ou MacOS)
curl -LsSf https://astral.sh/uv/install.sh | sh
ou
wget -qO- https://astral.sh/uv/install.sh | sh
ou
curl -LsSf https://astral.sh/uv/0.11.7/install.sh | sh

# Criando um ambiente virtual
uv venv

# Instalando as dependências
uv sync
```

Agora, crie um arquivo **.env** na raiz do repositório, copie e cole o conteúdo do arquivo **env-template** e preencha conforme necessário.

Para pegar as credenciais da AWS, vá em Learner Lab, clique em AWS Details, clique em AWS Cli, copie e cole o conteúdo em **~/.aws/credentials** (ou, se preferir, rode **aws configure** e siga o passo a passo). Além disso, coloque as credenciais no .env.

Caso queira visualizar os containers no docker, abra o aplicativo Docker Desktop, vá na pasta do projeto e rode o seguinte comando:

```bash
docker compose up -d
```

## Executando o projeto
Após todos os passos anteriores, rode o seguinte comando para realizar o deploy do projeto:
```bash
python deploy.py
```