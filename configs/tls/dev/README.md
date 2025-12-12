Development TLS assets are generated locally.

- Run `bash scripts/gen_dev_tls.sh` to create `localhost.crt.pem` and `localhost.key.pem`.
- Generated files are placed in `configs/tls/dev/generated/` and are git-ignored.
- Do not commit private keys or certificates to the repository.
