# Delivery System
Esse repositório traz uma infraestrutura kubernetes de um aplicativo de delivery idealizado para seguir a seguinte infraestrutura AWS

![Infraestrutura](images/infra.svg)

## Como rodar
Para rodar localmente e em produção, o repositório se utiliza do `terraform` para rodar containers e serviços

### Rodando localmente
Você **precisa** ter o `terraform` instalado, para tal, [clique aqui](https://developer.hashicorp.com/terraform/install#next-steps)

Em seguida, com o repositório baixado, você deve entrar na pasta `/infra/terraform`
```bash
cd infra/terraform
```

Logo após, você deve rodar o comando de inicialização do terraform (apenas uma vez)
```bash
terraform init
```

Então você deve inicializar os serviços passando o arquivo de variáveis correto (local ou production)
```bash
terraform apply -var-file="environments/local.tfvars"
```

E caso você deseje destruir os serviços, basta rodar:
```bash
terraform destroy
```
