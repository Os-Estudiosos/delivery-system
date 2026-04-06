"""
deploy_ecr.py — Cria e destrói o repositório ECR do DijkFood.

Também faz build local da imagem Docker da API e push para o ECR.

Pode ser executado de forma independente para fins de teste:
  python -m deploy.deploy_ecr
"""

import base64
import os
import subprocess
from pathlib import Path

import boto3

from .config import PROJECT, REGION

_DEFAULT_IMAGE_TAG = os.getenv("IMAGE_TAG", "latest")
_DEFAULT_DOCKERFILE = os.getenv("DOCKERFILE_PATH", "Dockerfile")


def _ecr():
    return boto3.client("ecr", region_name=REGION)


def _log(msg: str) -> None:
    print(f"[ecr] {msg}")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create(ctx: dict) -> dict:
    """Cria o repositório ECR, publica imagem e retorna URIs."""
    ecr        = _ecr()
    account_id = _get_account_id()
    repo_uri   = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{PROJECT}"
    image_tag  = str(ctx.get("image_tag") or _DEFAULT_IMAGE_TAG)
    image_uri  = f"{repo_uri}:{image_tag}"

    try:
        ecr.create_repository(
            repositoryName=PROJECT,
            imageScanningConfiguration={"scanOnPush": False},
            imageTagMutability="MUTABLE",
        )
        _log(f"repositório '{PROJECT}' criado.")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        _log(f"repositório '{PROJECT}' já existe, reutilizando.")

    _docker_login(ecr, account_id)
    _build_and_push_image(repo_uri, image_tag)

    _log("pronto.")
    return {
        "account_id": account_id,
        "repo_uri":   repo_uri,
        "image_tag":  image_tag,
        "image_uri":  image_uri,
    }


def _get_account_id() -> str:
    sts = boto3.client("sts", region_name=REGION)
    return sts.get_caller_identity()["Account"]


def _docker_login(ecr, account_id: str) -> None:
    token_data = ecr.get_authorization_token(registryIds=[account_id])["authorizationData"][0]
    auth_token = token_data["authorizationToken"]
    proxy_endpoint = token_data["proxyEndpoint"].replace("https://", "")
    _, password = base64.b64decode(auth_token).decode("utf-8").split(":", 1)

    _run_cmd(
        ["docker", "login", "--username", "AWS", "--password-stdin", proxy_endpoint],
        input_text=password,
    )
    _log(f"docker autenticado no registry {proxy_endpoint}.")


def _build_and_push_image(repo_uri: str, image_tag: str) -> None:
    root_dir = Path(__file__).resolve().parents[1]
    dockerfile_path = root_dir / _DEFAULT_DOCKERFILE
    if not dockerfile_path.exists():
        raise FileNotFoundError(f"Dockerfile não encontrado: {dockerfile_path}")

    local_tag = f"{PROJECT}:{image_tag}"
    remote_tag = f"{repo_uri}:{image_tag}"

    _log(f"build da imagem local '{local_tag}' usando '{dockerfile_path.name}'...")
    _run_cmd([
        "docker", "build",
        "-f", str(dockerfile_path),
        "-t", local_tag,
        str(root_dir),
    ])

    _log(f"tagging '{local_tag}' -> '{remote_tag}'...")
    _run_cmd(["docker", "tag", local_tag, remote_tag])

    _log(f"push da imagem '{remote_tag}'...")
    _run_cmd(["docker", "push", remote_tag])


def _run_cmd(args: list[str], input_text: str | None = None) -> None:
    try:
        subprocess.run(
            args,
            check=True,
            text=True,
            input=input_text,
        )
    except FileNotFoundError as e:
        cmd = args[0] if args else "comando"
        raise RuntimeError(f"'{cmd}' não está instalado ou não está no PATH.") from e
    except subprocess.CalledProcessError as e:
        cmd_str = " ".join(args)
        raise RuntimeError(f"Falha ao executar: {cmd_str}") from e


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
