# Provenance

`geosync-provenance.txt` records the HEAD commit SHA of this repository's
`main` branch at a specific point in time. `geosync-provenance.txt.ots` is an
[OpenTimestamps](https://opentimestamps.org/) proof for that file, anchored
independently to the Bitcoin blockchain via multiple calendar servers
(`opentimestamps.org`, `eternitywall.com`, `catallaxy.com`).

This exists so that authorship/existence of this project at this commit does
not depend on any single hosting platform (GitLab, GitHub, or otherwise)
remaining available or trustworthy. The proof is verifiable by anyone,
independently of this repository's host, using the `ots` CLI:

```
pip install opentimestamps-client
ots verify provenance/geosync-provenance.txt.ots
```

Once the underlying Bitcoin transaction confirms (usually within a few
hours of stamping), `ots upgrade provenance/geosync-provenance.txt.ots`
attaches the final block-height attestation.
