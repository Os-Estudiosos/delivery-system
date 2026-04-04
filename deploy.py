"""
DijkFood — deploy.py

Automated AWS deployment (no manual steps):
  Phase 1 — VPC, subnets, Internet Gateway, security groups
  Phase 2 — IAM roles (cria ou detecta LabRole do AWS Academy)
  Phase 3 — CloudWatch log group
  Phase 4 — RDS PostgreSQL + DDL
  Phase 5 — DynamoDB (tabela de posições de courier)
  Phase 6 — ECR + docker build + push
  Phase 7 — ECS cluster (EC2 launch type) + Auto Scaling Group
  Phase 8 — Application Load Balancer + Target Group
  Phase 9 — ECS Task Definition + Service
  Phase 10 — Simulador de carga
  Cleanup  — destrói tudo em ordem inversa no bloco finally

Credenciais AWS: ~/.aws/credentials  (boto3 default chain, sem hardcode)
Execute com:  uv run python deploy.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.request

import boto3

# =============================================================================
# CONFIG
# =============================================================================

REGION           = "us-east-1"
PROJECT          = "dijkfood"
KEY_PAIR_NAME    = "fgv"           # key pair existente na conta
EC2_INSTANCE_TYPE = "t3.small"     # instâncias ECS (2 vCPU, 2 GB)
RDS_INSTANCE_CLASS = "db.t3.micro"

RDS_USER     = "dijkfood"
RDS_PASSWORD = "DijkFood2026!"     # senha do banco (não é credencial AWS)
RDS_DB_NAME  = "dijkfood"

# =============================================================================
# STATE — rastreia recursos criados para o cleanup
# =============================================================================

state: dict = {}


def log(msg: str) -> None:
    print(f"[deploy] {msg}", flush=True)


# =============================================================================
# FASE 1 — REDE
# =============================================================================

def create_vpc(ec2) -> str:
    log("Criando VPC...")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
    ec2.create_tags(Resources=[vpc_id], Tags=[{"Key": "Name", "Value": f"{PROJECT}-vpc"}])
    state["vpc_id"] = vpc_id
    log(f"VPC: {vpc_id}")
    return vpc_id


def create_subnets(ec2, vpc_id: str) -> list[str]:
    log("Criando subnets...")
    azs = [az["ZoneName"] for az in ec2.describe_availability_zones()["AvailabilityZones"][:2]]
    subnet_ids = []
    for i, az in enumerate(azs):
        sn = ec2.create_subnet(VpcId=vpc_id, CidrBlock=f"10.0.{i}.0/24", AvailabilityZone=az)
        sid = sn["Subnet"]["SubnetId"]
        ec2.modify_subnet_attribute(SubnetId=sid, MapPublicIpOnLaunch={"Value": True})
        ec2.create_tags(Resources=[sid], Tags=[{"Key": "Name", "Value": f"{PROJECT}-subnet-{i}"}])
        subnet_ids.append(sid)
    state["subnet_ids"] = subnet_ids
    log(f"Subnets: {subnet_ids}")
    return subnet_ids


def create_internet_gateway(ec2, vpc_id: str) -> None:
    log("Criando Internet Gateway...")
    igw_id = ec2.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    state["igw_id"] = igw_id

    rt_id = ec2.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]
    ec2.create_route(RouteTableId=rt_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)
    for sid in state["subnet_ids"]:
        ec2.associate_route_table(RouteTableId=rt_id, SubnetId=sid)
    state["rt_id"] = rt_id
    log(f"IGW: {igw_id}")


def create_security_groups(ec2, vpc_id: str, local_ip: str) -> tuple[str, str, str]:
    log("Criando security groups...")

    def mk_sg(name, desc):
        sg_id = ec2.create_security_group(
            GroupName=f"{PROJECT}-{name}", Description=desc, VpcId=vpc_id
        )["GroupId"]
        state[f"sg_{name}_id"] = sg_id
        return sg_id

    sg_alb = mk_sg("alb", "ALB - public HTTP")
    sg_ecs = mk_sg("ecs", "ECS EC2 instances")
    sg_rds = mk_sg("rds", "RDS PostgreSQL")

    # ALB: aceita 80 da internet
    ec2.authorize_security_group_ingress(GroupId=sg_alb, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80,
         "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
    ])

    # ECS: aceita todo tráfego do ALB + SSH da máquina local
    ec2.authorize_security_group_ingress(GroupId=sg_ecs, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 0, "ToPort": 65535,
         "UserIdGroupPairs": [{"GroupId": sg_alb}]},
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
         "IpRanges": [{"CidrIp": f"{local_ip}/32"}]},
    ])

    # RDS: aceita 5432 do ECS e da máquina local (para rodar o DDL)
    ec2.authorize_security_group_ingress(GroupId=sg_rds, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
         "UserIdGroupPairs": [{"GroupId": sg_ecs}]},
        {"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
         "IpRanges": [{"CidrIp": f"{local_ip}/32"}]},
    ])

    log(f"SGs — ALB: {sg_alb}  ECS: {sg_ecs}  RDS: {sg_rds}")
    return sg_alb, sg_ecs, sg_rds


# =============================================================================
# FASE 2 — IAM
# =============================================================================

def ensure_iam_roles(iam, account_id: str) -> tuple[str, str]:
    """
    Tenta usar o LabRole do AWS Academy.
    Se não existir, cria os roles necessários para ECS EC2.
    Retorna (instance_profile_arn, task_execution_role_arn).
    """
    log("Configurando IAM roles...")

    # AWS Academy: LabRole + LabInstanceProfile já existem
    try:
        lab_arn = iam.get_role(RoleName="LabRole")["Role"]["Arn"]
        iam.get_instance_profile(InstanceProfileName="LabInstanceProfile")
        ip_arn = f"arn:aws:iam::{account_id}:instance-profile/LabInstanceProfile"
        state["roles_created"] = False
        log(f"Usando LabRole: {lab_arn}")
        return ip_arn, lab_arn
    except iam.exceptions.NoSuchEntityException:
        pass

    # Conta regular: cria os roles
    trust_ec2 = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow",
                       "Principal": {"Service": "ec2.amazonaws.com"},
                       "Action": "sts:AssumeRole"}],
    })
    trust_ecs = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow",
                       "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                       "Action": "sts:AssumeRole"}],
    })

    instance_role = f"{PROJECT}-ecs-instance"
    exec_role     = f"{PROJECT}-ecs-task-exec"

    for role, trust, policy in [
        (instance_role, trust_ec2,
         "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"),
        (exec_role, trust_ecs,
         "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"),
    ]:
        try:
            iam.create_role(RoleName=role, AssumeRolePolicyDocument=trust)
            iam.attach_role_policy(RoleName=role, PolicyArn=policy)
        except iam.exceptions.EntityAlreadyExistsException:
            pass

    try:
        iam.create_instance_profile(InstanceProfileName=instance_role)
        iam.add_role_to_instance_profile(InstanceProfileName=instance_role,
                                          RoleName=instance_role)
        time.sleep(10)  # propagação IAM
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    ip_arn   = f"arn:aws:iam::{account_id}:instance-profile/{instance_role}"
    exec_arn = f"arn:aws:iam::{account_id}:role/{exec_role}"
    state["roles_created"] = True
    log("IAM roles criados")
    return ip_arn, exec_arn


# =============================================================================
# FASE 3 — CLOUDWATCH LOGS
# =============================================================================

def create_log_group(logs) -> None:
    try:
        logs.create_log_group(logGroupName=f"/ecs/{PROJECT}")
        log("CloudWatch log group criado")
    except logs.exceptions.ResourceAlreadyExistsException:
        log("CloudWatch log group já existe")


# =============================================================================
# FASE 4 — RDS PostgreSQL
# =============================================================================

def _latest_pg16_version(rds) -> str:
    """Retorna a versão mais recente do PostgreSQL 16.x disponível na região."""
    resp = rds.describe_db_engine_versions(Engine="postgres")
    versions = sorted(
        v["EngineVersion"] for v in resp["DBEngineVersions"]
        if v["EngineVersion"].startswith("16.")
    )
    if not versions:
        raise RuntimeError("Nenhuma versão PostgreSQL 16.x disponível na região")
    return versions[-1]


def create_rds(rds, subnet_ids: list[str], sg_rds_id: str) -> str:
    log("Criando RDS PostgreSQL (Multi-AZ)...")

    pg_version = _latest_pg16_version(rds)
    log(f"Versao PostgreSQL disponivel: {pg_version}")

    try:
        rds.create_db_subnet_group(
            DBSubnetGroupName=f"{PROJECT}-db-subnet",
            DBSubnetGroupDescription="DijkFood RDS subnets",
            SubnetIds=subnet_ids,
        )
    except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
        log("  DB subnet group ja existe, recriando...")
        rds.delete_db_subnet_group(DBSubnetGroupName=f"{PROJECT}-db-subnet")
        rds.create_db_subnet_group(
            DBSubnetGroupName=f"{PROJECT}-db-subnet",
            DBSubnetGroupDescription="DijkFood RDS subnets",
            SubnetIds=subnet_ids,
        )

    rds.create_db_instance(
        DBInstanceIdentifier=f"{PROJECT}-db",
        DBInstanceClass=RDS_INSTANCE_CLASS,
        Engine="postgres",
        EngineVersion=pg_version,
        MasterUsername=RDS_USER,
        MasterUserPassword=RDS_PASSWORD,
        DBName=RDS_DB_NAME,
        AllocatedStorage=20,
        StorageType="gp2",
        MultiAZ=True,
        PubliclyAccessible=True,       # necessário para rodar DDL localmente
        VpcSecurityGroupIds=[sg_rds_id],
        DBSubnetGroupName=f"{PROJECT}-db-subnet",
        BackupRetentionPeriod=0,
        Tags=[{"Key": "project", "Value": PROJECT}],
    )

    log("Aguardando RDS ficar disponível (pode levar ~10 min)...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=f"{PROJECT}-db",
        WaiterConfig={"Delay": 30, "MaxAttempts": 40},
    )

    endpoint = rds.describe_db_instances(
        DBInstanceIdentifier=f"{PROJECT}-db"
    )["DBInstances"][0]["Endpoint"]["Address"]
    state["rds_endpoint"] = endpoint
    log(f"RDS pronto: {endpoint}")
    return endpoint


def run_ddl(rds_endpoint: str) -> None:
    """Executa o DDL no RDS usando psycopg2 (disponível via sqlmodel)."""
    log("Executando DDL no RDS...")
    import psycopg2  # disponível como dep transitiva do sqlmodel

    ddl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "infra", "sql", "ddl.sql")
    ddl_sql  = open(ddl_path).read()

    conn = psycopg2.connect(
        host=rds_endpoint,
        port=5432,
        user=RDS_USER,
        password=RDS_PASSWORD,
        dbname=RDS_DB_NAME,
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(ddl_sql)
    conn.close()
    log("DDL executado com sucesso")


# =============================================================================
# FASE 5 — DynamoDB
# =============================================================================

def create_dynamodb_table(dynamo) -> None:
    log("Criando tabela DynamoDB (posições de courier)...")
    table_name = f"{PROJECT}-courier-positions"
    try:
        dynamo.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "courier_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp",   "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "courier_id", "AttributeType": "S"},
                {"AttributeName": "timestamp",   "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
            Tags=[{"Key": "project", "Value": PROJECT}],
        )
        state["dynamo_table"] = table_name
        log(f"Tabela DynamoDB: {table_name}")
    except dynamo.exceptions.ResourceInUseException:
        state["dynamo_table"] = table_name
        log("Tabela DynamoDB já existe")


# =============================================================================
# FASE 6 — ECR + Docker
# =============================================================================

def build_and_push_image(ecr, account_id: str) -> str:
    """Cria repositório ECR, builda imagem local e faz push."""
    repo_name = f"{PROJECT}-api"

    log("Criando repositório ECR...")
    try:
        repo_uri = ecr.create_repository(repositoryName=repo_name)["repository"]["repositoryUri"]
    except ecr.exceptions.RepositoryAlreadyExistsException:
        repo_uri = ecr.describe_repositories(
            repositoryNames=[repo_name]
        )["repositories"][0]["repositoryUri"]
    state["ecr_repo_name"] = repo_name

    # Autenticar Docker no ECR
    log("Autenticando Docker no ECR...")
    token     = ecr.get_authorization_token()["authorizationData"][0]
    user, pwd = base64.b64decode(token["authorizationToken"]).decode().split(":", 1)
    registry  = token["proxyEndpoint"]
    subprocess.run(
        ["docker", "login", "--username", user, "--password-stdin", registry],
        input=pwd.encode(), check=True, capture_output=True,
    )

    project_root = os.path.dirname(os.path.abspath(__file__))
    image_tag    = f"{repo_uri}:latest"

    log("Build da imagem Docker...")
    subprocess.run(["docker", "build", "-t", repo_name, project_root], check=True)

    log("Push da imagem para ECR...")
    subprocess.run(["docker", "tag", repo_name, image_tag], check=True)
    subprocess.run(["docker", "push", image_tag], check=True)

    log(f"Imagem disponível: {image_tag}")
    return image_tag


# =============================================================================
# FASE 7 — ECS Cluster (EC2 launch type) + Auto Scaling Group
# =============================================================================

def get_ecs_optimized_ami() -> str:
    ssm = boto3.client("ssm", region_name=REGION)
    return ssm.get_parameter(
        Name="/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id"
    )["Parameter"]["Value"]


def create_ecs_cluster(ec2, ecs, asg_client, subnet_ids, sg_ecs_id, ip_arn) -> str:
    cluster_name = f"{PROJECT}-cluster"
    log(f"Criando ECS cluster: {cluster_name}")
    ecs.create_cluster(clusterName=cluster_name)
    state["cluster_name"] = cluster_name

    ami_id = get_ecs_optimized_ami()
    log(f"AMI ECS-optimized: {ami_id}")

    # UserData: registra instância no cluster
    user_data = base64.b64encode(
        f"#!/bin/bash\necho ECS_CLUSTER={cluster_name} >> /etc/ecs/ecs.config\n".encode()
    ).decode()

    lt = ec2.create_launch_template(
        LaunchTemplateName=f"{PROJECT}-ecs-lt",
        LaunchTemplateData={
            "ImageId":            ami_id,
            "InstanceType":       EC2_INSTANCE_TYPE,
            "SecurityGroupIds":   [sg_ecs_id],
            "IamInstanceProfile": {"Arn": ip_arn},
            "UserData":           user_data,
        },
    )
    lt_id = lt["LaunchTemplate"]["LaunchTemplateId"]
    state["lt_id"] = lt_id

    asg_name = f"{PROJECT}-asg"
    asg_client.create_auto_scaling_group(
        AutoScalingGroupName=asg_name,
        MinSize=1,
        MaxSize=4,
        DesiredCapacity=2,
        LaunchTemplate={"LaunchTemplateId": lt_id, "Version": "$Latest"},
        VPCZoneIdentifier=",".join(subnet_ids),
        Tags=[{
            "Key": "Name", "Value": f"{PROJECT}-ecs-ec2",
            "PropagateAtLaunch": True,
            "ResourceId": asg_name, "ResourceType": "auto-scaling-group",
        }],
    )
    state["asg_name"] = asg_name
    log("Auto Scaling Group criado, aguardando instâncias registrarem no cluster...")

    # Aguarda ao menos 1 instância registrada
    for _ in range(24):
        time.sleep(15)
        resp       = ecs.describe_clusters(clusters=[cluster_name])
        registered = resp["clusters"][0].get("registeredContainerInstancesCount", 0)
        log(f"  Instâncias registradas: {registered}")
        if registered >= 1:
            break

    return cluster_name


# =============================================================================
# FASE 8 — Application Load Balancer
# =============================================================================

def create_alb(elbv2, subnet_ids, sg_alb_id, vpc_id) -> tuple[str, str, str]:
    log("Criando Application Load Balancer...")

    alb     = elbv2.create_load_balancer(
        Name=f"{PROJECT}-alb",
        Subnets=subnet_ids,
        SecurityGroups=[sg_alb_id],
        Scheme="internet-facing",
        Type="application",
    )["LoadBalancers"][0]
    alb_arn = alb["LoadBalancerArn"]
    alb_dns = alb["DNSName"]
    state["alb_arn"] = alb_arn

    tg = elbv2.create_target_group(
        Name=f"{PROJECT}-tg",
        Protocol="HTTP",
        Port=8000,
        VpcId=vpc_id,
        TargetType="instance",
        HealthCheckPath="/",
        HealthCheckIntervalSeconds=30,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=3,
    )["TargetGroups"][0]
    tg_arn = tg["TargetGroupArn"]
    state["tg_arn"] = tg_arn

    elbv2.create_listener(
        LoadBalancerArn=alb_arn,
        Protocol="HTTP",
        Port=80,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
    )

    log(f"ALB DNS: {alb_dns}")
    return alb_arn, tg_arn, alb_dns


# =============================================================================
# FASE 9 — ECS Task Definition + Service
# =============================================================================

def create_task_definition(ecs, image_uri, exec_role_arn, rds_endpoint) -> str:
    log("Registrando Task Definition ECS...")
    resp = ecs.register_task_definition(
        family=f"{PROJECT}-api",
        networkMode="bridge",
        requiresCompatibilities=["EC2"],
        executionRoleArn=exec_role_arn,
        containerDefinitions=[{
            "name":      "api",
            "image":     image_uri,
            "cpu":       512,
            "memory":    512,
            "essential": True,
            "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
            "environment": [
                {"name": "DB_HOST",     "value": rds_endpoint},
                {"name": "DB_PORT",     "value": "5432"},
                {"name": "DB_NAME",     "value": RDS_DB_NAME},
                {"name": "DB_USER",     "value": RDS_USER},
                {"name": "DB_PASSWORD", "value": RDS_PASSWORD},
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group":         f"/ecs/{PROJECT}",
                    "awslogs-region":        REGION,
                    "awslogs-stream-prefix": "api",
                },
            },
        }],
    )
    td_arn = resp["taskDefinition"]["taskDefinitionArn"]
    state["task_def_arn"] = td_arn
    log(f"Task Definition: {td_arn}")
    return td_arn


def create_ecs_service(ecs, cluster_name, td_arn, tg_arn) -> None:
    log("Criando ECS Service...")
    ecs.create_service(
        cluster=cluster_name,
        serviceName=f"{PROJECT}-api",
        taskDefinition=td_arn,
        desiredCount=2,
        launchType="EC2",
        loadBalancers=[{
            "targetGroupArn": tg_arn,
            "containerName":  "api",
            "containerPort":  8000,
        }],
        deploymentConfiguration={
            "maximumPercent":        200,
            "minimumHealthyPercent": 50,
        },
        healthCheckGracePeriodSeconds=60,
    )
    state["service_name"] = f"{PROJECT}-api"

    log("Aguardando ECS service estabilizar (até 15 min)...")
    waiter = ecs.get_waiter("services_stable")
    waiter.wait(
        cluster=cluster_name,
        services=[f"{PROJECT}-api"],
        WaiterConfig={"Delay": 20, "MaxAttempts": 45},
    )
    log("ECS service estável")


# =============================================================================
# FASE 10 — Simulador de carga
# =============================================================================

def run_simulator(alb_dns: str) -> None:
    log(f"\nSimulador de carga → http://{alb_dns}")

    # Health check básico
    url = f"http://{alb_dns}/"
    with urllib.request.urlopen(url, timeout=15) as r:
        body = r.read().decode()
    log(f"API respondeu: {body}")

    # TODO: chamar simulator/load_simulator.py com a URL do ALB
    # quando as rotas estiverem implementadas


# =============================================================================
# CLEANUP — destrói tudo em ordem inversa
# =============================================================================

def destroy_all(ec2, ecs, rds, asg_client, elbv2, ecr, dynamo, iam, logs) -> None:
    log("\n" + "=" * 60)
    log("INICIANDO CLEANUP — destruindo todos os recursos")
    log("=" * 60)

    def safe(label, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
            log(f"  ✓ {label}")
        except Exception as e:
            log(f"  ⚠ {label}: {e}")

    # ECS service
    if "service_name" in state and "cluster_name" in state:
        safe("ECS service scale-down",
             ecs.update_service,
             cluster=state["cluster_name"], service=state["service_name"], desiredCount=0)
        time.sleep(5)
        safe("ECS service delete",
             ecs.delete_service,
             cluster=state["cluster_name"], service=state["service_name"], force=True)

    # ECS task definition
    if "task_def_arn" in state:
        safe("Task definition deregister",
             ecs.deregister_task_definition,
             taskDefinition=state["task_def_arn"])

    # Auto Scaling Group (termina instâncias EC2)
    if "asg_name" in state:
        safe("Auto Scaling Group",
             asg_client.delete_auto_scaling_group,
             AutoScalingGroupName=state["asg_name"], ForceDelete=True)

    # ECS Cluster
    if "cluster_name" in state:
        log("  Aguardando instâncias terminarem (~45s)...")
        time.sleep(45)
        safe("ECS cluster", ecs.delete_cluster, cluster=state["cluster_name"])

    # Launch Template
    if "lt_id" in state:
        safe("Launch Template",
             ec2.delete_launch_template,
             LaunchTemplateId=state["lt_id"])

    # ALB → Listener → Target Group
    if "alb_arn" in state:
        try:
            for l in elbv2.describe_listeners(LoadBalancerArn=state["alb_arn"])["Listeners"]:
                safe("ALB listener", elbv2.delete_listener, ListenerArn=l["ListenerArn"])
        except Exception as e:
            log(f"  ⚠ ALB listeners: {e}")
        safe("ALB", elbv2.delete_load_balancer, LoadBalancerArn=state["alb_arn"])
        time.sleep(10)
    if "tg_arn" in state:
        safe("Target Group", elbv2.delete_target_group, TargetGroupArn=state["tg_arn"])

    # RDS
    safe("RDS instance",
         rds.delete_db_instance,
         DBInstanceIdentifier=f"{PROJECT}-db",
         SkipFinalSnapshot=True,
         DeleteAutomatedBackups=True)
    # Subnet group pode só ser deletado após instância ser removida (async)
    log("  (RDS deletion é assíncrono — subnet group deletado após ~5min se necessário)")

    # DynamoDB
    if "dynamo_table" in state:
        safe("DynamoDB table", dynamo.delete_table, TableName=state["dynamo_table"])

    # ECR
    if "ecr_repo_name" in state:
        safe("ECR repository",
             ecr.delete_repository,
             repositoryName=state["ecr_repo_name"], force=True)

    # CloudWatch Logs
    safe("CloudWatch log group",
         logs.delete_log_group,
         logGroupName=f"/ecs/{PROJECT}")

    # RDS subnet group — sempre tenta deletar (idempotente)
    # Aguarda instância terminar primeiro, se existir
    if "rds_endpoint" in state:
        try:
            waiter = rds.get_waiter("db_instance_deleted")
            waiter.wait(DBInstanceIdentifier=f"{PROJECT}-db",
                        WaiterConfig={"Delay": 30, "MaxAttempts": 20})
        except Exception:
            pass
    safe("RDS subnet group",
         rds.delete_db_subnet_group,
         DBSubnetGroupName=f"{PROJECT}-db-subnet")

    # Security Groups — revogar regras cross-SG antes de deletar
    # (SG não pode ser deletado enquanto outro SG o referencia em uma regra)
    log("  Aguardando ENIs serem liberadas (~30s)...")
    time.sleep(30)
    for key in ["sg_rds_id", "sg_ecs_id", "sg_alb_id"]:  # ordem: dependentes primeiro
        sg_id = state.get(key)
        if not sg_id:
            continue
        try:
            sg_info = ec2.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]
            if sg_info["IpPermissions"]:
                ec2.revoke_security_group_ingress(
                    GroupId=sg_id, IpPermissions=sg_info["IpPermissions"]
                )
        except Exception as e:
            log(f"  ⚠ Revoke rules {key}: {e}")
        safe(f"Security Group {key}", ec2.delete_security_group, GroupId=sg_id)

    # Route Table
    if "rt_id" in state:
        try:
            rt = ec2.describe_route_tables(RouteTableIds=[state["rt_id"]])["RouteTables"][0]
            for assoc in rt.get("Associations", []):
                if not assoc.get("Main"):
                    safe("RT association",
                         ec2.disassociate_route_table,
                         AssociationId=assoc["RouteTableAssociationId"])
        except Exception as e:
            log(f"  ⚠ RT associations: {e}")
        safe("Route Table", ec2.delete_route_table, RouteTableId=state["rt_id"])

    # Subnets
    for sid in state.get("subnet_ids", []):
        safe(f"Subnet {sid}", ec2.delete_subnet, SubnetId=sid)

    # Internet Gateway
    if "igw_id" in state and "vpc_id" in state:
        safe("IGW detach",
             ec2.detach_internet_gateway,
             InternetGatewayId=state["igw_id"], VpcId=state["vpc_id"])
        safe("IGW delete",
             ec2.delete_internet_gateway,
             InternetGatewayId=state["igw_id"])

    # VPC
    if "vpc_id" in state:
        safe("VPC", ec2.delete_vpc, VpcId=state["vpc_id"])

    # IAM (somente se foram criados por este script)
    if state.get("roles_created"):
        instance_role = f"{PROJECT}-ecs-instance"
        exec_role     = f"{PROJECT}-ecs-task-exec"
        safe("IAM role detach (instance)",
             iam.detach_role_policy,
             RoleName=instance_role,
             PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role")
        safe("IAM role detach (exec)",
             iam.detach_role_policy,
             RoleName=exec_role,
             PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy")
        safe("Instance profile remove role",
             iam.remove_role_from_instance_profile,
             InstanceProfileName=instance_role, RoleName=instance_role)
        safe("Instance profile delete",
             iam.delete_instance_profile,
             InstanceProfileName=instance_role)
        safe("IAM role delete (instance)", iam.delete_role, RoleName=instance_role)
        safe("IAM role delete (exec)",     iam.delete_role, RoleName=exec_role)

    log("\nCleanup concluído.")


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    session = boto3.Session(region_name=REGION)

    ec2        = session.client("ec2")
    ecs        = session.client("ecs")
    rds        = session.client("rds")
    asg_client = session.client("autoscaling")
    elbv2      = session.client("elbv2")
    ecr        = session.client("ecr")
    dynamo     = session.client("dynamodb")
    iam        = session.client("iam")
    logs       = session.client("logs")

    account_id = session.client("sts").get_caller_identity()["Account"]
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5) as r:
        local_ip = r.read().decode().strip()

    log(f"Conta: {account_id} | IP local: {local_ip} | Região: {REGION}")

    try:
        # Fase 1 — Rede
        vpc_id     = create_vpc(ec2)
        subnet_ids = create_subnets(ec2, vpc_id)
        create_internet_gateway(ec2, vpc_id)
        sg_alb, sg_ecs, sg_rds = create_security_groups(ec2, vpc_id, local_ip)

        # Fase 2 — IAM
        ip_arn, exec_role_arn = ensure_iam_roles(iam, account_id)

        # Fase 3 — CloudWatch
        create_log_group(logs)

        # Fase 4 — RDS
        rds_endpoint = create_rds(rds, subnet_ids, sg_rds)
        run_ddl(rds_endpoint)

        # Fase 5 — DynamoDB
        create_dynamodb_table(dynamo)

        # Fase 6 — ECR + Docker
        image_uri = build_and_push_image(ecr, account_id)

        # Fase 7 — ECS Cluster
        cluster_name = create_ecs_cluster(ec2, ecs, asg_client, subnet_ids, sg_ecs, ip_arn)

        # Fase 8 — ALB
        _, tg_arn, alb_dns = create_alb(elbv2, subnet_ids, sg_alb, vpc_id)

        # Fase 9 — Task Definition + Service
        td_arn = create_task_definition(ecs, image_uri, exec_role_arn, rds_endpoint)
        create_ecs_service(ecs, cluster_name, td_arn, tg_arn)

        log(f"\n{'='*60}")
        log(f"API disponível em: http://{alb_dns}/")
        log(f"{'='*60}\n")

        # Fase 10 — Simulador
        run_simulator(alb_dns)

    except Exception as e:
        log(f"\nERRO FATAL: {e}")
        raise

    finally:
        destroy_all(ec2, ecs, rds, asg_client, elbv2, ecr, dynamo, iam, logs)


if __name__ == "__main__":
    main()
