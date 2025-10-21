package tradepulse.service

deny[msg] {
  input.kind == "Service"
  input.spec.type == "LoadBalancer"
  not input.metadata.annotations["service.beta.kubernetes.io/aws-load-balancer-type"]
  msg := sprintf("Service %s must set the AWS load balancer type annotation", [input.metadata.name])
}

deny[msg] {
  input.kind == "Service"
  input.spec.type == "ClusterIP"
  not input.spec.ports[_].targetPort
  msg := sprintf("Service %s must define targetPort for all ports", [input.metadata.name])
}
