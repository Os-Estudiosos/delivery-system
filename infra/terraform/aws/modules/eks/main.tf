terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "cluster_name" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "eks_compatible" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "availabilityZone"
    values = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d", "us-east-1f"]
  }
}

resource "aws_eks_cluster" "dijkfood" {
  name     = var.cluster_name
  role_arn = "arn:aws:iam::043830376165:role/c213967a5408241l15083359t1w043830-LabEksClusterRole-UZqtrw4Ps35H"

  vpc_config {
    subnet_ids = data.aws_subnets.eks_compatible.ids
  }
}

resource "aws_eks_node_group" "dijkfood" {
  cluster_name    = aws_eks_cluster.dijkfood.name
  node_group_name = "${var.cluster_name}-nodes"
  node_role_arn   = "arn:aws:iam::043830376165:role/c213967a5408241l15083359t1w043830376-LabEksNodeRole-2x8ymceYyHcW"
  subnet_ids      = data.aws_subnets.eks_compatible.ids
  instance_types  = ["t3.small"]

  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 5
  }
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region us-east-1 --name ${var.cluster_name}"
}
