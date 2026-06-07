terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ── AMI: Amazon Linux 2023 (mais recente) ────────────────────────────────────
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── Security Group: libera 8501 (Streamlit) e 22 (SSH) ───────────────────────
resource "aws_security_group" "dashboard" {
  name        = "dijkfood-dashboard-sg"
  description = "Streamlit dashboard - porta 8501 publica"

  ingress {
    description = "Streamlit"
    from_port   = 8501
    to_port     = 8501
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.common_tags
}

# ── EC2: instância com user_data que instala e sobe o Streamlit ───────────────
resource "aws_instance" "dashboard" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = var.ec2_instance_profile
  vpc_security_group_ids = [aws_security_group.dashboard.id]

  # user_data: roda na primeira inicialização
  # - instala Python + dependências
  # - baixa o dashboard_prod.py do S3
  # - sobe o Streamlit como serviço systemd
  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    aws_region       = var.aws_region
    athena_db        = var.athena_db
    athena_workgroup = var.athena_workgroup
    results_bucket   = var.results_bucket
    data_lake_bucket = var.data_lake_bucket
    dashboard_s3_key = var.dashboard_s3_key
  }))

  tags = merge(var.common_tags, {
    Name = "dijkfood-dashboard"
  })
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "dashboard_url" {
  value       = "http://${aws_instance.dashboard.public_ip}:8501"
  description = "URL pública do dashboard Streamlit"
}

output "instance_id" {
  value = aws_instance.dashboard.id
}

output "public_ip" {
  value = aws_instance.dashboard.public_ip
}
