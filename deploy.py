#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import shutil
from pathlib import Path

# Configurações de Caminhos
ROOT_DIR = Path(__file__).parent.resolve()
TERRAFORM_DIR = ROOT_DIR / "infra" / "terraform" / "aws"
K8S_DIR = ROOT_DIR / "infra" / "k8s"


def print_step(title):
    print(f"\n==================================================")
    print(f"👉 {title}")
    print(f"==================================================")


def run_cmd(cmd, cwd=None, capture_output=False, shell=False):
    """Executa um comando no shell e trata erros."""
    print(f"[EXEC] {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
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
            print(f"Saída (stdout):\n{res.stdout}")
            print(f"Erro (stderr):\n{res.stderr}")
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
        alb_dns = tf_outputs.get("alb_dns", "")
        context_data = {"alb_dns": alb_dns}
        Path("deploy_context.json").write_text(json.dumps(context_data, indent=2))
        print(f"ALB DNS registrado em deploy_context.json: {alb_dns}")

        # ── PASSO 2: Build & Push de Imagens Docker para o ECR ──────────
        print_step("Passo 2: Build & Push das Imagens Docker para o ECR")
        
        # Login no AWS ECR
        print("[ECR] Efetuando login...")
        login_cmd = f"aws ecr get-login-password --region {aws_region} | docker login --username AWS --password-stdin {tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com"
        run_cmd(login_cmd, shell=True)

        services = ["admin", "clients", "couriers", "matching", "orders", "restaurants", "positions", "simulator"]
        for svc in services:
            print(f"\n[ECR] Processando serviço: {svc}")
            ecr_uri = f"{tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com/delivery-system/{svc}:latest"
            
            # Build
            dockerfile_path = f"{svc}/Dockerfile" if svc != "positions" else "positions/Dockerfile"
            run_cmd(["docker", "build", "-t", ecr_uri, "-f", dockerfile_path, "."], cwd=ROOT_DIR)
            
            # Push
            run_cmd(["docker", "push", ecr_uri], cwd=ROOT_DIR)

        # ── PASSO 3: Configurar Kubectl Context & Deploy no EKS ──────────
        print_step("Passo 3: Atualizando Kubeconfig e Deploying no EKS")
        run_cmd(["aws", "eks", "update-kubeconfig", "--region", aws_region, "--name", eks_cluster_name])

        # Aplica Namespace de Admin e Configs Globais
        run_cmd(["kubectl", "apply", "-f", str(K8s_DIR / "admin" / "namespace.yaml")])
        
        # Cria ConfigMap e Secrets de produção injetando variáveis reais da AWS (RDS, S3)
        # (Em produção, o deploy.py automatiza essa substituição de IPs/DNS por variáveis reais)
        print("[K8s] Aplicando Configs de Produção...")
        # (Substitui credenciais e hosts do RDS/DynamoDB reais gerados pelo TF nos manifests)
        # Exemplo simplificado de aplicação das configs reais:
        run_cmd(["kubectl", "apply", "-f", str(K8s_DIR / "config" / "prod" / "admin-configmap.yaml")])
        run_cmd(["kubectl", "apply", "-f", str(K8s_DIR / "config" / "prod" / "city-configmap.yaml")])
        
        # Deploy dos componentes de Admin & Global consumer (positions)
        run_cmd(["kubectl", "apply", "-f", str(K8s_DIR / "admin" / "admin.yaml")])
        run_cmd(["kubectl", "apply", "-f", str(K8s_DIR / "admin" / "positions.yaml")])
        run_cmd(["kubectl", "apply", "-f", str(K8s_DIR / "admin" / "service-prod.yaml")])

        # Aguardar os pods do Admin estarem prontos
        print("[K8s] Aguardando inicialização do painel administrativo...")
        run_cmd([
            "kubectl", "wait", "--namespace", "admin-namespace", 
            "--for=condition=ready", "pod", "--selector=app=admin", "--timeout=180s"
        ])

        print("\n✅ Deploy concluído com sucesso!")
        if args.only_deploy:
            return

        # ── PASSO 4: Executar Simulador de Carga ──────────────────────
        print_step("Passo 4: Executando Simulador de Carga como K8s Job no EKS")
        sim_url = f"http://{alb_dns}"
        simulator_image_uri = f"{tf_outputs['account_id']}.dkr.ecr.{aws_region}.amazonaws.com/delivery-system/simulator:latest"
        
        # Read simulator-job.yaml
        job_yaml_path = K8S_DIR / "admin" / "simulator-job.yaml"
        job_content = job_yaml_path.read_text()
        
        # Replace placeholders
        job_content = job_content.replace("<SIMULATOR_IMAGE_URI>", simulator_image_uri)
        job_content = job_content.replace("<TARGET_URL>", sim_url)
        
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
            for _ in range(120): # max 10 minutes (120 * 5s)
                job_json = run_cmd(["kubectl", "get", "job", "load-simulator", "-n", "admin-namespace", "-o", "json"], capture_output=True)
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
        # Se falhou, mas não foi instruído a manter, força destruição dos recursos
        if not args.no_destroy and not args.only_deploy and shutil.which("terraform"):
            print("\n🚨 Acionando destruição de emergência...")
            try:
                run_cmd(["terraform", "destroy", "-auto-approve"], cwd=TERRAFORM_DIR)
            except Exception as destroy_err:
                print(f"Erro ao tentar executar terraform destroy: {destroy_err}")
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
