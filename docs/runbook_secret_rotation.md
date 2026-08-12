# Secret Rotation Runbook

## Purpose

This runbook codifies the steps required to rotate all credentials managed by
HashiCorp Vault for GeoSync services. It ensures rotations are performed
consistently, audited, and validated across dynamic and static secret
workflows.

## Scope

- **Systems** – Trading execution connectors, ingestion services, analytics
  workers, CI pipelines, and supporting databases that authenticate via Vault.
- **Secret Classes** – KV v2 static secrets, database dynamic credentials, JWT
  issuer keys, and API tokens used by GeoSync adapters.
- **Environments** – Production, staging, and disaster recovery regions.

## Pre-Rotation Checklist

1. Confirm Vault health: `vault status` must report `initialized`, `unsealed`,
   and `active`.
2. Verify the on-call SRE has `update` capabilities on the target mounts via
   `vault token capabilities secret/data/<path>`.
3. Ensure CI is green and no live deployment is running.
4. Announce the rotation window in the `#geosync-ops` channel and tag the
   security liaison.

## Static Secret Rotation (KV v2)

1. Retrieve current metadata for situational awareness:
   ```bash
   vault kv metadata get secret/data/services/<component>
   ```
2. Generate the replacement secret using the owning team's automation or
   `python -m application.secrets.vault SecretVault.generate_key` if the value
   is cryptographically random.
3. Update the secret atomically with compare-and-set to avoid stomping parallel
   edits:
   ```bash
   vault kv put -cas=<version> secret/data/services/<component> API_KEY=<value>
   ```
4. Confirm the rotation by inspecting metadata version increments and watching
   audit logs (`vault audit list` ➜ SIEM dashboard).

## Dynamic Credential Rotation

GeoSync services prefer dynamic credentials. Use the bundled automation to
issue a fresh lease and distribute it to the runtime environment.

```bash
python -m scripts.cli \
  --env-file scripts/.env \
  secrets-issue-dynamic \
  --address https://vault.geosync.internal:8200 \
  --mount database \
  --role geosync-execution \
  --token-env VAULT_TOKEN \
  --output state/vault/dynamic_execution.json \
  --refresh-margin 120
```

The command uses the `DynamicCredentialManager` from
`application.secrets.hashicorp` to automatically renew the lease before expiry.
The JSON payload contains the credentials and metadata required by the runtime
(`lease_id`, `lease_duration`, `renewable`, `issued_at`).

## Post-Rotation Validation

1. Trigger credential reloads for all affected services (Kubernetes secret
   sync, systemd reload, or connector hot swap via LiveTradingRunner).
2. Monitor the execution dashboard for authentication errors for 15 minutes.
3. Verify new leases exist by running `vault list sys/leases/lookup/database/creds`.
4. Ensure audit events were recorded by querying the SIEM for
   `event_type:vault.dynamic.issue` or `vault.kv.write`.

## Failure Handling

1. If a rotation fails, revoke the partial lease using
   `vault lease revoke <lease_id>` and reissue.
2. For KV writes blocked by CAS conflicts, fetch the latest version and merge
   changes before retrying.
3. Escalate to the security on-call if the Vault API is unavailable for more
   than five minutes or if audit logs fail to ingest.

## Records & Reporting

- Log the rotation in `reports/security/secret-rotations/<date>.md` including
  secret identifiers (never values), operator, and verification evidence.
- Capture the CLI output from `secrets-issue-dynamic` and attach it to the
  rotation ticket.
- Update service documentation with the new rotation timestamp.
