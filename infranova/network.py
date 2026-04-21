# infra_nova/01_network.py
import boto3
from infranova import config

ec2 = boto3.client('ec2', region_name=config.REGION)

def setup_network():
    print("--- 1. Configurando Rede e Security Groups ---")
    
    # 1. Busca a VPC Padrão
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    print(f"VPC Padrão encontrada: {vpc_id}")

    # 2. Busca as Subnets da VPC
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    subnet_ids = [s['SubnetId'] for s in subnets['Subnets']]
    print(f"Subnets encontradas: {len(subnet_ids)}")

    # 3. Cria Security Group do Load Balancer (Aberto para a Internet)
    alb_sg_resp = ec2.create_security_group(
        GroupName=f"{config.PROJECT}-alb-sg",
        Description="Permite trafego HTTP externo para o Load Balancer",
        VpcId=vpc_id
    )
    alb_sg_id = alb_sg_resp['GroupId']
    ec2.authorize_security_group_ingress(
        GroupId=alb_sg_id,
        IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}]
    )
    print(f"ALB Security Group criado: {alb_sg_id}")

    # 4. Cria Security Group do ECS (Recebe APENAS do Load Balancer)
    ecs_sg_resp = ec2.create_security_group(
        GroupName=f"{config.PROJECT}-ecs-sg",
        Description="Permite trafego do ALB para os containers ECS",
        VpcId=vpc_id
    )
    ecs_sg_id = ecs_sg_resp['GroupId']
    ec2.authorize_security_group_ingress(
        GroupId=ecs_sg_id,
        IpPermissions=[{
            'IpProtocol': 'tcp', 'FromPort': config.APP_PORT, 'ToPort': config.APP_PORT,
            'UserIdGroupPairs': [{'GroupId': alb_sg_id}]
        }]
    )
    print(f"ECS Security Group criado: {ecs_sg_id}")

    # 5. Cria Security Group do RDS (Recebe APENAS dos containers no ECS)
    rds_sg_resp = ec2.create_security_group(
        GroupName=f"{config.PROJECT}-rds-sg",
        Description="Permite trafego PostgreSQL do ECS",
        VpcId=vpc_id
    )
    rds_sg_id = rds_sg_resp['GroupId']
    ec2.authorize_security_group_ingress(
        GroupId=rds_sg_id,
        IpPermissions=[{
            'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432,
            'UserIdGroupPairs': [{'GroupId': ecs_sg_id}]
        }]
    )
    print(f"RDS Security Group criado: {rds_sg_id}")

    # Retorna o contexto para os próximos scripts usarem
    return {
        "vpc_id": vpc_id,
        "subnet_ids": subnet_ids,
        "alb_sg_id": alb_sg_id,
        "ecs_sg_id": ecs_sg_id,
        "rds_sg_id": rds_sg_id
    }

if __name__ == "__main__":
    try:
        network_context = setup_network()
        print("\nSucesso! A base da rede está pronta.")
    except Exception as e:
        print(f"\nErro ao configurar a rede: {e}")