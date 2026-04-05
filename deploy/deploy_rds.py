"""
deploy_rds.py — Cria e destrói a instância RDS PostgreSQL do DijkFood.

Dependências de ctx: subnet_ids, rds_sg_id

Multi-AZ está desabilitado para simplicidade e custo.
Para habilitar em produção: altere MULTI_AZ = True.

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_rds
"""

import boto3

from .config import PROJECT, REGION, tags

_DB_IDENTIFIER  = f"{PROJECT}-db"
_DB_NAME        = "dijkfood"
_DB_USER        = "postgres"
_DB_PASSWORD    = "postgres"
_DB_PORT        = 5432
_INSTANCE_CLASS = "db.t3.micro"
_ENGINE         = "postgres"
_ENGINE_VERSION = "17.4"
_SUBNET_GROUP   = f"{PROJECT}-db-subnet-group"
MULTI_AZ        = False


def _rds():
    return boto3.client("rds", region_name=REGION)


def _log(msg: str) -> None:
    print(f"[rds] {msg}")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create(ctx: dict) -> dict:
    """Cria subnet group e instância RDS. Aguarda ficar disponível."""
    rds = _rds()

    _create_subnet_group(rds, ctx["subnet_ids"])
    _create_instance(rds, ctx["rds_sg_id"])
    endpoint = _wait_available(rds)

    _log("pronto.")
    return {
        "db_host":     endpoint,
        "db_port":     _DB_PORT,
        "db_name":     _DB_NAME,
        "db_user":     _DB_USER,
        "db_password": _DB_PASSWORD,
    }


def _create_subnet_group(rds, subnet_ids: list[str]) -> None:
    try:
        rds.create_db_subnet_group(
            DBSubnetGroupName=_SUBNET_GROUP,
            DBSubnetGroupDescription=f"Subnet group para {PROJECT}",
            SubnetIds=subnet_ids,
            Tags=tags(_SUBNET_GROUP),
        )
        _log(f"subnet group '{_SUBNET_GROUP}' criado.")
    except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
        _log(f"subnet group '{_SUBNET_GROUP}' já existe, reutilizando.")


def _create_instance(rds, rds_sg_id: str) -> None:
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=_DB_IDENTIFIER,
            DBName=_DB_NAME,
            DBInstanceClass=_INSTANCE_CLASS,
            Engine=_ENGINE,
            EngineVersion=_ENGINE_VERSION,
            MasterUsername=_DB_USER,
            MasterUserPassword=_DB_PASSWORD,
            VpcSecurityGroupIds=[rds_sg_id],
            DBSubnetGroupName=_SUBNET_GROUP,
            MultiAZ=MULTI_AZ,
            PubliclyAccessible=False,
            AllocatedStorage=20,
            StorageType="gp2",
            Tags=tags(_DB_IDENTIFIER),
        )
        _log(f"instância '{_DB_IDENTIFIER}' criando (isso leva ~5 min)...")
    except rds.exceptions.DBInstanceAlreadyExistsFault:
        _log(f"instância '{_DB_IDENTIFIER}' já existe, reutilizando.")


def _wait_available(rds) -> str:
    _log("aguardando instância ficar disponível...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=_DB_IDENTIFIER,
        WaiterConfig={"Delay": 20, "MaxAttempts": 60},  # até 20 min
    )
    instance = rds.describe_db_instances(DBInstanceIdentifier=_DB_IDENTIFIER)
    endpoint = instance["DBInstances"][0]["Endpoint"]["Address"]
    _log(f"disponível em: {endpoint}")
    return endpoint


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def destroy(ctx: dict) -> None:
    """Remove a instância RDS e o subnet group."""
    rds = _rds()
    _delete_instance(rds)
    _delete_subnet_group(rds)


def _delete_instance(rds) -> None:
    try:
        rds.delete_db_instance(
            DBInstanceIdentifier=_DB_IDENTIFIER,
            SkipFinalSnapshot=True,
            DeleteAutomatedBackups=True,
        )
        _log(f"instância '{_DB_IDENTIFIER}' deletando (isso leva ~3 min)...")
        waiter = rds.get_waiter("db_instance_deleted")
        waiter.wait(
            DBInstanceIdentifier=_DB_IDENTIFIER,
            WaiterConfig={"Delay": 20, "MaxAttempts": 60},
        )
        _log("instância deletada.")
    except rds.exceptions.DBInstanceNotFoundFault:
        _log("instância não encontrada, nada a deletar.")
    except Exception as e:
        _log(f"aviso ao deletar instância: {e}")


def _delete_subnet_group(rds) -> None:
    try:
        rds.delete_db_subnet_group(DBSubnetGroupName=_SUBNET_GROUP)
        _log(f"subnet group '{_SUBNET_GROUP}' deletado.")
    except rds.exceptions.DBSubnetGroupNotFoundFault:
        _log("subnet group não encontrado, nada a deletar.")
    except Exception as e:
        _log(f"aviso ao deletar subnet group: {e}")


# ---------------------------------------------------------------------------
# Execução direta (teste isolado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    # ctx mínimo necessário para teste isolado
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}])["Subnets"]
    subnet_ids = [s["SubnetId"] for s in subnets]

    sgs = ec2.describe_security_groups(Filters=[
        {"Name": "group-name", "Values": [f"{PROJECT}-rds-sg"]},
        {"Name": "vpc-id",     "Values": [vpc["VpcId"]]},
    ])["SecurityGroups"]
    rds_sg_id = sgs[0]["GroupId"] if sgs else None

    mock_ctx = {"subnet_ids": subnet_ids, "rds_sg_id": rds_sg_id}

    print("=== Criando RDS ===")
    result = create(mock_ctx)
    print(json.dumps(result, indent=2))

    input("\nPressione Enter para destruir a instância...")
    destroy(result)
