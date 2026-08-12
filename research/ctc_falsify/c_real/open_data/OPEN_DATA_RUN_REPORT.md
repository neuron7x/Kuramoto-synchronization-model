# C-real Open-Data Acquisition Report

Tier-0 metadata-only discovery (DANDI REST API). No arrays downloaded; no CTC-theory claim; fail-closed.

- terminal_verdict: **INADMISSIBLE_TOO_LARGE_FOR_ENVIRONMENT**
- binding_tooling_present (pynwb/dandi/remfile): False
- candidates: 1

| dataset | spikes | lfp | areas≥2 | trials | indep.label | verdict |
|---|---|---|---|---|---|---|
| DANDI:MOCK0001 | True | True | None | None | None | REJECT_TOO_LARGE_FOR_ENV |

## Honest limitation

Coarse archive metadata confirms spikes/LFP/size/subjects but **cannot** confirm ≥2 areas, trial structure, or an INDEPENDENT routing label (attention/opto/microstim). The frozen C-real prereg makes the independent label mandatory; it is never metadata-inferable, so every metadata-only candidate stays `UNKNOWN_NEEDS_MANUAL_REVIEW` and the stage fails closed. This is the designed outcome, not a defect.

## Next action (only on explicit user vector)

Per-asset NWB introspection (needs pynwb/dandi/remfile + a specific dandiset whose docs declare an experimental ON/OFF manipulation), or a user-provided local paired dataset path.
