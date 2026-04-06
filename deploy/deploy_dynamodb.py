"""
deploy_dynamodb.py — Cria e destrói as tabelas DynamoDB do DijkFood.

Tabelas gerenciadas:
  - dijkfood-courier-positions : posições GPS dos entregadores (100ms)
      PK: courier_id (S)  |  SK: timestamp (S)
  - dijkfood-delivery-events   : histórico de eventos de entrega
      PK: delivery_id (S)  |  SK: timestamp (S)

Billing: PAY_PER_REQUEST (sem capacidade provisionada — mais barato para carga variável).

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_dynamodb
"""

import boto3

from .config import PROJECT, REGION, tags

_TABLES = [
    {
        "name":       f"{PROJECT}-courier-positions",
        "pk":         "courier_id",
        "sk":         "timestamp",
        "description": "Posições GPS dos entregadores",
    },
    {
        "name":       f"{PROJECT}-delivery-events",
        "pk":         "delivery_id",
        "sk":         "timestamp",
        "description": "Histórico de eventos de entrega",
    },
]


def _ddb():
    return boto3.client("dynamodb", region_name=REGION)


def _log(msg: str) -> None:
    print(f"[dynamodb] {msg}")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create(ctx: dict) -> dict:
    """Cria as tabelas DynamoDB e aguarda ficarem ativas."""
    ddb        = _ddb()
    table_names = []

    for table in _TABLES:
        _create_table(ddb, table)
        table_names.append(table["name"])

    for name in table_names:
        _wait_active(ddb, name)

    _log("pronto.")
    return {"dynamodb_tables": table_names}


def _create_table(ddb, table: dict) -> None:
    try:
        ddb.create_table(
            TableName=table["name"],
            KeySchema=[
                {"AttributeName": table["pk"], "KeyType": "HASH"},
                {"AttributeName": table["sk"], "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": table["pk"], "AttributeType": "S"},
                {"AttributeName": table["sk"], "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
            Tags=tags(table["name"]),
        )
        _log(f"tabela '{table['name']}' criada.")
    except ddb.exceptions.ResourceInUseException:
        _log(f"tabela '{table['name']}' já existe, reutilizando.")


def _wait_active(ddb, table_name: str) -> None:
    _log(f"aguardando '{table_name}' ficar ativa...")
    waiter = ddb.get_waiter("table_exists")
    waiter.wait(
        TableName=table_name,
        WaiterConfig={"Delay": 5, "MaxAttempts": 12},  # até 1 min
    )


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def destroy(ctx: dict) -> None:
    """Remove todas as tabelas DynamoDB."""
    ddb = _ddb()
    for table in _TABLES:
        _delete_table(ddb, table["name"])


def _delete_table(ddb, table_name: str) -> None:
    try:
        ddb.delete_table(TableName=table_name)
        _log(f"tabela '{table_name}' deletada.")
    except ddb.exceptions.ResourceNotFoundException:
        _log(f"tabela '{table_name}' não encontrada, nada a deletar.")
    except Exception as e:
        _log(f"aviso ao deletar '{table_name}': {e}")


# ---------------------------------------------------------------------------
# Execução direta (teste isolado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=== Criando tabelas DynamoDB ===")
    result = create({})
    print(json.dumps(result, indent=2))

    input("\nPressione Enter para destruir as tabelas...")
    destroy(result)
