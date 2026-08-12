# Stakeholder Matrix Artifacts

This directory stores generated governance assets derived exclusively from
`docs/responsible_ai_program.md`.

## Generation

```bash
python scripts/generate_stakeholder_assets.py
```

The script parses the source document, resolves section/line references, and
produces:

- `matrix.csv` – consolidated stakeholder matrix with power/interest mapping.
- `raci.csv` – RACI chart for ключові напрями робіт (development, testing,
  deployment, security, legal).
- `communication_plan.csv` – короткий план комунікацій, синхронізований із
  дорожньою картою запуску.
- `manifest.json` – reproducibility manifest (SHA-256 checksums, git revision,
  source hash).

## Artifact Manifest

| File | SHA-256 |
| --- | --- |
| `stakeholders/matrix.csv` | `6ac5acccf4da94bdb64d466dd4c8f703f2ab7f7575bbc608c862078a03962b98` |
| `stakeholders/raci.csv` | `0c75275bc83468755620d262f427fbfa98827bb4861cc1f41d60331c129602e1` |
| `stakeholders/communication_plan.csv` | `69b5a0d756690b6c08318b03783a3dc8e1260f56e2e1a8d936efa779da6df681` |
| `docs/responsible_ai_program.md` | `2b0e3039c1fa04699c63c6121690eba9379c331771bb504a194156c0a4c51a46` |

Git revision recorded in `manifest.json`: `c73836ebee6d5e182335d39b841c939b4a0d954e`.

Re-run the generator after any source document changes and commit the updated
artifacts plus manifest to maintain provenance.
