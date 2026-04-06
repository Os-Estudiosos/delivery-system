#!/usr/bin/env python3
"""
deploy.py — Orquestrador de implantação DijkFood na AWS.

Fluxo completo (sem intervenção manual):
  1. Cria recursos:  VPC → ECR → RDS → DynamoDB → ECS
  2. Executa o simulador de carga
  3. Destrói todos os recursos

Uso:
  python deploy.py
"""

import json
import sys
from pathlib import Path
from dotenv import load_dotenv

from deploy import deploy_dynamodb, deploy_ecr, deploy_ecs, deploy_rds, deploy_vpc
from simulator.load_simulator import simulation

# Arquivo temporário para persistir o contexto entre etapas.
# Útil para depuração: se o script falhar, é possível inspecionar o que foi criado.
_CTX_FILE = Path("./temp/dijkfood_ctx.json")
load_dotenv()

# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------

def _save_ctx(ctx: dict) -> None:
    _CTX_FILE.write_text(json.dumps(ctx, indent=2))


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

def deploy() -> dict:
    """Cria todos os recursos AWS em ordem de dependência."""
    ctx = {}

    steps = [
        ("VPC",       deploy_vpc.create),
        ("ECR",       deploy_ecr.create),
        ("RDS",       deploy_rds.create),
        ("DynamoDB",  deploy_dynamodb.create),
        ("ECS",       deploy_ecs.create),
    ]

    for i, (name, create_fn) in enumerate(steps, start=1):
        print(f"\n=== [{i}/{len(steps)}] {name} ===")
        try:
            result = create_fn(ctx)
            ctx.update(result)
            _save_ctx(ctx)
        except Exception as e:
            print(f"\nErro ao criar {name}: {e}")
            print("Iniciando rollback dos recursos já criados...")
            destroy(ctx)
            sys.exit(1)

    print("\nDeploy concluído.")
    return ctx


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def destroy(ctx: dict) -> None:
    """Destrói todos os recursos em ordem inversa à criação."""
    print("\n=== Destruindo recursos ===")

    steps = [
        ("ECS",       deploy_ecs.destroy),
        ("DynamoDB",  deploy_dynamodb.destroy),
        ("RDS",       deploy_rds.destroy),
        ("ECR",       deploy_ecr.destroy),
        ("VPC",       deploy_vpc.destroy),
    ]

    for name, destroy_fn in steps:
        print(f"  → {name}")
        try:
            destroy_fn(ctx)
        except Exception as e:
            print(f"  aviso ao destruir {name}: {e}")

    _CTX_FILE.unlink(missing_ok=True)
    print("Recursos destruídos.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctx = deploy()
    api_url = ctx.get("api_url")

    try:
        print("\n=== Simulador de carga ===")
        print(f"API URL: {api_url}")
        simulation(api_url)
    finally:
        destroy(ctx)
