import boto3
import subprocess
import base64
from infranova import config

region = config.REGION
ecr = boto3.client('ecr', region_name=region)
ecs = boto3.client('ecs', region_name=region)
elbv2 = boto3.client('elbv2', region_name=region)
sts = boto3.client('sts')

ACCOUNT_ID = sts.get_caller_identity()["Account"]
REPO_NAME = f"{config.PROJECT}-repo"
CLUSTER_NAME = f"{config.PROJECT}-cluster"
LAB_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/{config.LAB_ROLE_NAME}"

def run_command(command: str):
    """Executa comandos no terminal (necessário para o Docker)."""
    print(f"Executando: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Erro no comando: {result.stderr}")
        raise Exception(f"Falha ao executar: {command}")
    return result.stdout.strip()

def setup_compute(network_ctx: dict, db_ctx: dict):
    print("\n--- 3. Configurando Compute (ECR, ALB e ECS) ---")
    results = {}

    # 1. ECR - Criar Repositório
    try:
        print(f"Criando repositório ECR: {REPO_NAME}...")
        repo_resp = ecr.create_repository(repositoryName=REPO_NAME)
        repo_uri = repo_resp['repository']['repositoryUri']
    except ecr.exceptions.RepositoryAlreadyExistsException:
        print("Repositório já existe.")
        repo_uri = f"{ACCOUNT_ID}.dkr.ecr.{region}.amazonaws.com/{REPO_NAME}"
    results['repo_uri'] = repo_uri

    # 2. Docker Build & Push (Sem intervenção manual)
    print("\nIniciando processo de Build e Push da imagem Docker...")
    # Autentica o Docker na AWS
    auth_data = ecr.get_authorization_token()['authorizationData'][0]
    token = base64.b64decode(auth_data['authorizationToken']).decode('utf-8').split(':')[1]
    run_command(f"docker login -u AWS -p {token} {repo_uri.split('/')[0]}")
    
    # Build e Push
    print("Fazendo o build da imagem (isso pode levar alguns minutos)...")
    run_command(f"docker build -t {REPO_NAME} .")
    run_command(f"docker tag {REPO_NAME}:latest {repo_uri}:latest")
    print("Fazendo push para o ECR...")
    run_command(f"docker push {repo_uri}:latest")

    # 3. Application Load Balancer (ALB)
    print("\nCriando Application Load Balancer...")
    alb_resp = elbv2.create_load_balancer(
        Name=f"{config.PROJECT}-alb",
        Subnets=network_ctx['subnet_ids'],
        SecurityGroups=[network_ctx['alb_sg_id']],
        Scheme='internet-facing',
        Type='application'
    )
    alb_arn = alb_resp['LoadBalancers'][0]['LoadBalancerArn']
    alb_dns = alb_resp['LoadBalancers'][0]['DNSName']
    
    tg_resp = elbv2.create_target_group(
        Name=f"{config.PROJECT}-tg",
        Protocol='HTTP', Port=config.APP_PORT, VpcId=network_ctx['vpc_id'],
        TargetType='ip', HealthCheckPath='/health' # A API DEVE ter uma rota /health
    )
    tg_arn = tg_resp['TargetGroups'][0]['TargetGroupArn']
    
    elbv2.create_listener(
        LoadBalancerArn=alb_arn, Protocol='HTTP', Port=80,
        DefaultActions=[{'Type': 'forward', 'TargetGroupArn': tg_arn}]
    )

    # 4. ECS Cluster e Task Definition
    print("\nCriando Cluster ECS e Task Definition...")
    ecs.create_cluster(clusterName=CLUSTER_NAME)

    task_def_resp = ecs.register_task_definition(
        family=f"{config.PROJECT}-task",
        networkMode='awsvpc',
        requiresCompatibilities=['FARGATE'],
        cpu='512', memory='1024',
        executionRoleArn=LAB_ROLE_ARN, # Obrigatório: LabRole
        taskRoleArn=LAB_ROLE_ARN,      # Obrigatório: LabRole
        containerDefinitions=[{
            'name': 'api-container',
            'image': f"{repo_uri}:latest",
            'essential': True,
            'portMappings': [{'containerPort': config.APP_PORT, 'protocol': 'tcp'}],
            'environment': [
                {'name': 'DB_HOST', 'value': db_ctx.get('db_endpoint', 'localhost')},
                {'name': 'S3_BUCKET', 'value': db_ctx.get('bucket_name', '')},
                {'name': 'DYNAMO_TABLE', 'value': db_ctx.get('dynamo_table', '')}
            ],
            'logConfiguration': {
                'logDriver': 'awslogs',
                'options': {
                    'awslogs-group': f"/ecs/{config.PROJECT}",
                    'awslogs-region': region,
                    'awslogs-stream-prefix': 'ecs',
                    'awslogs-create-group': 'true'
                }
            }
        }]
    )
    task_def_arn = task_def_resp['taskDefinition']['taskDefinitionArn']

    # 5. Criando o Serviço ECS
    print("\nCriando Serviço ECS (Iniciando containers)...")
    ecs.create_service(
        cluster=CLUSTER_NAME,
        serviceName=f"{config.PROJECT}-service",
        taskDefinition=task_def_arn,
        desiredCount=2, # Começa com 2 instâncias para demonstrar disponibilidade
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': network_ctx['subnet_ids'],
                'securityGroups': [network_ctx['ecs_sg_id']],
                'assignPublicIp': 'ENABLED' # Crítico para baixar imagem do ECR em VPC padrão
            }
        },
        loadBalancers=[{'targetGroupArn': tg_arn, 'containerName': 'api-container', 'containerPort': config.APP_PORT}]
    )

    print(f"\nDeploy do Compute finalizado!")
    print(f"DNS do Load Balancer (Acesse por aqui): http://{alb_dns}")
    
    results['alb_dns'] = alb_dns
    return results

if __name__ == "__main__":
    # Teste isolado do script (Requer Docker rodando na máquina)
    ec2 = boto3.client('ec2', region_name=config.REGION)
    vpc_id = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])['Vpcs'][0]['VpcId']
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])['Subnets']
    
    sgs = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])['SecurityGroups']
    get_sg = lambda name: next(sg['GroupId'] for sg in sgs if sg['GroupName'] == f"{config.PROJECT}-{name}")
    
    mock_net = {
        'vpc_id': vpc_id,
        'subnet_ids': [s['SubnetId'] for s in subnets],
        'alb_sg_id': get_sg('alb-sg'),
        'ecs_sg_id': get_sg('ecs-sg')
    }
    
    mock_db = {
        'db_endpoint': 'mock-db-endpoint.rds.amazonaws.com',
        'bucket_name': f'{config.PROJECT}-osm-data-{ACCOUNT_ID}',
        'dynamo_table': f'{config.PROJECT}-Positions'
    }
    
    setup_compute(mock_net, mock_db)