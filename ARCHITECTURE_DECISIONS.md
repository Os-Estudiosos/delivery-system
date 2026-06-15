# Registro de Decisões e Alterações Arquiteturais (Changelog)

Este documento centraliza todas as principais alterações, correções e decisões de design aplicadas ao sistema **Dijkstra Food** durante esta sessão de engenharia, com o objetivo de escalar o sistema, implementar a separação lógica e corrigir falhas de monitoramento.

---

## 1. Isolamento Lógico de Banco de Dados por Cidade
**Momento:** Início da sessão.
**Onde:** Arquivos do Terraform (`infra/terraform/aws/modules/rds/`), Arquivos de configuração de deploy (`deploy.py`), Scripts SQL de Setup/Destroy e Microserviços (`clients`, `couriers`, `orders`, `restaurants`, `matching`).

* **O que foi feito:** O sistema foi alterado para sair de uma arquitetura de banco de dados global (onde todas as cidades compartilhavam a mesma instância e tabelas através de identificadores de região) para uma arquitetura distribuída. Cada cidade agora possui o seu próprio ambiente/schema no RDS.
* **Justificativa (Por quê):** Era um requisito essencial da atividade garantir que cada cidade fosse independente. O compartilhamento do banco estava causando gargalos e timeouts severos ("QueuePool limit overflow") porque a pequena instância `t3.micro` não suportava as conexões paralelas do simulador batendo em mais de 50 requisições por segundo para múltiplas cidades simultaneamente.
* **Lógica de Decisão:** Ao isolar os bancos, garantimos alta escalabilidade horizontal por região e isolamento de falhas (se uma cidade sobrecarregar o banco, as outras não caem).

---

## 2. Correção do Pipeline de Analytics (Dashboard Vazio)
**Momento:** Metade da sessão.
**Onde:** `infra/terraform/aws/modules/analytics/main.tf` (Configuração do EventBridge Pipe).

* **O que foi feito:** Ajustou-se o `input_template` do EventBridge Pipe que transfere eventos da fila SQS para o Kinesis Firehose. O formato anterior (`<$.body>\n`) estava convertendo o payload numa string sem aspas duplas e, portanto, gerando arquivos não-JSON no S3 (ex: `{order_id:6, status:CONFIRMED}`). O template foi alterado para reconstruir ativamente o JSON: `{"order_id": <$.body.order_id>, "status": "<$.body.status>", ...}`.
* **Justificativa (Por quê):** O AWS Athena, responsável por ler o bucket S3 e alimentar o Dashboard via `JsonSerDe`, não consegue parsear objetos JSON inválidos. Isso fazia com que as queries retornassem valores `NULL` e todos os gráficos do Dashboard ficassem completamente vazios.
* **Lógica de Decisão:** Fazer o parse/extração de chaves diretamente na camada do EventBridge Pipe elimina a necessidade de criar instâncias Lambda intermediárias de transformação de dados, economizando custos e reduzindo a latência do pipeline de dados.

---

## 3. Reprocessamento do Data Lake (S3 Backfill)
**Momento:** Reta final da sessão.
**Onde:** Bucket S3 do Data Lake, através do script temporário `fix_s3_json.py` injetado no pod `admin`.

* **O que foi feito:** Criamos um script que baixou todos os milhares de logs históricos de load tests salvos no S3 com a formatação quebrada, aplicou uma regex estrutural convertendo-os em NDJSON válido (JSON Lines com aspas apropriadas), e fez o upload sobrescrevendo-os de volta no Data Lake.
* **Justificativa (Por quê):** O conserto do EventBridge Pipe valia apenas para *novos* eventos. Para não perder os dados já coletados pelos simuladores que rodaram exaustivamente antes, optamos por higienizar os logs existentes.
* **Lógica de Decisão:** Corrigir os arquivos in-loco foi a saída mais performática. Rodar a limpeza dentro do pod `admin` do cluster EKS permitiu o uso das roles IAM integradas via ServiceAccount, evitando a necessidade de gerenciar credenciais AWS localmente no terminal.

---

## 4. Estabilidade do Terraform e AWS Academy IAM Roles
**Momento:** Durante a re-aplicação da infraestrutura.
**Onde:** `deploy.py` e execução de variáveis de ambiente.

* **O que foi feito:** O processo de provisionamento no script foi forçado a usar e exportar persistentemente as variáveis `TF_VAR_eks_cluster_role_arn` e `TF_VAR_eks_node_role_arn` apontando para a `LabRole` da AWS Academy.
* **Justificativa (Por quê):** Sem essas definições, o estado do Terraform tentava recriar os Cluster Roles (causando a temida transição do EKS Node Group para o estado `DELETING`, derrubando as APIs ativas). O AWS Academy proíbe rigorosamente a criação de novas Roles IAM (falta de permissões de *iam:CreateRole*).
* **Lógica de Decisão:** Garantir o uso imperativo da `LabRole` em qualquer chamada automática ao Terraform previne indisponibilidades drásticas não-planejadas e falhas nos deploys subsequentes do projeto.

---

**Estado Final do Sistema:**
* Instâncias desacopladas e escaláveis prontas para suportar altíssimas requisições através do *load simulator*.
* Dashboard Analítico recebendo fluxos perfeitamente compatíveis com Athena.
* Pipeline automatizado rodando com `deploy.py` robusto.
