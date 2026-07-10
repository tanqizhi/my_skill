# Report-directed validation

Use this workflow whenever the user supplies an existing vulnerability report. The report defines the maximum external scope.

## Normalize the report

1. Preserve the original report in `evidence/` after redaction.
2. For canonical JSON or CSV, use `report_input.py` directly.
3. For PDF, HTML, Markdown, screenshots, or vendor-specific formats, extract each finding into the canonical schema at `schemas/report-findings.schema.json`.
4. Record `report_id`, title, exact target, port/protocol or URL, vulnerability identifier, source page/row, and an exact verification method when known.
5. Show ambiguous host, URL, port, or finding mappings to the user. Do not guess.

Reject records without an exact asset and source page/row. Reject URLs containing credentials. Keep every accepted report row through final reporting.

## Build verification commands

Create an External, targeted, report-directed request. Generate a command only when a row declares an exact supported method:

- `nuclei:<template>`: run that template against that row's URL.
- `xray:<plugin>`: run that plugin in exact `--url` mode; never crawl.

Do not run Nmap discovery or generic Nuclei/Xray scanning. If no safe exact method exists, mark the row `not-assessable` or perform a manually reviewed protocol check without broadening scope.

## Record outcomes

Map every imported row to one of `confirmed`, `probable`, `not-reproduced`, or `not-assessable`. Preserve original provenance, new evidence, tool errors, and the reason for any unverified state. Never silently omit a report row.
