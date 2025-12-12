## Private key rotation and optional history purge

- Treat all previously committed keys as exposed; rotate any key that has ever been used outside development.
- Consider purging the repository history to remove the committed keys. Example (requires maintainer approval and coordinated force-push):

```bash
git filter-repo --path configs/tls/dev --invert-paths
# Force-push carefully after notifying all collaborators:
# git push --force-with-lease origin main
```

- After purging, invalidate and rotate any associated secrets. Enable or review GitHub secret scanning alerts to ensure leaked material is addressed.

> These steps are optional and require a maintainer decision before execution.
