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
  name     = var.eks_cluster_name
  role_arn = var.eks_cluster_role_arn

  vpc_config {
    subnet_ids = data.aws_subnets.eks_compatible.ids
  }

  tags = var.common_tags
}

resource "aws_eks_node_group" "dijkfood" {
  cluster_name    = aws_eks_cluster.dijkfood.name
  node_group_name = "${var.eks_cluster_name}-nodes"
  node_role_arn   = var.eks_node_role_arn
  subnet_ids      = data.aws_subnets.eks_compatible.ids
  instance_types  = ["t3.small"]

  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 5
  }

  tags = var.common_tags
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.aws_region} --name ${var.eks_cluster_name}"
}
