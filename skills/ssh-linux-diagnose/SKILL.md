---
name: ssh-linux-diagnose
description: Diagnose Linux servers over SSH or manual command relay. Use when the user asks to SSH into a Linux host, troubleshoot server slowness/outage/resource/service/network issues, verify or remediate vulnerabilities, investigate compromise/attack traces, or guide diagnosis for a pure-intranet host. Always interview first, run local tool preflight, AI-review every remote command, and require human confirmation for state changes or high-risk command words.
license: MIT
---

# ssh-linux-diagnose

## Purpose

Diagnose Linux servers through SSH, bastions, VPN paths, or manual command relay. Work like a careful SRE: clarify the incident, collect evidence, explain the conclusion, and ask before any risky action.

## Non-Negotiable Safety Rules

1. Interview before access. Ask what is wrong, when it started, who or what is affected, what changed recently, what was already tried, whether this is production, what actions are forbidden, and what result the user wants.
2. Run a local tool preflight before remote work. Check available local tools without reading secrets or printing private material.
3. AI-review every command intended for a remote server before execution or before giving it to the user for manual execution.
4. Require explicit human confirmation before any state-changing command.
5. Require explicit human confirmation for any command text containing high-risk words, even when the command is intended to be read-only, such as `grep "poweroff"` or `history | grep halt`.
6. Never imply that Codex executed a command when the user executed it manually on an intranet host.
7. Preserve evidence. Reports must include files involved, command output summaries, human-repeatable evidence commands, and evidence gaps.

## Workflow

1. Clarify the situation with a short interview. In urgent cases, at minimum ask for target host, symptom, start time, production status, and forbidden actions.
2. Run local tool preflight for `ssh`, `scp`, `sftp`, `ssh-agent`, `ssh-add`, `sshpass`, `nc`, `telnet`, `ping`, `traceroute`, `dig`, `nslookup`, `curl`, `grep`, `awk`, `sed`, `less`, `jq`, and scenario tools such as `docker`, `kubectl`, `mysql`, `psql`, or `redis-cli` when relevant.
3. Choose access mode: direct SSH, bastion/VPN, or manual execution for pure-intranet machines.
4. Build 2-4 ranked hypotheses before broad probing when the situation is unclear.
5. Review each remote command with the command review protocol in `references/command-safety.md`.
6. Execute only reviewed commands. If the command changes state or contains high-risk words, wait for explicit confirmation first.
7. Summarize evidence after each phase. State conclusion, confidence, impact, files involved, repeatable evidence commands, and next step.
8. For remediation, show command, purpose, risk, expected result, and rollback or recovery path before asking for confirmation.

## Access Modes

- Direct mode: Codex can SSH to the host.
- Jump/VPN mode: ask for the allowed route and do not invent access paths.
- Manual execution mode: provide one reviewed command at a time, wait for the user to paste output, then continue. Treat pasted output as evidence from the user, not as a command Codex executed.

## Scenario Routing

- For command review, high-risk words, and confirmation blocks, read `references/command-safety.md`.
- For Linux health, service failures, resources, network, containers, vulnerability verification, compromise checks, or vague business slowness, read `references/symptom-checklists.md`.
- For stage reports, final reports, vulnerability reports, and manual execution prompts, read `references/report-templates.md`.

## Output Expectations

Prefer concise incident-style reports. Include the conclusion first once evidence supports it, then the evidence chain. Do not bury uncertainty: label confidence as high, medium, or low and name evidence gaps.
