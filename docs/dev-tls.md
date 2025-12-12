## Development TLS assets

Use the provided helper to generate self-signed development certificates:

```bash
bash scripts/gen_dev_tls.sh
```

The script writes the following files to `configs/tls/dev/generated/`:

- `localhost.key.pem` (private key)
- `localhost.crt.pem` (certificate)

Update your local configuration or environment to point to the generated paths. For example, the Docker Compose stack mounts `configs/tls/dev` to `/app/tls` and expects:

```
TRADEPULSE_API_SERVER_TLS__CERT_FILE=/app/tls/generated/localhost.crt.pem
TRADEPULSE_API_SERVER_TLS__KEY_FILE=/app/tls/generated/localhost.key.pem
```

The generated folder is git-ignored and intended for local development only.
