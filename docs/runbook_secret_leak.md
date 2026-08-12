# Secret Leak Response Runbook

## Purpose

Provide a deterministic response plan for suspected or confirmed secret leaks
impacting GeoSync. The goal is to contain exposure, rotate credentials,
restore trust in the environment, and capture forensic evidence.

## Scope

- **Triggers** – Secret detection alerts in CI, SIEM notifications of Vault audit
  anomalies, leaked credential reports from partners, or manual discoveries.
- **Actors** – Security incident commander (SIC), on-call SRE, affected service
  owners, and compliance liaison.
- **Systems** – Vault (all mounts), Git repositories, CI/CD, execution runtime,
  partner integrations, and analytics infrastructure.

## Detection & Triage

1. Validate the alert source. For CI findings, inspect the
   `secret-scan` job artifacts; for Vault anomalies, review
   `event_type:vault.secret_read` from the SIEM.
2. Scope the exposure window using Vault audit records filtered by
   `details.secret.name`.
3. Create a SEV-1 incident in PagerDuty with the tag `secret-leak`.

## Containment Steps

1. Disable affected API keys at the upstream provider (exchange, database).
2. Revoke Vault leases immediately:
   ```bash
   vault lease revoke -prefix secret/data/<path>
   ```
3. Pause automated deployments and revoke CI tokens using
   `python -m scripts.cli secrets-issue-dynamic --role cicd --token-env VAULT_TOKEN`.
4. Lock Git repositories by enabling branch protection to block merges until
   rotated.

## Eradication & Rotation

1. Execute the [Secret Rotation Runbook](runbook_secret_rotation.md) for every
   affected credential, prioritising production systems.
2. Use the `secrets-issue-dynamic` command to issue fresh dynamic credentials
   with a reduced TTL (≤30 minutes) until the environment stabilises.
3. Update `SecretAccessPolicy` definitions in infrastructure-as-code to ensure
   least privilege after the incident.

## Recovery Verification

1. Confirm all services authenticate successfully using the new credentials.
2. Run smoke tests for trading execution and ingestion connectors.
3. Monitor Vault audit logs for attempted access to retired leases; no hits
   should appear after revocation.
4. Re-enable CI/CD once validation passes and confirm the secret scanning job
   returns clean results.

## Evidence Collection

- Export relevant Vault audit records and store under
  `reports/security/incidents/<incident-id>/audit.json`.
- Capture CLI outputs from revocation and rotation commands.
- Preserve SIEM alert screenshots and any vendor communications.

## Post-Incident Actions

1. File tickets for long-term fixes (e.g., missing deny-by-default policies).
2. Run the security postmortem template within 48 hours and link the final
   report to `docs/incident_playbooks.md`.
3. Update this runbook with any new detection sources or containment tooling.
