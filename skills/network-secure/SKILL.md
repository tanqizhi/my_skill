---
name: network-secure
description: Assess authorized servers and Web services through external scanning, Linux SSH inspection, or both. Use when Codex needs to run Nmap or Nuclei, optionally use Chaitin Xray for Web checks, validate an existing vulnerability report, inspect a mainstream Linux server over SSH, investigate suspicious indicators, or produce technical and executive security assessment reports. Windows targets support external assessment only.
---

# Network Secure

Assess only assets the user owns or is authorized to test. Do not infer permission for related domains, adjacent IPs, redirected hosts, cloud resources, or third-party services.

## Establish the assessment

Before running commands, ask for and confirm:

1. **Mode**
   - `External`: external scan with optional safe PoC validation.
   - `Internal`: Linux SSH inspection only.
   - `Both`: run External and Internal, then correlate the evidence.
2. **Coverage**
   - `Full`: apply the full relevant checklist, but only inside explicitly supplied assets.
   - `Targeted`: restrict checks to the supplied hosts, ports, URLs, services, directories, logs, and time range.
3. **Targets and authorization**: record exact IPs, hostnames, URL prefixes, SSH endpoints, and exclusions.
4. **PoC permission**: ask whether bounded, non-destructive validation is allowed.
5. **Outputs**: default to a technical Markdown report and a self-contained leadership HTML report based on [executive-report-template.html](assets/executive-report-template.html).

Freeze this scope before creating commands. Do not follow redirects, DNS results, symlinks, mounted paths, or discovered assets outside it.

## Choose the workflow

### Existing vulnerability report

If the user supplies a report, verify only its listed findings and exact assets. Do not start broad discovery, crawling, generic Nuclei scans, or unrelated internal checks.

- Preserve each report item and its source page or row.
- Clarify ambiguous targets instead of guessing.
- Use an exact Nuclei template, Xray plugin, protocol request, or read-only SSH check that corresponds to the reported issue.
- Mark every item `confirmed`, `probable`, `not-reproduced`, or `not-assessable`.
- Explain tool, permission, timeout, and evidence limitations.

### External

1. Check whether `nmap` and `nuclei` are available and record their versions.
2. If missing, propose installation on the assessment machine and request normal host approval. Never install scanning tools on the assessed server.
3. Run Nmap only against confirmed assets. Use explicit ports for targeted coverage; use all TCP ports only when full coverage was authorized.
4. Run Nuclei conservatively against in-scope services or URLs. Disable cloud upload and keep concurrency and rate limits appropriate for production.
5. If the target is a Web business, offer Chaitin Xray as an optional additional scanner. Confirm it is Chaitin Xray with the `webscan` command, not XTLS/Xray-core. Use exact URLs for targeted or report-directed checks.
6. Review each proposed PoC. Permit only non-destructive, non-persistent validation that avoids sensitive-data extraction and material business-state changes.

Never perform denial of service, brute force, credential attacks, destructive fuzzing, persistence, file writes, unsafe command execution, or unapproved out-of-band callbacks.

### Internal

Internal mode supports mainstream Linux distributions, including Debian/Ubuntu and RHEL/CentOS/Rocky/Alma. Windows remains external-only.

1. Confirm SSH host, port, account, host-key fingerprint, coverage, paths, logs, and time range.
2. Review every command before executing it remotely. Run read-only commands only.
3. Identify the OS and collect evidence relevant to:
   - OS version, patch state, repositories, and kernel.
   - Accounts, groups, sudo policy, password policy, and recent logins.
   - SSH configuration and authorized keys.
   - Listening ports, processes, services, firewall, and routing.
   - Packages, startup items, scheduled jobs, containers, and mounts.
   - Sensitive file permissions and security controls such as SELinux or AppArmor.
   - Authentication, system, service, and security logs within the confirmed time range.
4. With a normal account, run accessible checks first. Ask before applying `sudo` to an individual read-only check. With a supplied root account, run the same read-only check directly.
5. Record denied, unavailable, timed-out, or incomplete checks as `not-assessable`; never describe them as safe.

Do not change configuration, install packages, restart services, delete files, kill processes, create users, or otherwise remediate during the assessment.

### Forensics upgrade

Run deeper forensics only when the user selected it initially or after presenting suspicious evidence and receiving explicit confirmation to upgrade.

Prioritize bounded collection of volatile context, connections, logins, persistence metadata, recent file metadata, and relevant log timelines. Do not deploy agents, dump credentials, acquire full memory or disk images, quarantine files, or alter the suspected system without a separate plan and authorization.

## Command and evidence rules

- Show the purpose, target, expected impact, and exact command before any consequential or privileged action.
- Stop on scope drift, host-key changes, health degradation, abnormal error rates, corrupted output, or user cancellation.
- Keep credentials, private keys, sudo secrets, cookies, bearer tokens, hashes, and sensitive process arguments out of commands and reports.
- Store only necessary, redacted evidence. Record source, collection time, command or method, exit status, and limitations.
- Separate observations from conclusions. A scanner match alone is not proof, and no findings does not prove safety.

## Report the result

Produce:

- A technical Markdown report containing scope, methods, tool versions, coverage, findings, evidence references, limitations, and prioritized recommendations.
- A self-contained HTML report for leadership using the bundled template. Keep it offline, printable, concise, and free of external CDNs.

For each finding include asset, severity, confidence, evidence, impact, verification status, and recommended remediation. Clearly separate:

- Confirmed risks.
- Probable or unverified risks.
- Not reproduced findings.
- Coverage gaps and not-assessable areas.

Do not automatically remediate. If the user later requests remediation, create a separate change plan with impact, rollback, and explicit confirmation.
