"""
deploy_ecs.py — Cria e destrói o cluster ECS Fargate do DijkFood.

Recursos gerenciados:
  - CloudWatch Log Group
  - ECS Cluster
    - Task Definition (imagem publicada no ECR)
  - ALB + Target Group + Listener
  - ECS Service
  - Application Auto Scaling (CPU target 70%)

Dependências de ctx: subnet_ids, alb_sg_id, ecs_sg_id,
                     db_host, db_port, db_name, db_user, db_password

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_ecs
"""

import boto3
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import APP_PORT, LAB_ROLE_NAME, PROJECT, REGION, tags

_CLUSTER        = f"{PROJECT}-cluster"
_TASK_FAMILY    = f"{PROJECT}-task"
_SERVICE        = f"{PROJECT}-service"
_ALB_NAME       = f"{PROJECT}-alb"
_TG_NAME        = f"{PROJECT}-tg"
_LOG_GROUP      = f"/ecs/{PROJECT}"
_DEFAULT_IMAGE_TAG = "latest"
_CONTAINER_PORT = APP_PORT
_CPU            = "256"
_MEMORY         = "512"
_MIN_TASKS      = int(os.getenv("ECS_MIN_TASKS", "1"))
_MAX_TASKS      = int(os.getenv("ECS_MAX_TASKS", "4"))
_CPU_TARGET     = float(os.getenv("ECS_CPU_TARGET", "70"))
_MEMORY_TARGET  = float(os.getenv("ECS_MEMORY_TARGET", "75"))
_SCALE_IN_COOLDOWN  = int(os.getenv("ECS_SCALE_IN_COOLDOWN", "60"))
_SCALE_OUT_COOLDOWN = int(os.getenv("ECS_SCALE_OUT_COOLDOWN", "30"))


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


def export_container_logs(output_dir: str = "logs", container_count: int | None = None) -> list[str]:
    """Exporta logs do ECS para arquivos locais (um arquivo por container/task)."""
    logs_client = _logs()
    ecs_client = _ecs()
    max_files = container_count or _MIN_TASKS
    if max_files <= 0:
        return []

    task_arns = ecs_client.list_tasks(
        cluster=_CLUSTER,
        serviceName=_SERVICE,
        desiredStatus="RUNNING",
    ).get("taskArns", [])
    task_ids = [arn.rsplit("/", 1)[-1] for arn in task_arns]

    streams_resp = logs_client.describe_log_streams(
        logGroupName=_LOG_GROUP,
        orderBy="LastEventTime",
        descending=True,
        limit=max(50, max_files * 20),
    )
    stream_names = [s.get("logStreamName") for s in streams_resp.get("logStreams", []) if s.get("logStreamName")]
    if not stream_names:
        _log("nenhum stream encontrado para exportação.")
        return []

    if task_ids:
        selected_streams = [name for name in stream_names if any(task_id in name for task_id in task_ids)]
    else:
        selected_streams = stream_names

    if not selected_streams:
        selected_streams = stream_names

    selected_streams = selected_streams[:max_files]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    paginator = logs_client.get_paginator("filter_log_events")
    for index, stream_name in enumerate(selected_streams, start=1):
        events = []
        for page in paginator.paginate(
            logGroupName=_LOG_GROUP,
            logStreamNames=[stream_name],
            PaginationConfig={"PageSize": 1000},
        ):
            events.extend(page.get("events", []))

        events.sort(key=lambda event: event.get("timestamp", 0))
        task_id = next((tid for tid in task_ids if tid in stream_name), None)
        suffix = task_id or f"stream-{index:02d}"
        file_name = f"{PROJECT}-container-{suffix}.log"
        out_file = out_dir / file_name

        lines = [f"# stream={stream_name}"]
        if not events:
            lines.append("# sem eventos neste stream")
        else:
            for event in events:
                timestamp_ms = event.get("timestamp", 0)
                event_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
                message = str(event.get("message", "")).rstrip("\n")
                lines.append(f"[{event_time}] {message}")

        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        saved_files.append(str(out_file))

    _log(f"{len(saved_files)} arquivo(s) de log exportado(s) para '{out_dir}'.")
    return saved_files


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

    api_url = f"http://{alb_dns}"

    _log("pronto.")
    return {
        "alb_arn":      alb_arn,
        "alb_dns":      alb_dns,
        "api_url":      api_url,
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
    image_uri = ctx.get("image_uri")
    if not image_uri:
        repo_uri = ctx.get("repo_uri")
        if repo_uri:
            image_uri = f"{repo_uri}:{ctx.get('image_tag', _DEFAULT_IMAGE_TAG)}"
        else:
            raise ValueError("ctx sem imagem para ECS. Esperado: image_uri ou repo_uri.")

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
            "image":     image_uri,
            "essential": True,
            "portMappings": [{"containerPort": _CONTAINER_PORT, "protocol": "tcp"}],
            "environment": [
                {"name": "DB_HOST",     "value": ctx.get("db_host", "")},
                {"name": "DB_PORT",     "value": str(ctx.get("db_port", 5432))},
                {"name": "DB_NAME",     "value": ctx.get("db_name", "")},
                {"name": "DB_USER",     "value": ctx.get("db_user", "")},
                {"name": "DB_PASSWORD", "value": ctx.get("db_password", "")},
                {"name": "PROJECT_ENV", "value": "production"},
                {"name": "AWS_REGION",  "value": REGION},
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
        ecs.update_service(
            cluster=_CLUSTER,
            service=_SERVICE,
            taskDefinition=_TASK_FAMILY,
            desiredCount=_MIN_TASKS,
            forceNewDeployment=True,
        )
        _log(f"service '{_SERVICE}' já existe, atualizado para {_MIN_TASKS} tasks.")
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
    if _MAX_TASKS < _MIN_TASKS:
        raise ValueError(f"Configuração inválida de autoscaling: min {_MIN_TASKS} > max {_MAX_TASKS}")

    if _MAX_TASKS == _MIN_TASKS:
        _log(f"auto scaling desabilitado (min=max={_MIN_TASKS}).")
        return

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
    _put_target_tracking_policy(
        policy_name=f"{PROJECT}-cpu-scaling",
        resource_id=resource_id,
        metric_type="ECSServiceAverageCPUUtilization",
        target_value=_CPU_TARGET,
    )
    _put_target_tracking_policy(
        policy_name=f"{PROJECT}-memory-scaling",
        resource_id=resource_id,
        metric_type="ECSServiceAverageMemoryUtilization",
        target_value=_MEMORY_TARGET,
    )
    _log(
        "auto scaling registrado "
        f"(CPU {_CPU_TARGET}%, MEM {_MEMORY_TARGET}%, min {_MIN_TASKS}, max {_MAX_TASKS})."
    )


def _put_target_tracking_policy(
    policy_name: str,
    resource_id: str,
    metric_type: str,
    target_value: float,
) -> None:
    _aas().put_scaling_policy(
        PolicyName=policy_name,
        ServiceNamespace="ecs",
        ResourceId=resource_id,
        ScalableDimension="ecs:service:DesiredCount",
        PolicyType="TargetTrackingScaling",
        TargetTrackingScalingPolicyConfiguration={
            "TargetValue": target_value,
            "PredefinedMetricSpecification": {"PredefinedMetricType": metric_type},
            "ScaleInCooldown": _SCALE_IN_COOLDOWN,
            "ScaleOutCooldown": _SCALE_OUT_COOLDOWN,
        },
    )


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
