# Reporting contract

Use `schemas/findings.schema.json` as the machine-readable contract. Assign a deterministic `NSIS-<12 hex>` ID before rendering.

## Finding fields

Record asset, component, title, source tools, identifiers, status, severity, confidence, exposure conditions, evidence references, impact, remediation guidance, retest method, baseline mappings, and related finding IDs.

Use only these statuses:

- `confirmed`: sufficient direct evidence.
- `probable`: credible evidence that is not safe or sufficient to confirm.
- `not-reproduced`: a reported issue was tested but not reproduced; retain its provenance.
- `not-assessable`: a permission, safety, scope, tool, timeout, or parse limitation prevented assessment.

`not-assessable` reduces coverage. It never counts as safe.

## Integrity and correlation

Redact secrets before writing evidence. Write artifacts atomically with restrictive permissions and build a relative-path SHA-256 manifest.

Deduplicate findings only when the normalized asset shares a strong identifier such as CVE/GHSA, or when high-confidence asset/component/title keys are exact. Merge all source and evidence references. Link matching external ports to internal listeners by related finding ID; do not merge them and do not link different virtual hosts.

## Outputs

Produce `report.md`, `executive-report.html`, `findings.json`, and `evidence/manifest.json` for complete and partial runs. Put coverage gaps and stopped checks in every human-readable output.
