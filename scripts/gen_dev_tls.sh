#!/usr/bin/env bash
set -euo pipefail

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate dev TLS certificates" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/configs/tls/dev/generated"
mkdir -p "${OUT_DIR}"

KEY_PATH="${OUT_DIR}/localhost.key.pem"
CERT_PATH="${OUT_DIR}/localhost.crt.pem"

openssl req \
  -x509 \
  -nodes \
  -newkey rsa:2048 \
  -keyout "${KEY_PATH}" \
  -out "${CERT_PATH}" \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "Generated development TLS assets:"
echo "  Key : ${KEY_PATH}"
echo "  Cert: ${CERT_PATH}"
