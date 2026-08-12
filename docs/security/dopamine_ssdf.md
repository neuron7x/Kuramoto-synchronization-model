# Dopamine SSDF Mapping

This component maps the dopamine hardening gate to secure-development controls.

| SSDF function | Dopamine control |
|---|---|
| Prepare the Organization | Semantic contract, claim boundary, release verdict. |
| Protect the Software | Artifact SHA-256 manifests and provenance outputs. |
| Produce Well-Secured Software | Config validation, schema/runtime parity, offline evaluation harness, local metrics. |
| Respond to Vulnerabilities | Blocking release verdict, dependency-audit placeholder, scanner availability status. |

Tool availability must be recorded as `TOOL_UNAVAILABLE` when local tools are absent. The gate must not fake a pass for tools that did not run.
