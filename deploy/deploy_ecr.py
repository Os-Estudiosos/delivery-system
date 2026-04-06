"""
deploy_ecr.py — Cria e destrói o repositório ECR do DijkFood.

O build e push da imagem real são feitos separadamente quando a API
estiver pronta para produção (TODO).

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_ecr
"""

import boto3

from .config import PROJECT, REGION


def _ecr():
    return boto3.client("ecr", region_name=REGION)


def _log(msg: str) -> None:
    print(f"[ecr] {msg}")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create(ctx: dict) -> dict:
    """Cria o repositório ECR e retorna a URI."""
    ecr        = _ecr()
    account_id = _get_account_id()
    repo_uri   = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{PROJECT}"

    try:
        ecr.create_repository(
            repositoryName=PROJECT,
            imageScanningConfiguration={"scanOnPush": False},
            imageTagMutability="MUTABLE",
        )
        _log(f"repositório '{PROJECT}' criado.")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        _log(f"repositório '{PROJECT}' já existe, reutilizando.")

    _log("pronto.")
    return {
        "account_id": account_id,
        "repo_uri":   repo_uri,
    }


def _get_account_id() -> str:
    sts = boto3.client("sts", region_name=REGION)
    return sts.get_caller_identity()["Account"]


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def destroy(ctx: dict) -> None:
    """Remove o repositório ECR e todas as imagens."""
    ecr = _ecr()
    try:
        ecr.delete_repository(repositoryName=PROJECT, force=True)
        _log(f"repositório '{PROJECT}' deletado.")
    except ecr.exceptions.RepositoryNotFoundException:
        _log(f"repositório '{PROJECT}' não encontrado, nada a deletar.")
    except Exception as e:
        _log(f"aviso ao deletar repositório: {e}")


# ---------------------------------------------------------------------------
# Execução direta (teste isolado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=== Criando repositório ECR ===")
    result = create({})
    print(json.dumps(result, indent=2))

    input("\nPressione Enter para destruir o repositório...")
    destroy(result)
