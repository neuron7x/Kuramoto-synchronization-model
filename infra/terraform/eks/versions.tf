terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 5.49.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.26.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "= 2.11.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "= 4.0.5"
    }
    time = {
      source  = "hashicorp/time"
      version = "= 0.12.1"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "= 2.3.4"
    }
    null = {
      source  = "hashicorp/null"
      version = "3.2.4"
    }
  }
}
