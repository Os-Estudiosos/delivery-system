# infra_nova/02_databases.py
import boto3
import time
from infranova import config
from botocore.exceptions import ClientError

s3 = boto3.client('s3', region_name=config.REGION)
dynamodb = boto3.resource('dynamodb', region_name=config.REGION)
rds = boto3.client('rds', region_name=config.REGION)
sts = boto3.client('sts')

# Configurações
ACCOUNT_ID = sts.get_caller_identity()["Account"]
BUCKET_NAME = f"{config.PROJECT}-osm-data-{ACCOUNT_ID}"
DYNAMO_TABLE = f"{config.PROJECT}-Positions"
DB_ID = f"{config.PROJECT}-db"
SUBNET_GROUP = f"{config.PROJECT}-db-subnet-group"

def setup_databases(network_context: dict):
    print("\n--- 2. Configurando Banco de Dados e Storage ---")
    results = {}

    # 1. Criar Bucket S3 (Para armazenar o grafo .graphml)
    try:
        print(f"Criando S3 Bucket: {BUCKET_NAME}...")
        s3.create_bucket(Bucket=BUCKET_NAME)
        print("S3 Bucket criado com sucesso.")
    except ClientError as e:
        if e.response['Error']['Code'] in ['BucketAlreadyOwnedByYou', 'BucketAlreadyExists']:
            print("S3 Bucket já existe e está pronto.")
        else:
            raise e
    results['bucket_name'] = BUCKET_NAME

    # 2. Criar Tabela DynamoDB (Para rastreio em tempo real)
    try:
        print(f"Criando Tabela DynamoDB: {DYNAMO_TABLE}...")
        table = dynamodb.create_table(
            TableName=DYNAMO_TABLE,
            KeySchema=[
                {'AttributeName': 'order_id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'order_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'N'}
            ],
            ProvisionedThroughput={'ReadCapacityUnits': 50, 'WriteCapacityUnits': 200}
        )
        print("Aguardando ativação da tabela DynamoDB...")
        table.meta.client.get_waiter('table_exists').wait(TableName=DYNAMO_TABLE)
        print("Tabela DynamoDB pronta.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print("Tabela DynamoDB já existe e está pronta.")
        else:
            raise e
    results['dynamo_table'] = DYNAMO_TABLE

    # 3. Criar Subnet Group do RDS
    try:
        print(f"Criando DB Subnet Group: {SUBNET_GROUP}...")
        rds.create_db_subnet_group(
            DBSubnetGroupName=SUBNET_GROUP,
            DBSubnetGroupDescription="Subnets para o DijkFood",
            SubnetIds=network_context['subnet_ids']
        )
    except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
        print("DB Subnet Group já existe.")

    # 4. Criar Instância RDS (PostgreSQL com Multi-AZ)
    try:
        print(f"Criando Instância RDS PostgreSQL ({DB_ID})...")
        print("Aviso: O provisionamento do RDS leva cerca de 5 a 10 minutos.")
        rds.create_db_instance(
            DBInstanceIdentifier=DB_ID,
            DBName="dijkfood",
            DBInstanceClass="db.t3.micro",
            Engine="postgres",
            EngineVersion="17.4",
            MasterUsername="postgres",
            MasterUserPassword="postgres_admin_pwd", # Ideal usar Secrets Manager em prod
            VpcSecurityGroupIds=[network_context['rds_sg_id']],
            DBSubnetGroupName=SUBNET_GROUP,
            MultiAZ=True,  # CRÍTICO: Requisito de tolerância a falhas
            PubliclyAccessible=False,
            AllocatedStorage=20,
            StorageType="gp2"
        )
    except rds.exceptions.DBInstanceAlreadyExistsFault:
        print("Instância RDS já existe ou está sendo criada.")
    
    print("Aguardando instância RDS ficar disponível...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=DB_ID,
        WaiterConfig={"Delay": 30, "MaxAttempts": 40}
    )
    
    instance_info = rds.describe_db_instances(DBInstanceIdentifier=DB_ID)['DBInstances'][0]
    endpoint = instance_info['Endpoint']['Address']
    print(f"RDS disponível no endpoint: {endpoint}")
    
    results['db_endpoint'] = endpoint
    return results

if __name__ == "__main__":
    # Bloco para testar o script isoladamente
    ec2 = boto3.client('ec2', region_name=config.REGION)
    vpc_id = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])['Vpcs'][0]['VpcId']
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])['Subnets']
    
    # Busca o SG do RDS criado no passo 1
    sgs = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [f"{config.PROJECT}-rds-sg"]}])
    rds_sg_id = sgs['SecurityGroups'][0]['GroupId']
    
    mock_network_ctx = {
        'subnet_ids': [s['SubnetId'] for s in subnets],
        'rds_sg_id': rds_sg_id
    }
    
    setup_databases(mock_network_ctx)