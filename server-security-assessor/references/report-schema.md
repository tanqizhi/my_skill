# Reporting contract

Assign every finding a stable ID, asset, component, source, status, severity, confidence, exposure condition, evidence references, impact, remediation guidance, retest method, and baseline mapping.

Use these statuses: `confirmed`, `probable`, `not-reproduced`, and `not-assessable`. Deduplicate only high-confidence matches and retain all source evidence. Redact secrets before writing evidence, then create a SHA-256 manifest.

Produce `report.md`, `executive-report.html`, `findings.json`, and `evidence/` even for partial runs.
