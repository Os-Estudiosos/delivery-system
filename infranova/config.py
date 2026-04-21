REGION = "us-east-1"
PROJECT = "dijkfood-v2"
APP_PORT = 8000

# Essa é a restrição de ouro do seu laboratório:
LAB_ROLE_ARN = "arn:aws:iam::aws:policy/LabRole" 
LAB_ROLE_NAME = "LabRole"

def get_tags(name: str):
    return [
        {"Key": "Name", "Value": name},
        {"Key": "Project", "Value": PROJECT}
    ]