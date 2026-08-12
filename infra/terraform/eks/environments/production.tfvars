aws_region  = "us-east-1"
environment = "production"
cluster_name = "geosync-production"

node_groups = {
  system = {
    min_size       = 3
    max_size       = 9
    desired_size   = 3
    instance_types = ["m6i.xlarge"]
    capacity_type  = "ON_DEMAND"
    labels = {
      "workload" = "system"
    }
    taints = []
  }
  spot = {
    min_size       = 2
    max_size       = 12
    desired_size   = 4
    instance_types = ["m6i.xlarge", "m6a.xlarge"]
    capacity_type  = "SPOT"
    labels = {
      "workload" = "spot"
    }
    taints = []
  }
}

tags = {
  "CostCenter" = "geosync-production"
  "Availability" = "mission-critical"
}
