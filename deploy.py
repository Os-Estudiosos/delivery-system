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

    # Solicita senha do banco RDS de forma segura se não fornecida
    if "TF_VAR_db_password" not in os.environ and not (TERRAFORM_DIR / "terraform.tfvars").exists():
        import getpass
        try:
            password = getpass.getpass("🔑 Digite a senha desejada para o banco de dados RDS: ").strip()
        except Exception:
            try:
                password = input("🔑 Digite a senha desejada para o banco de dados RDS: ").strip()
            except Exception:
                password = ""
        if not password:
            print("\n❌ [ERRO] A senha do banco de dados é obrigatória para o provisionamento do RDS.")
            sys.exit(1)
        os.environ["TF_VAR_db_password"] = password

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

        # Registrar a cidade de Russas, Ceará para iniciar o deploy dinâmico
        print("[K8s] Registrando cidade 'Russas, Ceará, Brazil' no painel administrativo...")
        pf_proc = subprocess.Popen([
            "kubectl", "port-forward", "-n", "admin-namespace", "svc/admin", "4000:4000"
        ])
        time.sleep(5) # Aguarda port-forward estabelecer

        namespace_name = "city-1-russas-ceara-brazil" # fallback default
        try:
            city_payload = json.dumps({"name": "Russas, Ceará, Brazil"}).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:4000/city",
                data=city_payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            print("[HTTP] Enviando requisição para cadastrar cidade...")
            with urllib.request.urlopen(req, timeout=120) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                namespace_name = resp_data.get("namespace", namespace_name)
                print(f"✅ Cidade cadastrada! Namespace retornado: {namespace_name}")
        except Exception as city_err:
            print(f"⚠️ Aviso ao criar cidade via API (pode já existir): {city_err}")
            # Se falhou, vamos consultar as cidades cadastradas para descobrir o namespace correto
            try:
                with urllib.request.urlopen("http://localhost:4000/city", timeout=10) as response:
                    cities = json.loads(response.read().decode("utf-8"))
                    for c in cities:
                        if "russas" in c.get("name", "").lower():
                            namespace_name = c.get("namespace", namespace_name)
                            print(f"🔍 Encontrada cidade existente. Namespace: {namespace_name}")
                            break
            except Exception as list_err:
                print(f"⚠️ Não foi possível listar cidades: {list_err}. Usando namespace padrão: {namespace_name}")
        finally:
            pf_proc.terminate()

        # Persiste alb_dns e city_namespace DEPOIS de resolver o namespace real via API
        context_data = {"alb_dns": ingress_hostname, "city_namespace": namespace_name}
        Path("deploy_context.json").write_text(json.dumps(context_data, indent=2))
        print(f"deploy_context.json atualizado: alb_dns={ingress_hostname}, city_namespace={namespace_name}")

        print(f"[K8s] Reiniciando deployments no namespace dinâmico {namespace_name} para garantir atualização de imagens...")
        for deploy_name in ["clients", "couriers", "matching", "orders", "restaurants", "region"]:
            subprocess.run(["kubectl", "rollout", "restart", f"deployment/{deploy_name}", "-n", namespace_name])

        # Aguardar um momento para os pods da cidade começarem a subir no namespace dinâmico
        print(f"[K8s] Aguardando inicialização do roteador (matching) no namespace {namespace_name}...")
        time.sleep(10)
        try:
            run_cmd([
                "kubectl", "wait", "--namespace", namespace_name, 
                "--for=condition=ready", "pod", "--selector=app=matching", "--timeout=180s"
            ])
        except Exception as wait_err:
            print(f"⚠️ Aviso ao aguardar pod matching: {wait_err}. Continuando mesmo assim...")

        print("\n✅ Deploy concluído com sucesso!")
        if args.only_deploy:
            return

        # ── PASSO 4: Executar Simulador de Carga ──────────────────────
        print_step("Passo 4: Executando Simulador de Carga como K8s Job no EKS")
        sim_url = f"http://{namespace_name}.local"
        simulator_image_uri = f"{tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com/delivery-system/simulator:latest"
        
        # Read simulator-job.yaml
        job_yaml_path = K8S_DIR / "admin" / "simulator-job.yaml"
        job_content = job_yaml_path.read_text()
        # Replace placeholders
        job_content = job_content.replace("<SIMULATOR_IMAGE_URI>", simulator_image_uri)
        job_content = job_content.replace("<TARGET_URL>", sim_url)
        # Sobrescreve a linha de args para incluir os limites de tempo (20s) e RPS (200)
        job_content = job_content.replace(f'args: ["{sim_url}"]', f'args: ["{sim_url}", "--rps", "200", "--duration", "20"]')
        
        # Write to a temp file and apply
        temp_job_path = K8S_DIR / "admin" / "temp-simulator-job.yaml"
        temp_job_path.write_text(job_content)
        
        # Delete any existing simulator job first
        subprocess.run(["kubectl", "delete", "job", "load-simulator", "-n", "admin-namespace"], capture_output=True)
        
        try:
            # Apply the Job
            run_cmd(["kubectl", "apply", "-f", str(temp_job_path)])
            
            # Wait for the job pod to start and get its name
            print("[K8s] Aguardando o Job do simulador iniciar...")
            pod_name = ""
            for _ in range(30):
                pods_out = run_cmd(["kubectl", "get", "pods", "-n", "admin-namespace", "-l", "job-name=load-simulator", "-o", "jsonpath={.items[0].metadata.name}"], capture_output=True)
                if pods_out.strip():
                    pod_name = pods_out.strip()
                    break
                time.sleep(2)
                
            if not pod_name:
                raise RuntimeError("Pod do simulador de carga não foi criado a tempo.")
                
            print(f"[K8s] Streaming de logs do Pod {pod_name}...")
            # Stream logs in real time in background
            log_proc = subprocess.Popen(["kubectl", "logs", "-n", "admin-namespace", pod_name, "-f"])
            
            # Wait for job completion
            print("[K8s] Monitorando execução do simulador...")
            for _ in range(180): # max 15 minutes (180 * 5s)
                job_res = subprocess.run(["kubectl", "get", "job", "load-simulator", "-n", "admin-namespace", "-o", "json"], capture_output=True, text=True)
                job_json = job_res.stdout if job_res.returncode == 0 else "{}"
                job_status = json.loads(job_json).get("status", {})
                if job_status.get("succeeded", 0) > 0:
                    print("\n✅ Simulação de carga concluída com sucesso!")
                    break
                if job_status.get("failed", 0) > 0:
                    raise RuntimeError("O Job do simulador falhou durante a execução.")
                time.sleep(5)
            else:
                raise RuntimeError("Tempo limite de execução do simulador excedido.")
            
            # Terminate log streaming process
            log_proc.terminate()
        finally:
            # Cleanup temp file and job
            if temp_job_path.exists():
                temp_job_path.unlink()
            print("[K8s] Removendo Job do simulador...")
            subprocess.run(["kubectl", "delete", "job", "load-simulator", "-n", "admin-namespace"], capture_output=True)

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
