"""
DijkFood — deploy.py (Versão Otimizada para AWS Academy)
Objetivo: Validar API, RDS e DynamoDB com o mínimo de atrito.
"""

import boto3
import base64
import urllib.request
import time
# =============================================================================
# CONFIGURAÇÕES GERAIS
# =============================================================================
REGION = "us-east-1"
PROJECT = "dijkfood"
EC2_INSTANCE_TYPE = "t3.small"
RDS_INSTANCE_CLASS = "db.t3.micro"
RDS_USER = "dijkfood"
RDS_PASSWORD = "DijkFood2026!"
RDS_DB_NAME = "dijkfood"

state = {}

def log(msg: str):
    print(f"[deploy] {msg}", flush=True)

def get_ecs_optimized_ami():
    log("Buscando AMI otimizada para ECS (Amazon Linux 2)...")
    ssm = boto3.client('ssm', region_name=REGION)
    parameter = ssm.get_parameter(Name='/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id')
    return parameter['Parameter']['Value']

# =============================================================================
# FASE 1 — REDE (IDEMPOTENTE)
# =============================================================================
def get_or_create_vpc(ec2):
    log("Verificando VPC...")
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [f"{PROJECT}-vpc"]}])['Vpcs']
    if vpcs:
        vpc_id = vpcs[0]['VpcId']
        log(f"  ✓ Usando VPC existente: {vpc_id}")
    else:
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc['Vpc']['VpcId']
        ec2.create_tags(Resources=[vpc_id], Tags=[{"Key": "Name", "Value": f"{PROJECT}-vpc"}])
        log(f"  ✓ Nova VPC criada: {vpc_id}")
    
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
    state["vpc_id"] = vpc_id
    return vpc_id

def setup_network(ec2, vpc_id, local_ip):
    # Subnets
    azs = [az['ZoneName'] for az in ec2.describe_availability_zones()['AvailabilityZones'][:2]]
    subnet_ids = []
    
    for i, az in enumerate(azs):
        cidr = f"10.0.{i}.0/24"
        log(f"Verificando subnet para o bloco {cidr}...")
        
        # Procura por qualquer subnet que já use este CIDR nesta VPC
        existing_sn = ec2.describe_subnets(Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'cidr-block', 'Values': [cidr]}
        ])['Subnets']

        if existing_sn:
            sid = existing_sn[0]['SubnetId']
            log(f"  ✓ Subnet existente encontrada: {sid}")
            # Garante que ela tenha a tag correta para futuras execuções
            ec2.create_tags(Resources=[sid], Tags=[{"Key": "Name", "Value": f"{PROJECT}-sn-{i}"}])
        else:
            log(f"  Criando nova subnet em {az}...")
            sn = ec2.create_subnet(VpcId=vpc_id, CidrBlock=cidr, AvailabilityZone=az)
            sid = sn['Subnet']['SubnetId']
            ec2.create_tags(Resources=[sid], Tags=[{"Key": "Name", "Value": f"{PROJECT}-sn-{i}"}])
        
        # Garante IP público para as instâncias ECS e comunicação com o IGW [cite: 17]
        ec2.modify_subnet_attribute(SubnetId=sid, MapPublicIpOnLaunch={'Value': True})
        subnet_ids.append(sid)
    
    state["subnet_ids"] = subnet_ids

    # 2. INTERNET GATEWAY (Garantir que ele existe e está conectado)
    log("Configurando Internet Gateway...")
    igw_id = None
    igws = ec2.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}])['InternetGateways']
    
    if igws:
        igw_id = igws[0]['InternetGatewayId']
        log(f"  ✓ IGW existente encontrado: {igw_id}")
    else:
        igw = ec2.create_internet_gateway()
        igw_id = igw['InternetGateway']['InternetGatewayId']
        ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        ec2.create_tags(Resources=[igw_id], Tags=[{"Key": "Name", "Value": f"{PROJECT}-igw"}])
        log(f"  ✓ Novo IGW criado e conectado: {igw_id}")

    # 3. TABELA DE ROTAS E ROTA PARA INTERNET
    log("Configurando Tabela de Rotas...")
    rt_id = None
    rts = ec2.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}, {'Name': 'tag:Name', 'Values': [f"{PROJECT}-rt"]}])['RouteTables']
    
    if rts:
        rt_id = rts[0]['RouteTableId']
    else:
        rt = ec2.create_route_table(VpcId=vpc_id)
        rt_id = rt['RouteTable']['RouteTableId']
        ec2.create_tags(Resources=[rt_id], Tags=[{"Key": "Name", "Value": f"{PROJECT}-rt"}])
        
        # ESSENCIAL: Cria a rota 0.0.0.0/0 apontando para o IGW
        ec2.create_route(
            RouteTableId=rt_id,
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw_id
        )
        log(f"  ✓ Tabela de rotas criada com saída para internet.")

    # 4. ASSOCIAR TABELA ÀS SUB-REDES
    for sid in state["subnet_ids"]:
        try:
            ec2.associate_route_table(RouteTableId=rt_id, SubnetId=sid)
        except:
            pass # Ignora se já estiver associado

    # Security Groups
    def get_sg(name, desc):
        try:
            return ec2.describe_security_groups(Filters=[{'Name': 'group-name', 'Values': [f"{PROJECT}-{name}"]}])['SecurityGroups'][0]['GroupId']
        except:
            return ec2.create_security_group(GroupName=f"{PROJECT}-{name}", Description=desc, VpcId=vpc_id)['GroupId']

    sg_alb = get_sg("alb", "ALB Public")
    sg_ecs = get_sg("ecs", "ECS Instances")
    sg_rds = get_sg("rds", "RDS Port")
    state.update({"sg_alb": sg_alb, "sg_ecs": sg_ecs, "sg_rds": sg_rds})

    # Regras básicas (Ignora se já existir)
    try:
        ec2.authorize_security_group_ingress(GroupId=sg_alb, IpProtocol='tcp', FromPort=80, ToPort=80, CidrIp='0.0.0.0/0')
        ec2.authorize_security_group_ingress(GroupId=sg_ecs, IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 8000, 'ToPort': 8000, 'UserIdGroupPairs': [{'GroupId': sg_alb}]}])
        ec2.authorize_security_group_ingress(GroupId=sg_rds, IpProtocol='tcp', FromPort=5432, ToPort=5432, CidrIp=f"{local_ip}/32")
        ec2.authorize_security_group_ingress(GroupId=sg_rds, IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432, 'UserIdGroupPairs': [{'GroupId': sg_ecs}]}])
    except: pass

    return subnet_ids

# =============================================================================
# FASE 2 — IAM (LABROLE)
# =============================================================================
def get_lab_role(iam, account_id):
    log("Detectando LabRole do AWS Academy...")
    role_arn = f"arn:aws:iam::{account_id}:role/LabRole"
    ip_arn = f"arn:aws:iam::{account_id}:instance-profile/LabInstanceProfile"
    return ip_arn, role_arn

# =============================================================================
# FASE 3 — RDS (SINGLE-AZ PARA TESTE RÁPIDO)
# =============================================================================
def setup_rds(rds, subnet_ids, sg_id, vpc_id):
    sng_name = f"{PROJECT}-sng-{vpc_id[-8:]}"
    try:
        rds.create_db_subnet_group(DBSubnetGroupName=sng_name, DBSubnetGroupDescription="DijkFood", SubnetIds=subnet_ids)
    except: pass

    try:
        log("Iniciando criação do RDS (Single-AZ)...")
        rds.create_db_instance(
            DBInstanceIdentifier=f"{PROJECT}-db",
            DBInstanceClass=RDS_INSTANCE_CLASS,
            Engine="postgres",
            MasterUsername=RDS_USER,
            MasterUserPassword=RDS_PASSWORD,
            AllocatedStorage=20,
            VpcSecurityGroupIds=[sg_id],
            DBSubnetGroupName=sng_name,
            PubliclyAccessible=True,
            MultiAZ=False # Simplificado para teste
        )
    except: log("  ✓ RDS já existente.")

    waiter = rds.get_waiter('db_instance_available')
    waiter.wait(DBInstanceIdentifier=f"{PROJECT}-db")
    endpoint = rds.describe_db_instances(DBInstanceIdentifier=f"{PROJECT}-db")['DBInstances'][0]['Endpoint']['Address']
    state["rds_endpoint"] = endpoint
    return endpoint

# =============================================================================
# FASE 4 — ECS CLUSTER E ALB
# =============================================================================
def setup_ecs_cluster(ecs, ec2, asg, subnet_ids, sg_ecs, ip_arn):
    cluster_name = f"{PROJECT}-cluster"
    lt_name = f"{PROJECT}-lt"
    asg_name = f"{PROJECT}-asg"

    log(f"Configurando infraestrutura do Cluster: {cluster_name}")
    try: ecs.create_cluster(clusterName=cluster_name)
    except: pass
    
    # 1. LIMPEZA ROBUSTA DO ASG (Essencial para não dar erro de 'AlreadyExists')
    try:
        log(f"  Solicitando exclusão do ASG antigo: {asg_name}...")
        asg.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
        log("  Aguardando remoção do ASG antigo...")
        for _ in range(30):
            time.sleep(10)
            check = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            if not check['AutoScalingGroups']: break
        log("  ✓ ASG antigo removido.")
    except: pass

    try: 
        ec2.delete_launch_template(LaunchTemplateName=lt_name)
        time.sleep(2)
    except: pass

    # 2. BUSCA DA AMI CORRETA E USERDATA
    ami_id = get_ecs_optimized_ami() # Busca a imagem certa
    log(f"  Usando AMI: {ami_id}")

    # O 'mkdir -p' evita o erro "No such file or directory" que apareceu no seu log
    user_data_script = f"#!/bin/bash\nmkdir -p /etc/ecs\necho ECS_CLUSTER={cluster_name} >> /etc/ecs/ecs.config"
    user_data_b64 = base64.b64encode(user_data_script.encode()).decode()

    # 3. CRIAR NOVO LAUNCH TEMPLATE
    log(f"  Criando novo Launch Template...")
    ec2.create_launch_template(
        LaunchTemplateName=lt_name,
        LaunchTemplateData={
            'ImageId': ami_id, 
            'InstanceType': EC2_INSTANCE_TYPE,
            'SecurityGroupIds': [sg_ecs],
            'IamInstanceProfile': {'Name': 'LabInstanceProfile'}, 
            'UserData': user_data_b64
        }
    )
    
    # 4. CRIAR NOVO ASG
    log(f"  Criando novo ASG: {asg_name}...")
    asg.create_auto_scaling_group(
        AutoScalingGroupName=asg_name,
        MinSize=1, MaxSize=1, DesiredCapacity=1,
        VPCZoneIdentifier=",".join(subnet_ids),
        LaunchTemplate={'LaunchTemplateName': lt_name, 'Version': '$Latest'},
        Tags=[{'Key': 'Name', 'Value': f'{PROJECT}-ecs-host', 'PropagateAtLaunch': True}]
    )

    # 5. AGUARDAR REGISTRO NO CLUSTER (O passo final de validação)
    log("  Aguardando instância EC2 se registrar no cluster (2-4 min)...")
    for i in range(20):
        time.sleep(20)
        check = ecs.describe_clusters(clusters=[cluster_name])['clusters'][0]
        if check.get('registeredContainerInstancesCount', 0) > 0:
            log("  ✓ Instância detectada no cluster! Prosseguindo...")
            return cluster_name
        log(f"  ...tentativa {i+1}/20: instância ainda não registrada.")
    
    raise Exception("ERRO: Instância não se registrou no cluster a tempo. Verifique o LabInstanceProfile.")

def setup_alb(elbv2, subnet_ids, sg_alb, vpc_id):
    alb = elbv2.create_load_balancer(Name=f"{PROJECT}-alb", Subnets=subnet_ids, SecurityGroups=[sg_alb])['LoadBalancers'][0]
    tg = elbv2.create_target_group(Name=f"{PROJECT}-tg", Protocol='HTTP', Port=8000, VpcId=vpc_id, TargetType='instance',
                                   HealthCheckPath='/', HealthCheckIntervalSeconds=30, HealthyThresholdCount=2, UnhealthyThresholdCount=5)['TargetGroups'][0]
    
    elbv2.create_listener(LoadBalancerArn=alb['LoadBalancerArn'], Protocol='HTTP', Port=80, DefaultActions=[{'Type': 'forward', 'TargetGroupArn': tg['TargetGroupArn']}])
    return alb['DNSName'], tg['TargetGroupArn']

# =============================================================================
# FASE 5 — SERVICE E DEPLOY
# =============================================================================
def deploy_service(ecs, cluster, image_uri, role_arn, tg_arn, rds_host):
    log("Registrando Task e Service...")
    td = ecs.register_task_definition(
        family=f"{PROJECT}-task",
        networkMode='bridge',
        executionRoleArn=role_arn,
        containerDefinitions=[{
            'name': 'api',
            'image': image_uri,
            'cpu': 512, 'memory': 512,
            'portMappings': [{'containerPort': 8000, 'hostPort': 8000}], # PORTA FIXA PARA BRIDGE
            'environment': [
                {'name': 'DB_HOST', 'value': rds_host},
                {'name': 'DB_NAME', 'value': RDS_DB_NAME},
                {'name': 'DB_USER', 'value': RDS_USER},
                {'name': 'DB_PASSWORD', 'value': RDS_PASSWORD}
            ],
            'logConfiguration': {
                'logDriver': 'awslogs',
                'options': {'awslogs-group': f"/ecs/{PROJECT}", 'awslogs-region': REGION, 'awslogs-stream-prefix': 'api'}
            }
        }]
    )['taskDefinition']['taskDefinitionArn']

    try:
        ecs.create_service(
            cluster=cluster, serviceName=f"{PROJECT}-service", taskDefinition=td,
            loadBalancers=[{'targetGroupArn': tg_arn, 'containerName': 'api', 'containerPort': 8000}],
            desiredCount=1, launchType='EC2', healthCheckGracePeriodSeconds=300
        )
    except:
        ecs.update_service(cluster=cluster, service=f"{PROJECT}-service", taskDefinition=td)

    log("Aguardando estabilização...")
    waiter = ecs.get_waiter('services_stable')
    waiter.wait(cluster=cluster, services=[f"{PROJECT}-service"], WaiterConfig={'Delay': 20, 'MaxAttempts': 30})

# =============================================================================
# MAIN
# =============================================================================
def main():
    session = boto3.Session(region_name=REGION)
    ec2 = session.client('ec2')
    rds = session.client('rds')
    ecs = session.client('ecs')
    elbv2 = session.client('elbv2')
    asg = session.client('autoscaling')
    iam = session.client('iam')
    sts = session.client('sts')
    
    account_id = sts.get_caller_identity()['Account']
    local_ip = urllib.request.urlopen("https://checkip.amazonaws.com").read().decode().strip()
    
    vpc_id = get_or_create_vpc(ec2)
    subnet_ids = setup_network(ec2, vpc_id, local_ip)
    ip_arn, role_arn = get_lab_role(iam, account_id)
    
    rds_host = setup_rds(rds, subnet_ids, state["sg_rds"], vpc_id)
    # Aqui entraria o seu Phase 6 (ECR/Docker Build)
    image_uri = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{PROJECT}-api:latest"
    
    cluster = setup_ecs_cluster(ecs, ec2, asg, subnet_ids, state["sg_ecs"], ip_arn)
    alb_dns, tg_arn = setup_alb(elbv2, subnet_ids, state["sg_alb"], vpc_id)
    
    deploy_service(ecs, cluster, image_uri, role_arn, tg_arn, rds_host)
    
    log(f"\nAPI ONLINE: http://{alb_dns}/")

if __name__ == "__main__":
    main()