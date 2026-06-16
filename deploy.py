#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import shutil
import urllib.request
from pathlib import Path

# Configurações de Caminhos
ROOT_DIR = Path(__file__).parent.resolve()
TERRAFORM_DIR = ROOT_DIR / "infra" / "terraform" / "aws"
K8S_DIR = ROOT_DIR / "infra" / "k8s"


def print_step(title):
    print(f"\n==================================================")
    print(f"👉 {title}")
    print(f"==================================================")


def run_cmd(cmd, cwd=None, capture_output=True, shell=False):
    """Executa um comando no shell e trata erros. Logs de sucesso silenciados."""
    print(f"⏳ [EXEC] {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    
    res = subprocess.run(
        cmd,
        cwd=cwd,
        shell=shell or isinstance(cmd, str),
        capture_output=capture_output,
        text=True
    )
    if res.returncode != 0:
        print(f"\n❌ [ERRO] Falha ao executar: {cmd}")
        if capture_output:
            print("\n--- STDOUT (SAÍDA COMPLETA) ---")
            print(res.stdout)
            print("\n--- STDERR (ERROS COMPLETOS) ---")
            print(res.stderr)
        raise RuntimeError(f"Command failed with exit code {res.returncode}")
    return res.stdout


def get_terraform_outputs():
    """Lê as variáveis de saída do Terraform."""
    print("[TF] Lendo outputs...")
    out_json = run_cmd(["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True)
    outputs = json.loads(out_json)
    return {k: v["value"] for k, v in outputs.items()}


def main():
    parser = argparse.ArgumentParser(description="Orquestrador de Deploy & Destruição DijkFood AWS")
    parser.add_argument("--only-deploy", action="store_true", help="Apenas faz o deploy sem rodar simulação ou destruir")
    parser.add_argument("--only-destroy", action="store_true", help="Apenas destroi a infraestrutura existente na AWS")
    parser.add_argument("--no-destroy", action="store_true", help="Faz o deploy e roda simulação, mas NÃO destrói no final")
    args = parser.parse_args()

    # Valida binários necessários
    for binary in ["terraform", "docker", "kubectl", "aws"]:
        if not shutil.which(binary):
            print(f"\n❌ [ERRO] O executável '{binary}' não foi encontrado no PATH.")
            print(f"Por favor, certifique-se de que o '{binary}' está instalado e configurado corretamente.")
            sys.exit(1)

    # Obter Account ID do AWS CLI para configurar a LabRole dinâmica no AWS Academy Learner Lab
    try:
        account_id = subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            text=True
        ).strip()
        print(f"ℹ️ [AWS] Conta ativa identificada: {account_id}")
        lab_role_arn = f"arn:aws:iam::{account_id}:role/LabRole"
        os.environ["TF_VAR_eks_cluster_role_arn"] = lab_role_arn
        os.environ["TF_VAR_eks_node_role_arn"] = lab_role_arn
        print(f"ℹ️ [AWS] Configurando TF_VAR_eks_cluster_role_arn e TF_VAR_eks_node_role_arn com {lab_role_arn}")
    except Exception as e:
        print(f"⚠️ [AWS] Não foi possível detectar o ID da conta AWS automaticamente: {e}")

    # Solicita senha do banco RDS de forma segura se não fornecida
    import getpass
    db_password = os.environ.get("TF_VAR_db_password")
    if not db_password and not (TERRAFORM_DIR / "terraform.tfvars").exists():
        try:
            db_password = getpass.getpass("🔑 Digite a senha desejada para o banco de dados RDS: ").strip()
        except Exception:
            try:
                db_password = input("🔑 Digite a senha desejada para o banco de dados RDS: ").strip()
            except Exception:
                db_password = ""
        if not db_password:
            print("\n❌ [ERRO] A senha do banco de dados é obrigatória para o provisionamento do RDS.")
            sys.exit(1)
        os.environ["TF_VAR_db_password"] = db_password

    # Se a flag for apenas destruir, executa e encerra
    if args.only_destroy:
        print_step("Iniciando Destruição (Teardown) Completa na AWS")
        run_cmd(["terraform", "destroy", "-auto-approve"], cwd=TERRAFORM_DIR)
        print("\n✅ Teardown finalizado com sucesso!")
        return

    try:
        # ── PASSO 1: Terraform Provisioning ──────────────────────────
        print_step("Passo 1: Provisionando recursos na AWS com Terraform")
        run_cmd(["terraform", "init"], cwd=TERRAFORM_DIR)
        run_cmd(["terraform", "apply", "-auto-approve"], cwd=TERRAFORM_DIR)
        
        # Obter dados de saída (ECR urls, EKS cluster name, etc.)
        tf_outputs = get_terraform_outputs()
        eks_cluster_name = tf_outputs.get("eks_cluster_name", "dijkfood")
        aws_region = tf_outputs.get("aws_region", "us-east-1")
        
        # Salva o contexto para o simulador
        # deploy_context.json será populado com o hostname real do LoadBalancer
        # após a instalação do NGINX Ingress Controller (ver adiante neste script).

        # ── PASSO 2: Build & Push de Imagens Docker para o ECR ──────────
        print_step("Passo 2: Build & Push das Imagens Docker para o ECR")
        
        # Login no AWS ECR
        print("[ECR] Efetuando login...")
        login_cmd = f"aws ecr get-login-password --region {aws_region} | docker login --username AWS --password-stdin {tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com"
        run_cmd(login_cmd, shell=True)

        services = ["admin", "clients", "couriers", "matching", "orders", "restaurants", "positions", "simulator", "region"]
        for svc in services:
            print(f"\n[ECR] Processando serviço: {svc}")
            ecr_uri = f"{tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com/delivery-system/{svc}:latest"
            
            # Build
            if svc == "positions":
                run_cmd(["docker", "build", "-t", ecr_uri, "-f", "Dockerfile", "."], cwd=ROOT_DIR / "positions")
            else:
                dockerfile_path = f"{svc}/Dockerfile"
                run_cmd(["docker", "build", "-t", ecr_uri, "-f", dockerfile_path, "."], cwd=ROOT_DIR)
            
            # Push
            run_cmd(["docker", "push", ecr_uri], cwd=ROOT_DIR)

        # ── PASSO 3: Configurar Kubectl Context & Deploy no EKS ──────────
        print_step("Passo 3: Atualizando Kubeconfig e Deploying no EKS")
        run_cmd(["aws", "eks", "update-kubeconfig", "--region", aws_region, "--name", eks_cluster_name])

        # Aplica Namespace de Admin e Configs Globais
        run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "admin" / "namespace.yaml")])
        
        # Cria ConfigMap e Secrets de produção injetando variáveis reais da AWS (RDS, S3)
        rds_address = tf_outputs.get("rds_address", "")
        if not rds_address:
            print("❌ [AVISO] 'rds_address' não encontrado nos outputs do Terraform!")
            
        print("[K8s] Aplicando ConfigMaps com endpoints reais...")
        
        # Para admin-configmap.yaml
        admin_cm_path = K8S_DIR / "config" / "prod" / "admin-configmap.yaml"
        ecr_registry = f"{tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com"
        admin_cm_content = admin_cm_path.read_text().replace("<endpoint RDS>", rds_address)
        admin_cm_content += f"\n  ECR_REGISTRY: \"{ecr_registry}\"\n"
        
        assets_bucket = tf_outputs.get("assets_bucket_name", "")
        datalake_bucket = tf_outputs.get("datalake_bucket_name", "")
        if assets_bucket:
            admin_cm_content += f"  S3_BUCKET: \"{assets_bucket}\"\n"
        if datalake_bucket:
            admin_cm_content += f"  DATALAKE_BUCKET: \"{datalake_bucket}\"\n"

        temp_admin_cm = K8S_DIR / "config" / "prod" / "temp-admin-configmap.yaml"
        temp_admin_cm.write_text(admin_cm_content)
        run_cmd(["kubectl", "apply", "-f", str(temp_admin_cm)])
        temp_admin_cm.unlink()
        


        # Cria app-secret com credenciais reais do RDS na admin-namespace
        db_password = os.environ.get("TF_VAR_db_password", "")
        print("[K8s] Criando segredo app-secret na namespace do admin...")
        subprocess.run(["kubectl", "delete", "secret", "app-secret", "-n", "admin-namespace"], capture_output=True)
        
        # Carrega credenciais AWS locais para propagar aos pods
        import configparser
        aws_creds = {}
        aws_cred_path = Path.home() / ".aws" / "credentials"
        if aws_cred_path.exists():
            try:
                config = configparser.ConfigParser()
                config.read(aws_cred_path)
                profile = os.environ.get("AWS_PROFILE", "default")
                if profile in config:
                    if "aws_access_key_id" in config[profile]:
                        aws_creds["AWS_ACCESS_KEY_ID"] = config[profile]["aws_access_key_id"]
                    if "aws_secret_access_key" in config[profile]:
                        aws_creds["AWS_SECRET_ACCESS_KEY"] = config[profile]["aws_secret_access_key"]
                    if "aws_session_token" in config[profile]:
                        aws_creds["AWS_SESSION_TOKEN"] = config[profile]["aws_session_token"]
            except Exception as e:
                print(f"[K8s] Aviso: falha ao ler ~/.aws/credentials: {e}")
        
        # Fallback para variáveis de ambiente locais
        for k in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
            if k in os.environ:
                aws_creds[k] = os.environ[k]
                
        secret_cmd = [
            "kubectl", "create", "secret", "generic", "app-secret",
            "-n", "admin-namespace",
            "--from-literal=DB_USER=dijkfood",
            f"--from-literal=DB_PASSWORD={db_password}"
        ]
        for k, v in aws_creds.items():
            secret_cmd.append(f"--from-literal={k}={v}")
            
        run_cmd(secret_cmd)

        # Criar a Secret com credenciais temporárias no namespace kube-system para o Cluster Autoscaler
        secret_cmd_sys = [
            "kubectl", "create", "secret", "generic", "app-secret",
            "-n", "kube-system",
            "--from-literal=DB_USER=dijkfood",
            f"--from-literal=DB_PASSWORD={db_password}"
        ]
        for k, v in aws_creds.items():
            secret_cmd_sys.append(f"--from-literal={k}={v}")
            
        subprocess.run(["kubectl", "delete", "secret", "app-secret", "-n", "kube-system"], capture_output=True)
        run_cmd(secret_cmd_sys)

        # Deploy do Cluster Autoscaler no kube-system
        print("[K8s] Implantando Cluster Autoscaler no namespace kube-system...")
        run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "admin" / "cluster-autoscaler.yaml")])

        print("[K8s] Instalando Metrics Server (necessário para o HPA funcionar)...")
        run_cmd(["kubectl", "apply", "-f", "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"])
        # Patch para garantir que funcione no EKS sem erros de certificado
        run_cmd(["kubectl", "patch", "deployment", "metrics-server", "-n", "kube-system", "--type=json", "-p", '[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'])

        # Inicializa o esquema de tabelas (DDL.sql) no RDS
        print("[K8s] Inicializando esquema do banco de dados RDS (DDL.sql)...")
        subprocess.run(["kubectl", "delete", "pod", "db-init-temp", "-n", "admin-namespace"], capture_output=True)
        run_cmd([
            "kubectl", "run", "db-init-temp",
            "--image=postgres:16-alpine",
            "--restart=Never",
            "-n", "admin-namespace",
            f"--env=PGPASSWORD={db_password}",
            "--", "sleep", "3600"
        ])
        
        print("[K8s] Aguardando inicialização do pod temporário psql...")
        run_cmd([
            "kubectl", "wait", "--namespace", "admin-namespace",
            "--for=condition=ready", "pod/db-init-temp", "--timeout=60s"
        ])
        
        print("[K8s] Copiando scripts SQL para o pod...")
        run_cmd([
            "kubectl", "cp", "shared/database/sql/DROP.sql",
            "admin-namespace/db-init-temp:/tmp/DROP.sql"
        ])
        run_cmd([
            "kubectl", "cp", "shared/database/sql/DDL.sql",
            "admin-namespace/db-init-temp:/tmp/DDL.sql"
        ])
        
        print("[K8s] Executando comandos SQL no RDS...")
        run_cmd([
            "kubectl", "exec", "-n", "admin-namespace", "db-init-temp", "--",
            "psql", "-h", rds_address, "-U", "dijkfood", "-d", "dijkfood", "-f", "/tmp/DROP.sql"
        ])
        run_cmd([
            "kubectl", "exec", "-n", "admin-namespace", "db-init-temp", "--",
            "psql", "-h", rds_address, "-U", "dijkfood", "-d", "dijkfood", "-f", "/tmp/DDL.sql"
        ])
        
        print("[K8s] Removendo pod temporário psql...")
        subprocess.run(["kubectl", "delete", "pod", "db-init-temp", "-n", "admin-namespace"], capture_output=True)
        
        # Deploy dos componentes de Admin & Global consumer (positions)
        admin_yaml_content = (K8S_DIR / "admin" / "admin.yaml").read_text()
        admin_yaml_content = admin_yaml_content.replace("image: delivery-system/admin:latest", f"image: {ecr_registry}/delivery-system/admin:latest")
        temp_admin_yaml = K8S_DIR / "admin" / "temp-admin.yaml"
        temp_admin_yaml.write_text(admin_yaml_content)
        run_cmd(["kubectl", "apply", "-f", str(temp_admin_yaml)])
        temp_admin_yaml.unlink()

        positions_yaml_content = (K8S_DIR / "admin" / "positions.yaml").read_text()
        positions_yaml_content = positions_yaml_content.replace("image: delivery-system/positions:latest", f"image: {ecr_registry}/delivery-system/positions:latest")
        temp_positions_yaml = K8S_DIR / "admin" / "temp-positions.yaml"
        temp_positions_yaml.write_text(positions_yaml_content)
        run_cmd(["kubectl", "apply", "-f", str(temp_positions_yaml)])
        temp_positions_yaml.unlink()

        run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "admin" / "service-prod.yaml")])

        print("[K8s] Reiniciando deployments em admin-namespace para garantir atualização de imagens e secrets...")
        subprocess.run(["kubectl", "rollout", "restart", "deployment/admin", "-n", "admin-namespace"])
        subprocess.run(["kubectl", "rollout", "restart", "deployment/positions", "-n", "admin-namespace"])

        # Aguardar os pods do Admin estarem prontos
        print("[K8s] Aguardando inicialização do painel administrativo...")
        run_cmd([
            "kubectl", "wait", "--namespace", "admin-namespace",
            "--for=condition=ready", "pod", "--selector=app=admin", "--timeout=180s"
        ])

        # Instalar NGINX Ingress Controller e capturar o hostname do LoadBalancer
        print("[K8s] Instalando NGINX Ingress Controller no EKS...")
        run_cmd([
            "kubectl", "apply", "-f",
            "https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/aws/deploy.yaml"
        ])
        print("[K8s] Aguardando NGINX Ingress Controller ficar pronto...")
        run_cmd([
            "kubectl", "wait", "--namespace", "ingress-nginx",
            "--for=condition=ready", "pod",
            "--selector=app.kubernetes.io/component=controller",
            "--timeout=180s"
        ])

        # Aguarda o LoadBalancer receber um hostname externo (pode demorar até 2 minutos na AWS)
        print("[K8s] Aguardando hostname externo do LoadBalancer do NGINX Ingress...")
        ingress_hostname = ""
        for attempt in range(30):  # Max 5 minutos (30 x 10s)
            lb_raw = run_cmd(
                ["kubectl", "get", "svc", "ingress-nginx-controller",
                 "-n", "ingress-nginx",
                 "-o", "jsonpath={.status.loadBalancer.ingress[0].hostname}"],
                capture_output=True
            ).strip()
            if lb_raw:
                ingress_hostname = lb_raw
                print(f"\u2705 LoadBalancer hostname obtido: {ingress_hostname}")
                break
            print(f"   [K8s] Aguardando LoadBalancer... (tentativa {attempt+1}/30)")
            time.sleep(10)

        if not ingress_hostname:
            print("⚠️  Aviso: não foi possível obter o hostname do LoadBalancer. Simulador local usará URL vazia.")

        # Registra cidades na API
        cities_to_register = ["São Paulo, Brazil", "Russas, Ceará, Brazil"]
        namespaces = []
        try:
            # We port-forward the admin service port 4000 to talk to the API
            pf_cmd = ["kubectl", "port-forward", "-n", "admin-namespace", "svc/admin", "4000:4000"]
            pf_proc = subprocess.Popen(pf_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3) # Wait for port-forward to establish
            
            for city in cities_to_register:
                ns_name = None
                try:
                    city_payload = json.dumps({"name": city}).encode("utf-8")
                    req = urllib.request.Request(
                        "http://localhost:4000/city",
                        data=city_payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    print(f"[HTTP] Enviando requisição para cadastrar cidade '{city}'...")
                    with urllib.request.urlopen(req, timeout=120) as response:
                        resp_data = json.loads(response.read().decode("utf-8"))
                        ns_name = resp_data.get("namespace")
                        if ns_name:
                            namespaces.append(ns_name)
                            print(f"✅ Cidade '{city}' cadastrada! Namespace retornado: {ns_name}")
                except Exception as city_err:
                    print(f"⚠️ Aviso ao criar cidade '{city}' via API (pode já existir): {city_err}")
                    # Se falhou, vamos consultar as cidades cadastradas para descobrir o namespace correto
                    try:
                        with urllib.request.urlopen("http://localhost:4000/city", timeout=10) as response:
                            cities_list = json.loads(response.read().decode("utf-8"))
                            for c in cities_list:
                                if c.get("name", "").lower() == city.lower():
                                    ns_name = c.get("namespace")
                                    if ns_name:
                                        namespaces.append(ns_name)
                                        print(f"🔍 Encontrada cidade existente '{city}'. Namespace: {ns_name}")
                                        break
                    except Exception as list_err:
                        print(f"⚠️ Não foi possível listar cidades: {list_err}")
        finally:
            pf_proc.terminate()

        # Fallbacks se nenhuma foi cadastrada com sucesso
        if not namespaces:
            namespaces = ["city-1-s-o-paulo-brazil", "city-2-russas-cear-brazil"]

        # Persiste o último namespace no deploy_context.json para compatibilidade
        context_data = {"alb_dns": ingress_hostname, "city_namespace": namespaces[-1]}
        Path("deploy_context.json").write_text(json.dumps(context_data, indent=2))
        print(f"deploy_context.json atualizado: alb_dns={ingress_hostname}, city_namespace={namespaces[-1]}")

        for namespace_name in namespaces:
            print(f"[K8s] Reiniciando deployments no namespace {namespace_name}...")
            for deploy_name in ["clients", "couriers", "matching", "orders", "restaurants", "region"]:
                subprocess.run(["kubectl", "rollout", "restart", f"deployment/{deploy_name}", "-n", namespace_name])

        # Aguardar um momento para os pods começarem a subir nos namespaces
        print(f"[K8s] Aguardando inicialização do roteador (matching) nos namespaces...")
        time.sleep(10)
        for namespace_name in namespaces:
            try:
                run_cmd([
                    "kubectl", "wait", "--namespace", namespace_name, 
                    "--for=condition=ready", "pod", "--selector=app=matching", "--timeout=180s"
                ])
            except Exception as wait_err:
                print(f"⚠️ Aviso ao aguardar pod matching em {namespace_name}: {wait_err}. Continuando...")

        print("\n✅ Deploy concluído com sucesso!")
        if args.only_deploy:
            return

        # ── PASSO 4: Executar Simulador de Carga ──────────────────────
        print_step("Passo 4: Executando Simulador de Carga como K8s Jobs no EKS")
        simulator_image_uri = f"{tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com/delivery-system/simulator:latest"
        
        # We will run the load simulator for all registered namespaces
        # which are São Paulo (city-1-s-o-paulo-brazil) and Russas (city-2-russas-cear-brazil)
        namespaces_to_simulate = ["city-1-s-o-paulo-brazil", "city-2-russas-cear-brazil"]
        
        # Read simulator-job.yaml
        job_yaml_path = K8S_DIR / "admin" / "simulator-job.yaml"
        job_template = job_yaml_path.read_text()
        
        job_names = []
        temp_paths = []
        
        for idx, ns in enumerate(namespaces_to_simulate):
            job_name = f"load-simulator-{idx + 1}"
            sim_url = f"http://{ingress_hostname}"
            
            job_content = job_template
            job_content = job_content.replace("name: load-simulator", f"name: {job_name}")
            job_content = job_content.replace("<SIMULATOR_IMAGE_URI>", simulator_image_uri)
            job_content = job_content.replace("<TARGET_URL>", sim_url)
            job_content = job_content.replace("<CITY_NAMESPACE>", ns)
            
            # Write to a temp file and apply
            temp_job_path = K8S_DIR / "admin" / f"temp-{job_name}.yaml"
            temp_job_path.write_text(job_content)
            temp_paths.append(temp_job_path)
            job_names.append(job_name)
            
            # Delete any existing simulator job first
            subprocess.run(["kubectl", "delete", "job", job_name, "-n", "admin-namespace"], capture_output=True)
            
        try:
            # Apply all Jobs
            for temp_path in temp_paths:
                run_cmd(["kubectl", "apply", "-f", str(temp_path)])
                
            # Stream logs and wait for completion of all jobs
            log_processes = []
            pod_names = {}
            
            print("[K8s] Aguardando os Jobs do simulador iniciarem...")
            time.sleep(5)
            
            for job_name in job_names:
                pod_name = ""
                for _ in range(30):
                    pods_out = run_cmd(["kubectl", "get", "pods", "-n", "admin-namespace", "-l", f"job-name={job_name}", "-o", "jsonpath={.items[0].metadata.name}"], capture_output=True)
                    if pods_out.strip():
                        pod_name = pods_out.strip()
                        break
                    time.sleep(2)
                if pod_name:
                    pod_names[job_name] = pod_name
                    print(f"[K8s] Iniciando streaming de logs do Pod {pod_name}...")
                    log_proc = subprocess.Popen(["kubectl", "logs", "-n", "admin-namespace", pod_name, "-f"])
                    log_processes.append(log_proc)
            
            # Wait for all jobs to complete
            print("[K8s] Monitorando execução dos simuladores...")
            active_jobs = list(job_names)
            start_wait = time.time()
            
            while active_jobs and (time.time() - start_wait < 900): # max 15 minutes
                still_active = []
                for job_name in active_jobs:
                    job_res = subprocess.run(["kubectl", "get", "job", job_name, "-n", "admin-namespace", "-o", "json"], capture_output=True, text=True)
                    job_json = job_res.stdout if job_res.returncode == 0 else "{}"
                    job_status = json.loads(job_json).get("status", {})
                    if job_status.get("succeeded", 0) > 0:
                        print(f"\n✅ Simulação de carga do job '{job_name}' concluída com sucesso!")
                    elif job_status.get("failed", 0) > 0:
                        raise RuntimeError(f"O Job do simulador '{job_name}' falhou.")
                    else:
                        still_active.append(job_name)
                active_jobs = still_active
                if active_jobs:
                    time.sleep(5)
            
            if active_jobs:
                raise RuntimeError("Tempo limite de execução dos simuladores excedido.")
                
            # Terminate log processes
            for lp in log_processes:
                lp.terminate()

            # ── PASSO 4.5: Formatar Arquivos S3 para NDJSON ──────────────────
            print("\n[S3] Formatando arquivos de log do S3 para o formato JSON Lines (NDJSON)...")
            s3_clean_script = f"""
import boto3
s3 = boto3.client('s3', region_name='{aws_region}')
bucket = '{datalake_bucket}'
paginator = s3.get_paginator('list_objects_v2')
pages = paginator.paginate(Bucket=bucket, Prefix='events/')
files_processed = 0
for page in pages:
    if 'Contents' not in page:
        continue
    for obj in page['Contents']:
        key = obj['Key']
        if key.endswith('/'):
            continue
        resp = s3.get_object(Bucket=bucket, Key=key)
        content = resp['Body'].read().decode('utf-8', errors='ignore')
        formatted = content.replace('}}{{', '}}\\n{{')
        if formatted != content:
            s3.put_object(Bucket=bucket, Key=key, Body=formatted.encode('utf-8'))
            files_processed += 1
print(f"Formatados {{files_processed}} arquivos com sucesso!")
"""
            try:
                subprocess.run([
                    "uv", "run", "--with", "boto3", "python", "-c", s3_clean_script
                ], check=True)
                print("[S3] Formatação concluída!")
            except Exception as s3_err:
                print(f"⚠️ Aviso ao formatar arquivos S3: {s3_err}")
                
        finally:
            # Cleanup temp files and jobs
            for temp_path in temp_paths:
                if temp_path.exists():
                    temp_path.unlink()
            for job_name in job_names:
                pass
                # print(f"[K8s] Removendo Job {job_name}...")
                # subprocess.run(["kubectl", "delete", "job", job_name, "-n", "admin-namespace"], capture_output=True)

    except Exception as e:
        print(f"\n❌ [CRÍTICO] Falha na orquestração: {e}")
        print("[Aviso] A destruição automática foi desativada para manter o ambiente online para depuração.")
        sys.exit(1)

    # ── PASSO 5: Teardown Automático (Final) ────────────────────────
    if not args.no_destroy:
        print_step("Passo 5: Destruindo recursos (Teardown) para economizar custos")
        run_cmd(["terraform", "destroy", "-auto-approve"], cwd=TERRAFORM_DIR)
        print("\n✅ Infraestrutura AWS desmontada com sucesso!")
    else:
        print("\n⚠️ Infraestrutura preservada para fins de demonstração/depuração.")


if __name__ == "__main__":
    main()
