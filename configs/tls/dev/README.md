## Development TLS materials

Private keys are no longer stored in the repository. Generate fresh, local-only
certificates with:

```bash
bash scripts/gen_dev_tls.sh
```

Outputs are written to `configs/tls/dev/generated/` and are `.gitignore`d. The
docker-compose mounts already point at this directory. Never reuse these
artifacts in production.
