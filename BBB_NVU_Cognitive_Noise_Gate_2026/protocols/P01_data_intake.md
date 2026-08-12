# P01 — Data Intake Protocol

Purpose: accept data without losing context, units, timestamps, provenance, quality, evidence grade, or version.

Required fields: `subject_id`, `observation_id`, `timestamp`, `source_type`, `domain`, `measure_code`, `value`, `unit`, `method`, and `provenance`.

Rules:

- Data without timestamp do not enter inference.
- Data without provenance cannot increase confidence.
- Units are converted only through an allowed dictionary.
- Each source receives source reliability.
- Raw data are not overwritten.
