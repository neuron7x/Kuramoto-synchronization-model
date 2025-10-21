package tradepulse.deployment

default allow = true

deny[msg] {
  input.kind == "Deployment"
  not input.spec.template.spec.securityContext.runAsNonRoot
  msg := sprintf("%s must run as non-root", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  some i
  container := input.spec.template.spec.containers[i]
  not has_resources(container)
  msg := sprintf("container %s in %s is missing resource requests/limits", [container.name, input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  not has_probe(input.spec.template.spec.containers[_].livenessProbe)
  msg := sprintf("%s is missing a liveness probe", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  not has_probe(input.spec.template.spec.containers[_].readinessProbe)
  msg := sprintf("%s is missing a readiness probe", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  not input.spec.template.spec.securityContext.seccompProfile.type
  msg := sprintf("%s must set a seccomp profile", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  not container.securityContext.readOnlyRootFilesystem
  msg := sprintf("%s container %s must use a read-only root filesystem", [input.metadata.name, container.name])
}

has_probe(probe) {
  probe != null
}

has_resources(container) {
  container.resources.requests.cpu
  container.resources.requests.memory
  container.resources.limits.cpu
  container.resources.limits.memory
}
