locals {
  name_prefix = "geosync-${var.environment}"
  base_tags = {
    "Environment" = var.environment
    "Project"     = "GeoSync"
    "ManagedBy"   = "Terraform"
  }
  tags = merge(local.base_tags, var.tags)

  resolved_azs    = length(var.availability_zones) > 0 ? var.availability_zones : slice(data.aws_availability_zones.available.names, 0, 3)
  subnet_count    = min(length(local.resolved_azs), length(var.private_subnet_cidrs), length(var.public_subnet_cidrs))
  azs             = slice(local.resolved_azs, 0, local.subnet_count)
  private_subnets = slice(var.private_subnet_cidrs, 0, local.subnet_count)
  public_subnets  = slice(var.public_subnet_cidrs, 0, local.subnet_count)

  managed_node_groups = length(var.node_groups) > 0 ? var.node_groups : {
    general = {
      min_size       = 3
      max_size       = 9
      desired_size   = 3
      instance_types = ["m6i.xlarge"]
      capacity_type  = "ON_DEMAND"
      labels = {
        "workload" = "general"
      }
      taints = []
    }
  }
}

check "subnet_cidr_alignment" {
  assert {
    condition     = length(var.private_subnet_cidrs) == length(var.public_subnet_cidrs)
    error_message = "private_subnet_cidrs must align with the number of public_subnet_cidrs."
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source = "../modules/terraform-aws-vpc"

  name = "${local.name_prefix}-vpc"
  cidr = var.vpc_cidr
  azs  = local.azs

  private_subnets = local.private_subnets
  public_subnets  = local.public_subnets

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_support   = true
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }

  tags = local.tags
}

module "eks" {
  source = "../modules/terraform-aws-eks"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  enable_irsa = true

  vpc_id                                = module.vpc.vpc_id
  subnet_ids                            = module.vpc.private_subnets
  cluster_additional_security_group_ids = []

  tags = local.tags

  eks_managed_node_groups = {
    for name, group in local.managed_node_groups : name => {
      min_size       = group.min_size
      max_size       = group.max_size
      desired_size   = group.desired_size
      instance_types = group.instance_types
      capacity_type  = group.capacity_type
      labels = merge({
        "app.kubernetes.io/part-of"    = "geosync"
        "app.kubernetes.io/managed-by" = "terraform"
        "environment"                  = var.environment
      }, group.labels)
      taints = [for taint in group.taints : {
        key    = taint.key
        value  = taint.value
        effect = taint.effect
      }]
    }
  }

  node_security_group_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "owned"
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

locals {
  autoscaler_namespace       = "kube-system"
  autoscaler_service_account = "cluster-autoscaler"
}

resource "aws_iam_policy" "cluster_autoscaler" {
  count = var.enable_cluster_autoscaler ? 1 : 0

  name        = "${var.cluster_name}-cluster-autoscaler"
  description = "Grants the Kubernetes cluster-autoscaler access to manage node groups"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeTags",
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup",
          "ec2:DescribeLaunchTemplateVersions"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "cluster_autoscaler" {
  count = var.enable_cluster_autoscaler ? 1 : 0

  name = "${var.cluster_name}-cluster-autoscaler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:sub" = "system:serviceaccount/${local.autoscaler_namespace}/${local.autoscaler_service_account}"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  count      = var.enable_cluster_autoscaler ? 1 : 0
  role       = aws_iam_role.cluster_autoscaler[0].name
  policy_arn = aws_iam_policy.cluster_autoscaler[0].arn
}

resource "helm_release" "cluster_autoscaler" {
  count = var.enable_cluster_autoscaler ? 1 : 0

  name       = "cluster-autoscaler"
  repository = "https://kubernetes.github.io/autoscaler"
  chart      = "cluster-autoscaler"
  version    = "9.37.0"
  namespace  = local.autoscaler_namespace

  create_namespace = false

  values = [yamlencode({
    autoDiscovery = {
      clusterName = module.eks.cluster_name
    }
    awsRegion     = var.aws_region
    cloudProvider = "aws"
    rbac = {
      serviceAccount = {
        create = true
        name   = local.autoscaler_service_account
        annotations = {
          "eks.amazonaws.com/role-arn" = aws_iam_role.cluster_autoscaler[0].arn
        }
      }
    }
    extraArgs = {
      "balance-similar-node-groups"   = "true"
      expander                        = "least-waste"
      "skip-nodes-with-local-storage" = "false"
      "skip-nodes-with-system-pods"   = "false"
    }
  })]

  depends_on = [aws_iam_role_policy_attachment.cluster_autoscaler]
}
