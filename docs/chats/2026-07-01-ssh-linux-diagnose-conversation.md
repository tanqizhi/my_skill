# ssh-linux-diagnose Conversation Migration

Source thread: `019f1dc8-8c7e-7b61-8d75-86bd4e7bb46c`

This document preserves the design decisions from the Codex conversation that produced the `ssh-linux-diagnose` skill.

## User Goal

Create a skill specialized in diagnosing other Linux systems over SSH.

The intended behavior is conservative: first produce diagnosis and evidence, then ask before any state-changing remediation.

## Key Decisions

- Interview before connecting or preparing commands, similar to the `brainstorming` workflow.
- Ask about symptom, time window, impact, recent changes, attempted actions, production status, forbidden actions, and success criteria.
- Run local tool preflight for SSH and diagnosis helpers such as `ssh`, `scp`, `ssh-agent`, `sshpass`, `nc`, `dig`, `curl`, `jq`, `docker`, `kubectl`, and database clients when relevant.
- Determine whether the target server is directly reachable, behind a jump/VPN path, or pure intranet.
- For pure intranet hosts, use manual execution mode: provide one reviewed command at a time, wait for user-pasted output, and never claim Codex executed the command.
- AI-review every remote command before execution or before handing it to the user for manual execution.
- Require human confirmation for every state-changing command.
- Require human confirmation for diagnostic commands that contain high-risk words, even when the intent is read-only, such as `grep "poweroff"` or `history | grep halt`.
- Include evidence files and human-repeatable evidence commands in reports.

## Covered Scenarios

- Linux baseline diagnosis.
- Service failure, resource pressure, disk or inode exhaustion, network/DNS/port issues.
- Docker and Kubernetes inspection.
- Vulnerability verification from scanners or new advisories, including remediation and post-fix verification.
- Compromise or attack trace checks.
- Vague business slowness reports from non-technical stakeholders.

## Repository Artifacts

- `skills/ssh-linux-diagnose/SKILL.md`
- `skills/ssh-linux-diagnose/references/command-safety.md`
- `skills/ssh-linux-diagnose/references/symptom-checklists.md`
- `skills/ssh-linux-diagnose/references/report-templates.md`
- `skills/ssh-linux-diagnose/evals/evals.json`
- `docs/plans/2026-07-01-ssh-linux-diagnose-design.md`
- `docs/plans/2026-07-01-ssh-linux-diagnose.md`
