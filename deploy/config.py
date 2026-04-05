REGION  = "us-east-1"
PROJECT = "dijkfood"

APP_PORT = 8000

# Nome da role pré-existente em qualquer conta AWS Academy
LAB_ROLE_NAME = "LabRole"


def tags(name: str) -> list[dict]:
    """Tags padrão aplicadas em todos os recursos criados."""
    return [
        {"Key": "Name",    "Value": name},
        {"Key": "Project", "Value": PROJECT},
    ]
