package tradepulse.rollout

deny[msg] {
  input.kind == "Rollout"
  not input.spec.strategy
  msg := sprintf("Rollout %s must define a strategy", [input.metadata.name])
}

deny[msg] {
  input.kind == "Rollout"
  input.spec.strategy.canary
  not input.spec.strategy.canary.steps
  msg := sprintf("Rollout %s must define canary steps", [input.metadata.name])
}

deny[msg] {
  input.kind == "Rollout"
  container := input.spec.template.spec.containers[_]
  not container.resources.requests
  msg := sprintf("Rollout %s container %s is missing resource requests", [input.metadata.name, container.name])
}

deny[msg] {
  input.kind == "Rollout"
  container := input.spec.template.spec.containers[_]
  not container.livenessProbe
  msg := sprintf("Rollout %s container %s is missing a liveness probe", [input.metadata.name, container.name])
}

deny[msg] {
  input.kind == "Rollout"
  container := input.spec.template.spec.containers[_]
  not container.securityContext.runAsNonRoot
  msg := sprintf("Rollout %s container %s must run as non-root", [input.metadata.name, container.name])
}
