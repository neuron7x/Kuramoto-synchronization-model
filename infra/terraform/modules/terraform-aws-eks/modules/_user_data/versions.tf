terraform {
  required_version = "= 1.6.6"

  required_providers {
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = ">= 2.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }
}
