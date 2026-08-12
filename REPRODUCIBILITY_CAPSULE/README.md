# Reproducibility Capsule

> Closes audit task T5 of the 9.9 upgrade. Contains everything
> needed for an independent third party to clone the repo at the
> referenced SHA and reproduce the verified test counts and the
> X-9R `verdict: PASS` on synthetic data.

## What's in this capsule

| File | Purpose |
|---|---|
| `README.md` | This file. |
| `MANIFEST.json` | Frozen reference values (SHA, test counts, verdict hashes). |
| `ENVIRONMENT.lock` | Output of `pip freeze` at capsule time. |
| `COMMANDS.sh` | Executable command sequence to reproduce. |
| `EXPECTED_OUTPUTS.json` | Expected stdout / verdict / counts. |
| `SHA256SUMS.txt` | SHA-256 of every other file in the capsule. |
| `CI_RUN_LINKS.md` | Pointers to GitHub Actions runs at the referenced SHA. |
| `MYPY_REPORT.txt` | Last `mypy --strict` report at capsule time. |
| `RUFF_REPORT.txt` | Last `ruff check` report. |
| `BLACK_REPORT.txt` | Last `black --check` report. |
| `TEST_REPORT.xml` | Last pytest junit XML at capsule time. |

## Reproducibility contract

> PASS = clean clone + locked deps + exact commands + same test
> count + same verdict hashes
>
> FAIL = any manual step, hidden state, "works on my machine"

If you reproduce this capsule and any of the verdicts in
`EXPECTED_OUTPUTS.json` does **not** match, file a finding under
`EXTERNAL_REVIEW_PACKET/06_REVIEW_FORM.md` category
"irreproducible command".

## How to reproduce

```bash
git clone https://github.com/neuron7xLab/GeoSync.git
cd GeoSync
git checkout <SHA from MANIFEST.json>
python -m pip install -r requirements.txt
bash REPRODUCIBILITY_CAPSULE/COMMANDS.sh
diff <(jq -S . EXPECTED_OUTPUTS_actual.json) \
     <(jq -S . REPRODUCIBILITY_CAPSULE/EXPECTED_OUTPUTS.json)
# diff exits 0 if they match
```
