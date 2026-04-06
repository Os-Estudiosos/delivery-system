"""
deploy_ecs.py — Cria e destrói o cluster ECS Fargate do DijkFood.

Recursos gerenciados:
  - CloudWatch Log Group
  - ECS Cluster
  - Task Definition (imagem placeholder nginx — substituir pela API real)
  - ALB + Target Group + Listener
  - ECS Service
  - Application Auto Scaling (CPU target 70%)

Dependências de ctx: subnet_ids, alb_sg_id, ecs_sg_id,
                     db_host, db_port, db_name, db_user, db_password

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_ecs
"""

import boto3

from .config import LAB_ROLE_NAME, PROJECT, REGION, tags

_CLUSTER        = f"{PROJECT}-cluster"
_TASK_FAMILY    = f"{PROJECT}-task"
_SERVICE        = f"{PROJECT}-service"
_ALB_NAME       = f"{PROJECT}-alb"
_TG_NAME        = f"{PROJECT}-tg"
_LOG_GROUP      = f"/ecs/{PROJECT}"
_PLACEHOLDER    = "nginx:latest"   # substituir pela imagem ECR quando API estiver pronta
_CONTAINER_PORT = 80               # nginx usa 80; mudar para APP_PORT quando usar API real
_CPU            = "256"
_MEMORY         = "512"
_MIN_TASKS      = 1
_MAX_TASKS      = 4
_CPU_TARGET     = 70.0


def _ecs():
    return boto3.client("ecs", region_name=REGION)

def _elbv2():
    return boto3.client("elbv2", region_name=REGION)

def _aas():
    return boto3.client("application-autoscaling", region_name=REGION)

def _logs():
    return boto3.client("logs", region_name=REGION)

def _lab_role_arn() -> str:
    iam = boto3.client("iam", region_name=REGION)
    return iam.get_role(RoleName=LAB_ROLE_NAME)["Role"]["Arn"]

def _log(msg: str) -> None:
    print(f"[ecs] {msg}")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create(ctx: dict) -> dict:
    lab_role  = _lab_role_arn()
    subnet_ids = ctx["subnet_ids"]
    alb_sg_id  = ctx["alb_sg_id"]
    ecs_sg_id  = ctx["ecs_sg_id"]

    _create_log_group()
    _create_cluster()
    task_def_arn = _register_task_definition(lab_role, ctx)
    tg_arn       = _create_target_group(ctx["vpc_id"])
    alb_arn, alb_dns = _create_alb(subnet_ids, alb_sg_id)
    _create_listener(alb_arn, tg_arn)
    _create_service(subnet_ids, ecs_sg_id, tg_arn)
    _wait_service_stable()
    _register_autoscaling()

    _log("pronto.")
    return {
        "alb_arn":      alb_arn,
        "alb_dns":      alb_dns,
        "tg_arn":       tg_arn,
        "task_def_arn": task_def_arn,
    }


def _create_log_group() -> None:
    try:
        _logs().create_log_group(logGroupName=_LOG_GROUP)
        _log(f"log group '{_LOG_GROUP}' criado.")
    except Exception:
        _log(f"log group '{_LOG_GROUP}' não criado (pode já existir ou estar indisponível). Continuando.")


def _create_cluster() -> None:
    ecs = _ecs()
    resp = ecs.create_cluster(
        clusterName=_CLUSTER,
        capacityProviders=["FARGATE"],
        tags=[{"key": "Project", "value": PROJECT}],
    )
    status = resp["cluster"]["status"]
    _log(f"cluster '{_CLUSTER}': {status}")


def _register_task_definition(lab_role: str, ctx: dict) -> str:
    ecs = _ecs()
    resp = ecs.register_task_definition(
        family=_TASK_FAMILY,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu=_CPU,
        memory=_MEMORY,
        executionRoleArn=lab_role,
        taskRoleArn=lab_role,
        containerDefinitions=[{
            "name":      PROJECT,
            "image":     _PLACEHOLDER,
            "essential": True,
            "portMappings": [{"containerPort": _CONTAINER_PORT, "protocol": "tcp"}],
            "environment": [
                {"name": "DB_HOST",     "value": ctx.get("db_host", "")},
                {"name": "DB_PORT",     "value": str(ctx.get("db_port", 5432))},
                {"name": "DB_NAME",     "value": ctx.get("db_name", "")},
                {"name": "DB_USER",     "value": ctx.get("db_user", "")},
                {"name": "DB_PASSWORD", "value": ctx.get("db_password", "")},
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group":         _LOG_GROUP,
                    "awslogs-region":        REGION,
                    "awslogs-stream-prefix": "ecs",
                    "awslogs-create-group":  "true",
                },
            },
        }],
        tags=[{"key": "Project", "value": PROJECT}],
    )
    arn = resp["taskDefinition"]["taskDefinitionArn"]
    _log(f"task definition registrada: {arn}")
    return arn


def _create_target_group(vpc_id: str) -> str:
    elb = _elbv2()
    existing = elb.describe_target_groups(Names=[_TG_NAME])["TargetGroups"] if _tg_exists() else []
    if existing:
        arn = existing[0]["TargetGroupArn"]
        _log(f"target group '{_TG_NAME}' já existe, reutilizando.")
        return arn

    resp = elb.create_target_group(
        Name=_TG_NAME,
        Protocol="HTTP",
        Port=_CONTAINER_PORT,
        VpcId=vpc_id,
        TargetType="ip",
        HealthCheckProtocol="HTTP",
        HealthCheckPath="/",
        HealthCheckIntervalSeconds=30,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=3,
        Tags=tags(_TG_NAME),
    )
    arn = resp["TargetGroups"][0]["TargetGroupArn"]
    _log(f"target group criado: {arn}")
    return arn


def _tg_exists() -> bool:
    try:
        _elbv2().describe_target_groups(Names=[_TG_NAME])
        return True
    except _elbv2().exceptions.TargetGroupNotFoundException:
        return False


def _create_alb(subnet_ids: list[str], alb_sg_id: str) -> tuple[str, str]:
    elb = _elbv2()

    existing = [a for a in elb.describe_load_balancers()["LoadBalancers"] if a["LoadBalancerName"] == _ALB_NAME]
    if existing:
        alb = existing[0]
        _log(f"ALB '{_ALB_NAME}' já existe, reutilizando.")
        return alb["LoadBalancerArn"], alb["DNSName"]

    resp = elb.create_load_balancer(
        Name=_ALB_NAME,
        Subnets=subnet_ids,
        SecurityGroups=[alb_sg_id],
        Scheme="internet-facing",
        Type="application",
        Tags=tags(_ALB_NAME),
    )
    alb = resp["LoadBalancers"][0]
    _log(f"ALB criado: {alb['DNSName']}")
    _log("aguardando ALB ficar ativo...")
    elb.get_waiter("load_balancer_available").wait(LoadBalancerArns=[alb["LoadBalancerArn"]])
    return alb["LoadBalancerArn"], alb["DNSName"]


def _create_listener(alb_arn: str, tg_arn: str) -> None:
    elb = _elbv2()
    existing = elb.describe_listeners(LoadBalancerArn=alb_arn)["Listeners"]
    if existing:
        _log("listener já existe, reutilizando.")
        return
    elb.create_listener(
        LoadBalancerArn=alb_arn,
        Protocol="HTTP",
        Port=80,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
    )
    _log("listener HTTP:80 criado.")


def _create_service(subnet_ids: list[str], ecs_sg_id: str, tg_arn: str) -> None:
    ecs = _ecs()
    existing = ecs.describe_services(cluster=_CLUSTER, services=[_SERVICE])["services"]
    if existing and existing[0]["status"] != "INACTIVE":
        _log(f"service '{_SERVICE}' já existe, reutilizando.")
        return

    ecs.create_service(
        cluster=_CLUSTER,
        serviceName=_SERVICE,
        taskDefinition=_TASK_FAMILY,
        launchType="FARGATE",
        desiredCount=_MIN_TASKS,
        networkConfiguration={"awsvpcConfiguration": {
            "subnets":        subnet_ids,
            "securityGroups": [ecs_sg_id],
            "assignPublicIp": "ENABLED",
        }},
        loadBalancers=[{
            "targetGroupArn": tg_arn,
            "containerName":  PROJECT,
            "containerPort":  _CONTAINER_PORT,
        }],
        tags=[{"key": "Project", "value": PROJECT}],
    )
    _log(f"service '{_SERVICE}' criado.")


def _wait_service_stable() -> None:
    _log("aguardando service estabilizar...")
    _ecs().get_waiter("services_stable").wait(
        cluster=_CLUSTER,
        services=[_SERVICE],
        WaiterConfig={"Delay": 15, "MaxAttempts": 40},  # até 10 min
    )
    _log("service estável.")


def _register_autoscaling() -> None:
    aas         = _aas()
    resource_id = f"service/{_CLUSTER}/{_SERVICE}"
    lab_role    = _lab_role_arn()

    aas.register_scalable_target(
        ServiceNamespace="ecs",
        ResourceId=resource_id,
        ScalableDimension="ecs:service:DesiredCount",
        MinCapacity=_MIN_TASKS,
        MaxCapacity=_MAX_TASKS,
        RoleARN=lab_role,
    )
    aas.put_scaling_policy(
        PolicyName=f"{PROJECT}-cpu-scaling",
        ServiceNamespace="ecs",
        ResourceId=resource_id,
        ScalableDimension="ecs:service:DesiredCount",
        PolicyType="TargetTrackingScaling",
        TargetTrackingScalingPolicyConfiguration={
            "TargetValue": _CPU_TARGET,
            "PredefinedMetricSpecification": {"PredefinedMetricType": "ECSServiceAverageCPUUtilization"},
            "ScaleInCooldown":  60,
            "ScaleOutCooldown": 30,
        },
    )
    _log(f"auto scaling registrado (CPU target {_CPU_TARGET}%, min {_MIN_TASKS}, max {_MAX_TASKS}).")


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def destroy(ctx: dict) -> None:
    """Remove todos os recursos ECS em ordem segura."""
    _deregister_autoscaling()
    _delete_service()
    _delete_listener(ctx.get("alb_arn"))
    _delete_alb(ctx.get("alb_arn"))
    _delete_target_group(ctx.get("tg_arn"))
    _deregister_task_definitions()
    _delete_cluster()
    _delete_log_group()


def _deregister_autoscaling() -> None:
    aas         = _aas()
    resource_id = f"service/{_CLUSTER}/{_SERVICE}"
    try:
        aas.deregister_scalable_target(
            ServiceNamespace="ecs",
            ResourceId=resource_id,
            ScalableDimension="ecs:service:DesiredCount",
        )
        _log("auto scaling removido.")
    except Exception as e:
        _log(f"aviso ao remover auto scaling: {e}")


def _delete_service() -> None:
    ecs = _ecs()
    try:
        ecs.update_service(cluster=_CLUSTER, service=_SERVICE, desiredCount=0)
        ecs.delete_service(cluster=_CLUSTER, service=_SERVICE, force=True)
        _log(f"service '{_SERVICE}' deletado.")
    except Exception as e:
        _log(f"aviso ao deletar service: {e}")


def _delete_listener(alb_arn: str | None) -> None:
    if not alb_arn:
        return
    try:
        listeners = _elbv2().describe_listeners(LoadBalancerArn=alb_arn)["Listeners"]
        for l in listeners:
            _elbv2().delete_listener(ListenerArn=l["ListenerArn"])
        _log("listeners deletados.")
    except Exception as e:
        _log(f"aviso ao deletar listeners: {e}")


def _delete_alb(alb_arn: str | None) -> None:
    if not alb_arn:
        return
    try:
        _elbv2().delete_load_balancer(LoadBalancerArn=alb_arn)
        _log(f"ALB deletado. Aguardando remoção...")
        _elbv2().get_waiter("load_balancers_deleted").wait(LoadBalancerArns=[alb_arn])
    except Exception as e:
        _log(f"aviso ao deletar ALB: {e}")


def _delete_target_group(tg_arn: str | None) -> None:
    if not tg_arn:
        return
    try:
        _elbv2().delete_target_group(TargetGroupArn=tg_arn)
        _log("target group deletado.")
    except Exception as e:
        _log(f"aviso ao deletar target group: {e}")


def _deregister_task_definitions() -> None:
    ecs = _ecs()
    try:
        arns = ecs.list_task_definitions(familyPrefix=_TASK_FAMILY)["taskDefinitionArns"]
        for arn in arns:
            ecs.deregister_task_definition(taskDefinition=arn)
        _log(f"{len(arns)} task definition(s) desregistradas.")
    except Exception as e:
        _log(f"aviso ao desregistrar task definitions: {e}")


def _delete_cluster() -> None:
    ecs = _ecs()
    try:
        _log("aguardando tasks do cluster pararem...")
        waiter = ecs.get_waiter("tasks_stopped")
        running = ecs.list_tasks(cluster=_CLUSTER, desiredStatus="RUNNING")["taskArns"]
        if running:
            waiter.wait(
                cluster=_CLUSTER,
                tasks=running,
                WaiterConfig={"Delay": 10, "MaxAttempts": 30},
            )
        ecs.delete_cluster(cluster=_CLUSTER)
        _log(f"cluster '{_CLUSTER}' deletado.")
    except Exception as e:
        _log(f"aviso ao deletar cluster: {e}")


def _delete_log_group() -> None:
    try:
        _logs().delete_log_group(logGroupName=_LOG_GROUP)
        _log(f"log group '{_LOG_GROUP}' deletado.")
    except Exception as e:
        _log(f"aviso ao deletar log group: {e}")
