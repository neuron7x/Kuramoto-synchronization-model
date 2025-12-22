# Development TLS Certificates

This directory contains TLS certificates and keys for local development and testing.

## Security Notice

**Private keys (.key.pem files) are never committed to version control** and must be generated locally on each development machine.

## Generating Development Certificates

Development TLS certificates and keys are generated locally. Recommended path:

```bash
# From repository root
./scripts/gen_dev_tls.sh
ls configs/tls/dev/generated
```

The script writes fresh keys/certs to `configs/tls/dev/generated/` and never
touches tracked files.

## Files in This Directory

- `*.pem` - Public certificates (safe to commit)
- `*.key.pem` - **Private keys (NEVER commit, gitignored)**
- `root-ca.pem` - Root CA certificate for dev environment

## Certificate Validity

Development certificates are self-signed and valid for 365 days. Regenerate them annually or when they expire.

## Production Usage

⚠️ **WARNING**: These are development-only certificates. **NEVER use these in production.**

For production:
- Use certificates from a trusted Certificate Authority
- Store private keys in a secure secret manager (e.g., AWS Secrets Manager, HashiCorp Vault)
- Use proper certificate rotation policies
- Enable certificate transparency monitoring

## Security Best Practices

1. **Never commit private keys** - They are gitignored for a reason
2. **Regenerate after compromise** - If you accidentally commit a key, regenerate all certs
3. **Use different certs per service** - Each service should have its own certificate
4. **Rotate regularly** - Even in dev, rotate certificates periodically

## Troubleshooting

### "Certificate not found" error

Generate certificates using one of the methods above.

### "Certificate expired" error

Regenerate certificates:
```bash
rm *.key.pem *.pem
make generate-dev-certs
```

### Permission denied errors

Ensure certificate files have correct permissions:
```bash
chmod 600 *.key.pem  # Private keys: owner read/write only
chmod 644 *.pem      # Public certs: owner read/write, others read
```

## Related Documentation

- See `SECURITY.md` for overall security practices
- See `docs/deployment/tls.md` for production TLS configuration
