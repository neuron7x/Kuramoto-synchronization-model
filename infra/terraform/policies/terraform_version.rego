package main

required_version := "= 1.6.6"

deny[msg] {
  not input.terraform.required_version
  msg := sprintf("%s: terraform required_version must be %s", [input.__path__, required_version])
}

deny[msg] {
  version := input.terraform.required_version
  version != required_version
  msg := sprintf("%s: terraform required_version must be %s but found %s", [input.__path__, required_version, version])
}
