#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/configs/tls/dev/generated"
DAYS="${DAYS:-365}"

mkdir -p "${OUT_DIR}"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "${OUT_DIR}/root-ca.key.pem" \
  -out "${OUT_DIR}/root-ca.pem" \
  -days "${DAYS}" \
  -subj "/CN=tradepulse-dev-root" >/dev/null

issue_cert() {
  local name="$1"
  local cn="$2"
  local san="${3:-DNS:localhost,IP:127.0.0.1}"
  openssl req -new -nodes \
    -keyout "${OUT_DIR}/${name}.key.pem" \
    -out "${OUT_DIR}/${name}.csr.pem" \
    -subj "/CN=${cn}" >/dev/null

  openssl x509 -req \
    -in "${OUT_DIR}/${name}.csr.pem" \
    -CA "${OUT_DIR}/root-ca.pem" \
    -CAkey "${OUT_DIR}/root-ca.key.pem" \
    -CAcreateserial \
    -out "${OUT_DIR}/${name}.pem" \
    -days "${DAYS}" \
    -sha256 \
    -extfile <(printf "subjectAltName=%s\nextendedKeyUsage=serverAuth,clientAuth\n" "${san}") >/dev/null

  rm -f "${OUT_DIR}/${name}.csr.pem"
}

issue_cert "tradepulse-server" "tradepulse.local"
issue_cert "cortex-server" "cortex.local"
issue_cert "cortex-db-server" "cortex-db.local"
issue_cert "cortex-db-client" "cortex-db.client.local"

cat <<'EOF'
Generated development TLS materials under configs/tls/dev/generated:
  - root-ca.pem / root-ca.key.pem
  - tradepulse-server.pem / tradepulse-server.key.pem
  - cortex-server.pem / cortex-server.key.pem
  - cortex-db-server.pem / cortex-db-server.key.pem
  - cortex-db-client.pem / cortex-db-client.key.pem

Use these only for local development. The directory is .gitignored to prevent
committing key material.
EOF
