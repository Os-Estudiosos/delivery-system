#!/usr/bin/env python3
import json
import boto3
import time
from pathlib import Path
from infranova import config

CTX_FILE = Path("deploy_context.json")

def destroy_all():
    if not CTX_FILE.exists():
        print("Arquivo de contexto não encontrado. Nada a destruir.")
        return

    ctx = json.loads(CTX_FILE.read_text())
    region = config.REGION
    
    ecs = boto3.client('ecs', region_name=region)
    elbv2 = boto3.client('elbv2', region_name=region)
    rds = boto3.client('rds', region_name=region)
    dynamodb = boto3.client('dynamodb', region_name=region)
    s3 = boto3.resource('s3', region_name=region)
    ec2 = boto3.client('ec2', region_name=region)

    print("Iniciando destruição da infraestrutura...\n")

    # 1. ECS (Zerar e Deletar Serviço)
    print("1. Apagando ECS Service...")
    try:
        ecs.update_service(cluster=f"{config.PROJECT}-cluster", service=f"{config.PROJECT}-service", desiredCount=0)
        time.sleep(60) # Espera os containers morrerem
        ecs.delete_service(cluster=f"{config.PROJECT}-cluster", service=f"{config.PROJECT}-service", force=True)
        ecs.delete_cluster(cluster=f"{config.PROJECT}-cluster")
    except Exception as e: print(f"Aviso ECS: {e}")

    # 2. ALB e Target Group
    print("2. Apagando Load Balancer...")
    try:
        alb_arn = elbv2.describe_load_balancers(Names=[f"{config.PROJECT}-alb"])['LoadBalancers'][0]['LoadBalancerArn']
        elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
        
        tg_arn = elbv2.describe_target_groups(Names=[f"{config.PROJECT}-tg"])['TargetGroups'][0]['TargetGroupArn']
        # ALB demora um pouco para liberar o TG
        time.sleep(15)
        elbv2.delete_target_group(TargetGroupArn=tg_arn)
    except Exception as e: print(f"Aviso ALB: {e}")

    # 3. RDS
    print("3. Apagando RDS (isso demora alguns minutos)...")
    try:
        rds.delete_db_instance(DBInstanceIdentifier=f"{config.PROJECT}-db", SkipFinalSnapshot=True)
        waiter = rds.get_waiter('db_instance_deleted')
        waiter.wait(DBInstanceIdentifier=f"{config.PROJECT}-db", WaiterConfig={"Delay": 30, "MaxAttempts": 40})
        rds.delete_db_subnet_group(DBSubnetGroupName=f"{config.PROJECT}-db-subnet-group")
    except Exception as e: print(f"Aviso RDS: {e}")

    # 4. DynamoDB e S3
    print("4. Apagando DynamoDB e S3...")
    try:
        dynamodb.delete_table(TableName=ctx['dynamo_table'])
    except Exception as e: print(f"Aviso Dynamo: {e}")
    
    try:
        bucket = s3.Bucket(ctx['bucket_name'])
        bucket.objects.all().delete() # Esvazia antes de deletar
        bucket.delete()
    except Exception as e: print(f"Aviso S3: {e}")

    # 5. Security Groups
    print("5. Apagando Security Groups...")
    try:
        ec2.delete_security_group(GroupId=ctx['rds_sg_id'])
        ec2.delete_security_group(GroupId=ctx['ecs_sg_id'])
        ec2.delete_security_group(GroupId=ctx['alb_sg_id'])
    except Exception as e: print(f"Aviso SGs: {e}")

    CTX_FILE.unlink()
    print("\nInfraestrutura totalmente destruída!")

if __name__ == "__main__":
    destroy_all()