# ssh-linux-diagnose Skill Design

## Goal

Create a personal Codex skill named `ssh-linux-diagnose` for diagnosing Linux servers over SSH. It covers operational incidents, vulnerability verification, compromise checks, and vague business slowness reports. The skill is evidence-driven and conservative with remote execution.

## Core Principles

1. Interview before access. Ask about symptom, time window, impact, recent changes, environment constraints, and success criteria before connecting or generating commands.
2. Diagnose before changing. Produce a conclusion, evidence, confidence level, and next steps before suggesting state-changing commands.
3. Review every remote command. Every command intended for a remote server must pass an AI second review before execution or before being handed to a human for manual execution.
4. Require human confirmation for state changes and high-risk words. Commands that change state, or whose text contains high-risk words such as `halt`, `poweroff`, `reboot`, `shutdown`, `rm`, `kill`, or SQL write verbs, require explicit confirmation even if they are diagnostic commands such as `grep "poweroff"`.
5. Preserve a reproducible evidence trail. Reports must list evidence files, command output summaries, human-repeatable evidence commands, evidence gaps, and unexecuted recommendations.

## Triggering

Trigger when the user asks Codex to SSH into a Linux server, diagnose a Linux/server issue, verify a vulnerability on a server, investigate compromise or attack traces, or interpret vague reports such as business slowness on a server.

Example prompts:

- `ssh to prod-api-01 and check why nginx returns 502; do not change anything first.`
- `Check whether someone ran poweroff or halt on this Linux machine last night.`
- `The server disk is full. Diagnose the cause, but ask before deleting anything.`
- `The scanner says web-01 has an OpenSSL CVE. Verify and fix it.`
- `A sudo local privilege escalation vulnerability was announced. Check whether prod-batch-02 is affected.`
- `Check whether this server has signs of being attacked or compromised.`
- `The account manager says the business is slow. Check whether the server has clues.`

## Local Tool Preflight

Before remote access, inspect the local environment for useful tools: `ssh`, `scp`, `sftp`, `ssh-agent`, `ssh-add`, `sshpass`, `nc`, `telnet`, `ping`, `traceroute`, `dig`, `nslookup`, `curl`, `grep`, `awk`, `sed`, `less`, `jq`, and scenario tools such as `docker`, `kubectl`, `mysql`, `psql`, and `redis-cli`.

The preflight only checks availability and versions. It must not print private keys, read secrets, or require package installation by default.

## Access Mode Selection

Before diagnosis, determine whether the target host is reachable by the AI environment:

- Direct mode: AI can connect to the host over SSH.
- Jump/VPN mode: AI needs a bastion, VPN, or special route; ask for the allowed path.
- Manual execution mode: the server is pure intranet or otherwise unreachable by AI.

In manual execution mode, the skill gives the user one reviewed command at a time, waits for pasted output, then continues. It must not imply that Codex executed a command it only suggested. Manual commands still pass AI second review, and high-risk-word or state-changing commands still require explicit human confirmation.

## Pre-Diagnosis Interview

The skill asks concise questions before running commands. For routine cases, gather target host, SSH details, sudo constraints, symptom, start time, impact scope, recent changes, attempted actions, production status, prohibited actions, and success criteria.

For urgent cases, at minimum ask target host, symptom, start time, production status, and prohibited actions. For vague reports from non-technical users, translate the complaint into diagnosable questions such as what is slow, when it started, who is affected, and whether there are errors, timeouts, or recent changes.

## Remote Command Safety

Every remote command, including read-only commands, must be shown through an AI second-review block before execution or before being handed to a user for manual execution.

The review checks:

- Target host and access mode.
- Purpose and matching diagnostic hypothesis.
- Read-only versus state-changing behavior.
- Quoting, escaping, variables, globbing, pipes, and command substitutions.
- High-risk words and high-risk effects.
- Credential exposure risk.

State-changing commands always need human confirmation. Diagnostic commands also need human confirmation if the command text includes a high-risk word, even when the intent is only to search logs or history. Examples: `journalctl -u app | grep "poweroff"`, `history | grep "halt"`, and `last -x | grep reboot`.

High-risk words and effects include `halt`, `poweroff`, `reboot`, `shutdown`, `init 0`, `init 6`, `rm`, `truncate`, `mkfs`, `dd`, `kill`, `pkill`, `systemctl stop`, `systemctl restart`, `docker stop`, `docker rm`, `kubectl delete`, firewall mutation, route mutation, recursive permission changes, SQL `DROP`, `DELETE`, and `UPDATE`.

## Diagnostic Branches

The skill should include checklists for these scenarios:

- Linux baseline: OS, kernel, uptime, time, load, CPU, memory, swap, disk, inode, mounts, process list, listening ports, routes, DNS, and key service status.
- Service failure: systemd status, recent journal entries, config files, ports, dependencies, and recent restarts.
- Resource pressure: CPU, memory/OOM, disk fullness, inode exhaustion, IO wait, log growth, and runaway processes.
- Network symptoms: listening sockets, routes, DNS, connectivity, packet loss clues, proxy or firewall clues.
- Containers and orchestration: Docker, container logs, image versions, Kubernetes get/describe/logs where available.
- Vulnerability verification: collect CVE/component/source details, verify package or image versions, runtime exposure, config mitigations, and classify as confirmed affected, suspected affected, no evidence found, likely false positive, or unable to verify.
- Vulnerability remediation: package upgrades, config changes, image replacement, service restart, or firewall changes require explicit confirmation; post-fix verification compares before and after evidence.
- Compromise check: login records, auth logs, sudo traces, new users, SSH keys, cron/systemd persistence, suspicious processes, network connections, recent file changes, web access logs, and evidence gaps.
- Vague business slowness: first translate vague complaints into technical hypotheses; if details are unavailable, run a conservative server-side read-only baseline and avoid equating no host anomaly with no business problem.

## Reporting

Stage reports should use this structure:

```markdown
## Current Assessment
- Conclusion:
- Confidence: high / medium / low
- Impact:
- Needs change: no / requires confirmation

## Evidence
- Observed facts:
- Files involved:
- Key command output summary:
- Human-repeatable evidence commands:
- Timeline clues:

## Ruled Out
- Hypothesis:
- Reason:

## Next Step
- Read-only checks:
- Changes requiring confirmation:
```

Final reports should include final conclusion, most likely root cause, evidence chain, files involved, human-repeatable evidence commands, commands executed, commands intentionally not executed, evidence gaps, recommended changes, rollback notes, and follow-up monitoring.

## File Structure

```text
ssh-linux-diagnose/
├── SKILL.md
├── references/
│   ├── command-safety.md
│   ├── symptom-checklists.md
│   └── report-templates.md
└── evals/
    └── evals.json
```

## Notes

This workspace is not a git repository, so the design document could not be committed here. If this is later moved into a repo, commit the design and implementation plan together before editing the installed skill.
