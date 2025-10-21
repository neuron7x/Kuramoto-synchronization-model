#!/usr/bin/env bash
# TradePulse container build, scan, and signing helper.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

IMAGE_NAME=${IMAGE_NAME:-tradepulse}
IMAGE_TAG=${IMAGE_TAG:-$(git -C "${REPO_ROOT}" rev-parse --short HEAD)}
IMAGE_REGISTRY=${IMAGE_REGISTRY:-}
IMAGE_PLATFORM=${IMAGE_PLATFORM:-linux/amd64}
BUILD_TARGET=${BUILD_TARGET:-runtime}
DOCKERFILE=${DOCKERFILE:-Dockerfile}
CONTEXT=${CONTEXT:-${REPO_ROOT}}
TRIVY_SEVERITY=${TRIVY_SEVERITY:-CRITICAL,HIGH}
TRIVY_BIN=${TRIVY_BIN:-trivy}
COSIGN_BIN=${COSIGN_BIN:-cosign}
CONFTST_BIN=${CONFTST_BIN:-conftest}
POLICY_DIR=${POLICY_DIR:-${REPO_ROOT}/deploy/policies/opa}
HELM_CHART=${HELM_CHART:-${REPO_ROOT}/deploy/helm/tradepulse}
CHART_VALUES=${CHART_VALUES:-${HELM_CHART}/values.yaml}

usage() {
    cat <<USAGE
Usage: ${0##*/} <command>

Commands:
  build        Build the TradePulse image (default target=${BUILD_TARGET}).
  scan         Run Trivy against the image reference.
  sign         Sign the image with cosign. Requires COSIGN_KEY or keyless setup.
  policy       Evaluate policy-as-code against the rendered Helm chart.
  all          Execute build, scan, and policy in sequence.

Environment variables:
  IMAGE_NAME, IMAGE_TAG, IMAGE_REGISTRY, IMAGE_PLATFORM, BUILD_TARGET,
  TRIVY_BIN, COSIGN_BIN, CONFTST_BIN, POLICY_DIR, HELM_CHART, CHART_VALUES.
USAGE
}

log() {
    printf '[tradepulse-container] %s\n' "$*"
}

require_cmd() {
    local cmd=$1
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log "Missing dependency: $cmd"
        return 1
    fi
}

image_ref() {
    if [[ -n "${IMAGE_REGISTRY}" ]]; then
        printf '%s/%s:%s' "${IMAGE_REGISTRY}" "${IMAGE_NAME}" "${IMAGE_TAG}"
    else
        printf '%s:%s' "${IMAGE_NAME}" "${IMAGE_TAG}"
    fi
}

cmd_build() {
    require_cmd docker || return 1
    log "Building image $(image_ref)"
    DOCKER_BUILDKIT=1 docker buildx build "${CONTEXT}" \
        --platform "${IMAGE_PLATFORM}" \
        --target "${BUILD_TARGET}" \
        --file "${REPO_ROOT}/${DOCKERFILE}" \
        --tag "$(image_ref)" \
        --provenance=false \
        --sbom=false \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --build-arg PYTHON_VERSION=${PYTHON_VERSION:-3.11-slim} \
        --progress plain \
        --pull
}

cmd_scan() {
    require_cmd "${TRIVY_BIN}" || return 1
    log "Scanning image $(image_ref)"
    "${TRIVY_BIN}" image \
        --quiet \
        --severity "${TRIVY_SEVERITY}" \
        --scanners vuln,config,secret \
        --timeout 10m \
        --exit-code 1 \
        "$(image_ref)"
}

cmd_sign() {
    require_cmd "${COSIGN_BIN}" || return 1
    local image
    image=$(image_ref)
    if [[ -n "${COSIGN_KEY:-}" ]]; then
        log "Signing ${image} with key ${COSIGN_KEY}"
        "${COSIGN_BIN}" sign --key "${COSIGN_KEY}" "${image}"
    else
        log "Signing ${image} using keyless flow"
        "${COSIGN_BIN}" sign "${image}"
    fi
}

cmd_policy() {
    require_cmd helm || {
        log "Helm is not installed; skipping policy evaluation"
        return 0
    }
    require_cmd "${CONFTST_BIN}" || return 1
    log "Rendering Helm chart for policy evaluation"
    local rendered
    rendered=$(mktemp)
    helm template tradepulse "${HELM_CHART}" --values "${CHART_VALUES}" > "${rendered}"
    log "Running conftest with policies in ${POLICY_DIR}"
    "${CONFTST_BIN}" test "${rendered}" --policy "${POLICY_DIR}"
    rm -f "${rendered}"
}

cmd_all() {
    cmd_build
    cmd_scan
    cmd_policy
}

main() {
    local command=${1:-}
    if [[ -z "${command}" ]]; then
        usage
        exit 1
    fi
    case "${command}" in
        build) shift; cmd_build "$@" ;;
        scan) shift; cmd_scan "$@" ;;
        sign) shift; cmd_sign "$@" ;;
        policy) shift; cmd_policy "$@" ;;
        all) shift; cmd_all "$@" ;;
        -h|--help|help) usage ;;
        *)
            log "Unknown command: ${command}"
            usage
            exit 1
            ;;
    esac
}

main "$@"
