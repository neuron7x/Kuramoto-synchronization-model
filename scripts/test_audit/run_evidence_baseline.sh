#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="reports/test_audit/baseline_run_${TS_UTC}"
mkdir -p "$RUN_DIR"

python --version > "${RUN_DIR}/python_version.txt"
pip freeze > "${RUN_DIR}/pip_freeze.txt"
git rev-parse HEAD > "${RUN_DIR}/git_sha.txt"
git status --short > "${RUN_DIR}/git_dirty_state.txt"

python -m pip show pytest >/dev/null
python -m pip show pytest-cov >/dev/null || true

PYTEST_CMD="pytest tests/ -m \"not nightly and not flaky\" --cov=core --cov=backtest --cov=execution --cov-config=configs/quality/critical_surface.coveragerc --cov-report=xml:${RUN_DIR}/coverage.xml --cov-report=term-missing --junitxml=${RUN_DIR}/junit.xml"

set +e
bash -lc "$PYTEST_CMD" 2>&1 | tee "${RUN_DIR}/pytest.log"
PYTEST_EXIT=${PIPESTATUS[0]}
set -e

[[ -f "${RUN_DIR}/junit.xml" ]] || : > "${RUN_DIR}/junit.xml"
[[ -f "${RUN_DIR}/coverage.xml" ]] || : > "${RUN_DIR}/coverage.xml"
echo "${PYTEST_EXIT}" > "${RUN_DIR}/exit_code.txt"

python tools/coverage/write_coverage_summary.py --coverage-xml "${RUN_DIR}/coverage.xml" --output "${RUN_DIR}/coverage_summary.json" || true

python - <<PY
import datetime, json, platform, subprocess
from pathlib import Path
run_dir=Path("${RUN_DIR}")
meta={
  "schema_version":"1.0",
  "repo":"neuron7xLab/GeoSync",
  "branch": subprocess.check_output(["git","branch","--show-current"], text=True).strip(),
  "git_sha": subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip(),
  "dirty_worktree": bool((run_dir / "git_dirty_state.txt").read_text().strip()),
  "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
  "python_version": platform.python_version(),
  "platform": platform.platform(),
  "command_profile": "coverage_baseline",
  "ci": False,
  "ci_run_id": None,
  "exit_code": ${PYTEST_EXIT}
}
(run_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2)+"\n", encoding="utf-8")
PY

(
  cd "$RUN_DIR"
  sha256sum pytest.log junit.xml coverage.xml coverage_summary.json python_version.txt pip_freeze.txt git_sha.txt git_dirty_state.txt run_metadata.json exit_code.txt > artifact_manifest.sha256
)

echo "RUN_DIR=${RUN_DIR}"
exit "${PYTEST_EXIT}"
