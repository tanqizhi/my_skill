---
name: network-security-integrated-scanner
description: Assess authorized Linux servers, Windows server exposure, and Web services using External, Internal SSH, or Both modes. Use when Codex needs to scan a server, validate an existing vulnerability report, check Linux security through SSH, investigate compromise indicators, run bounded safe PoCs, or produce evidence-backed security reports. Supports Nmap, Nuclei, optional Chaitin Xray for Web targets, custom baselines, and Markdown, HTML, JSON, and evidence outputs.
---

# Network Security Integrated Scanner

Assess only targets supplied by the user. Treat supplied targets as authorized, but never infer or expand to sibling domains, resolved addresses, redirects, CIDRs, or related assets.

## Workflow

1. Ask for the assessment mode:
   - `External`: external scan or report-directed verification only.
   - `Internal`: Linux SSH inspection only.
   - `Both`: run both paths and correlate their evidence.
2. Ask for coverage:
   - `全面检查`: use the complete checklist within the supplied target boundary.
   - `定向检查`: collect exact IPs, domains, ports, URLs, services, directories, logs, and time ranges.
3. Read [scope-policy.md](references/scope-policy.md) and freeze the scope before producing commands.
4. If a vulnerability report is supplied, read [report-validation.md](references/report-validation.md). Verify only report findings; do not start broad discovery or crawling.
5. For modes containing External, read [external-assessment.md](references/external-assessment.md). If a required local tool is missing, read [tool-installation.md](references/tool-installation.md). Ask whether safe PoC verification is allowed. Enable Chaitin Xray only for an identified Web business and within its URL scope.
6. For modes containing Internal, require Linux and read [linux-internal-assessment.md](references/linux-internal-assessment.md) plus the [Linux check catalog](references/checks/linux-checks.json). Use the supplied account; use confirmed `sudo` only when a normal account cannot perform a required read-only check.
7. Run forensics only when explicitly selected or after showing suspicious evidence and receiving upgrade confirmation. Read [forensics.md](references/forensics.md) and the [forensic check catalog](references/checks/forensic-checks.json).
8. Correlate and report results using [report-schema.md](references/report-schema.md).

## Non-negotiable gates

- Review every external or SSH command before execution.
- Keep version 1 assessment-only. Do not remediate, restart services, alter files, install software on the target, create persistence, dump credentials, or run denial-of-service checks.
- Allow only non-destructive, non-persistent PoCs that avoid material business-state changes and sensitive-data extraction.
- Stop on health degradation, unexpected scope, host-key changes, or user cancellation.
- Record permission, timeout, parse, and tool failures as `not-assessable`; never describe an unchecked area as safe.
- Install missing Nmap, Nuclei, or Chaitin Xray only on the assessment machine through normal Codex approval. Distinguish Chaitin Xray from XTLS/Xray-core and verify official checksums.
- Never store passwords, private keys, sudo secrets, bearer tokens, or cookies in commands, logs, `findings.json`, or evidence.

## Required outputs

Always create a run directory containing:

- `report.md`: detailed technical report.
- `executive-report.html`: self-contained, responsive, printable leadership report with no external CDN.
- `findings.json`: canonical machine-readable findings.
- `evidence/`: redacted source artifacts and a SHA-256 manifest.

If execution is partial, still create all four outputs and state coverage gaps prominently.
