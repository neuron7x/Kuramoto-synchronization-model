#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

if [ "$#" -eq 0 ]; then
  npm exec --prefix ui/dashboard prettier -- --write ui/dashboard
else
  npm exec --prefix ui/dashboard prettier -- --write "$@"
fi
