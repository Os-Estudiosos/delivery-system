"""
deploy_vpc.py — Descobre a rede padrão AWS Academy e cria os security groups.

A VPC padrão, subnets e Internet Gateway já existem em qualquer conta Academy —
não criamos nem destruímos esses recursos. Gerenciamos apenas os security groups.

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_vpc
"""

import boto3

from .config import APP_PORT, PROJECT, REGION, tags


def _ec2():
    return boto3.client("ec2", region_name=REGION)


def _log(msg: str) -> None:
    print(f"[vpc] {msg}")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create(ctx: dict) -> dict:
    """Descobre VPC/subnets padrão e cria os security groups necessários."""
    ec2 = _ec2()

    vpc_id, subnet_ids = _fetch_default_vpc(ec2)
    alb_sg_id, ecs_sg_id, rds_sg_id = _create_security_groups(ec2, vpc_id)

    _log("pronto.")
    return {
        "vpc_id":      vpc_id,
        "subnet_ids":  subnet_ids,
        "alb_sg_id":   alb_sg_id,
        "ecs_sg_id":   ecs_sg_id,
        "rds_sg_id":   rds_sg_id,
    }


def _fetch_default_vpc(ec2) -> tuple[str, list[str]]:
    vpc = ec2.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )["Vpcs"][0]
    vpc_id = vpc["VpcId"]
    _log(f"VPC padrão encontrada: {vpc_id}")

    subnets = ec2.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )["Subnets"]
    subnet_ids = [s["SubnetId"] for s in sorted(subnets, key=lambda s: s["AvailabilityZone"])]
    _log(f"{len(subnet_ids)} subnets encontradas: {subnet_ids}")

    return vpc_id, subnet_ids


def _create_security_groups(ec2, vpc_id: str) -> tuple[str, str, str]:
    # ALB — aceita HTTP externo
    alb_sg_id = _make_sg(ec2, vpc_id, "alb-sg", "ALB DijkFood")
    _authorize(ec2, alb_sg_id, [
        {"IpProtocol": "tcp", "FromPort": 80,  "ToPort": 80,  "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
    ])
    _log(f"SG ALB: {alb_sg_id}")

    # ECS — aceita tráfego apenas do ALB
    ecs_sg_id = _make_sg(ec2, vpc_id, "ecs-sg", "ECS tasks DijkFood")
    _authorize(ec2, ecs_sg_id, [{
        "IpProtocol": "tcp",
        "FromPort": APP_PORT,
        "ToPort":   APP_PORT,
        "UserIdGroupPairs": [{"GroupId": alb_sg_id}],
    }])
    _log(f"SG ECS: {ecs_sg_id}")

    # RDS — aceita PostgreSQL apenas das tasks ECS
    rds_sg_id = _make_sg(ec2, vpc_id, "rds-sg", "RDS DijkFood")
    _authorize(ec2, rds_sg_id, [{
        "IpProtocol": "tcp",
        "FromPort": 5432,
        "ToPort":   5432,
        "UserIdGroupPairs": [{"GroupId": ecs_sg_id}],
    }])
    _log(f"SG RDS: {rds_sg_id}")

    return alb_sg_id, ecs_sg_id, rds_sg_id


def _authorize(ec2, sg_id: str, permissions: list) -> None:
    try:
        ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=permissions)
    except ec2.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
            pass  # regra já existe, ok
        else:
            raise


def _make_sg(ec2, vpc_id: str, suffix: str, description: str) -> str:
    name = f"{PROJECT}-{suffix}"
    existing = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [name]},
            {"Name": "vpc-id",     "Values": [vpc_id]},
        ]
    )["SecurityGroups"]
    if existing:
        _log(f"SG '{name}' já existe, reutilizando: {existing[0]['GroupId']}")
        return existing[0]["GroupId"]
    resp  = ec2.create_security_group(GroupName=name, Description=description, VpcId=vpc_id)
    sg_id = resp["GroupId"]
    ec2.create_tags(Resources=[sg_id], Tags=tags(name))
    return sg_id


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def destroy(ctx: dict) -> None:
    """Remove apenas os security groups criados por este módulo."""
    ec2 = _ec2()

    _revoke_cross_references(ec2, ctx)

    for key in ("rds_sg_id", "ecs_sg_id", "alb_sg_id"):
        sg_id = ctx.get(key)
        if not sg_id:
            continue
        try:
            ec2.delete_security_group(GroupId=sg_id)
            _log(f"SG deletado: {sg_id}")
        except Exception as e:
            _log(f"aviso ao deletar SG {sg_id}: {e}")


def _revoke_cross_references(ec2, ctx: dict) -> None:
    """Remove regras entre SGs para evitar DependencyViolation na deleção."""
    pairs = [
        ("rds_sg_id", "ecs_sg_id", 5432),
        ("ecs_sg_id", "alb_sg_id", APP_PORT),
    ]
    for target_key, source_key, port in pairs:
        target = ctx.get(target_key)
        source = ctx.get(source_key)
        if not (target and source):
            continue
        try:
            ec2.revoke_security_group_ingress(
                GroupId=target,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort":   port,
                    "UserIdGroupPairs": [{"GroupId": source}],
                }],
            )
        except Exception as e:
            _log(f"aviso ao revogar regra {target} ← {source}: {e}")


# ---------------------------------------------------------------------------
# Execução direta (teste isolado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=== Descobrindo VPC e criando security groups ===")
    result = create({})
    print(json.dumps(result, indent=2))

    input("\nPressione Enter para destruir os recursos criados...")
    destroy(result)
