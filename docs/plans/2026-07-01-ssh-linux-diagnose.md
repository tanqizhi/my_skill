# ssh-linux-diagnose Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and install a personal Codex skill for safe, evidence-driven SSH/Linux server diagnosis.

**Architecture:** Create a lightweight skill directory with one primary `SKILL.md` and three progressively loaded references: command safety, symptom checklists, and report templates. Keep mandatory safety rules in `SKILL.md`; move long checklists and templates into references.

**Tech Stack:** Markdown skill files, JSON eval prompts, shell validation with `find`, `sed`, and `rg`.

---

### Task 1: Create Skill Directory Skeleton

**Files:**
- Create: `work/ssh-linux-diagnose/SKILL.md`
- Create: `work/ssh-linux-diagnose/references/command-safety.md`
- Create: `work/ssh-linux-diagnose/references/symptom-checklists.md`
- Create: `work/ssh-linux-diagnose/references/report-templates.md`
- Create: `work/ssh-linux-diagnose/evals/evals.json`

**Step 1: Create directories**

Run: `mkdir -p work/ssh-linux-diagnose/references work/ssh-linux-diagnose/evals`

Expected: directories exist.

**Step 2: Add placeholder files with apply_patch**

Expected: `find work/ssh-linux-diagnose -type f | sort` lists the five files.

### Task 2: Write SKILL.md

**Files:**
- Modify: `work/ssh-linux-diagnose/SKILL.md`

**Step 1: Add frontmatter**

Use this metadata:

```yaml
---
name: ssh-linux-diagnose
description: Diagnose Linux servers over SSH or manual command relay. Use when the user asks to SSH into a Linux host, troubleshoot server slowness/outage/resource/service/network issues, verify or remediate vulnerabilities, investigate compromise/attack traces, or guide diagnosis for a pure-intranet host. Always interview first, run local tool preflight, AI-review every remote command, and require human confirmation for state changes or high-risk command words.
license: MIT
---
```

**Step 2: Add required workflow**

Include purpose, non-negotiable safety rules, workflow, local tool preflight, access mode selection, pre-diagnosis interview, command review protocol, reporting requirements, and reference routing.

Expected: `SKILL.md` contains all safety gates and points to the three reference files.

### Task 3: Write Command Safety Reference

**Files:**
- Modify: `work/ssh-linux-diagnose/references/command-safety.md`

Document low-risk read-only commands, read-only commands needing confirmation due to high-risk words, state-changing commands, high-risk words, AI review checklist, and human confirmation block.

Expected: reference explicitly covers diagnostic commands such as `grep "poweroff"` requiring confirmation.

### Task 4: Write Symptom Checklists

**Files:**
- Modify: `work/ssh-linux-diagnose/references/symptom-checklists.md`

Add checklists for baseline Linux health, service failure, resource pressure, network/DNS/port issues, containers/Kubernetes, vulnerability verification/remediation, compromise checks, and vague business slowness.

Expected: checklists include evidence files and human-repeatable evidence commands.

### Task 5: Write Report Templates

**Files:**
- Modify: `work/ssh-linux-diagnose/references/report-templates.md`

Add templates for pre-diagnosis interview, remote command review, human confirmation, stage assessment, final report, vulnerability verification report, and manual execution mode.

Expected: templates include files involved and human-repeatable evidence commands.

### Task 6: Write Eval Prompts

**Files:**
- Modify: `work/ssh-linux-diagnose/evals/evals.json`

Add realistic prompts covering:

- Nginx 502 with no changes allowed.
- Searching for `poweroff` or `halt` history.
- Disk full with cleanup requiring confirmation.
- Scanner-reported CVE verification and fix.
- Announced vulnerability verification.
- Compromise trace investigation.
- Vague business slowness from a non-technical user.
- Pure intranet server requiring manual command relay.

Expected: JSON parses with `python3 -m json.tool work/ssh-linux-diagnose/evals/evals.json`.

### Task 7: Validate Skill Structure

**Files:**
- Read: `work/ssh-linux-diagnose/**`

Run:

```bash
find work/ssh-linux-diagnose -type f | sort
python3 -m json.tool work/ssh-linux-diagnose/evals/evals.json
rg -n "AI second review|human confirmation|high-risk|manual execution|evidence commands" work/ssh-linux-diagnose
```

Expected: all files exist, JSON parses, and core safety phrases are present.

### Task 8: Install Skill

**Files:**
- Copy from: `work/ssh-linux-diagnose/`
- Copy to: `/Users/tanqizhi/.agents/skills/ssh-linux-diagnose/`

Run after user approval if sandbox escalation is required:

```bash
mkdir -p /Users/tanqizhi/.agents/skills/ssh-linux-diagnose
cp -R work/ssh-linux-diagnose/. /Users/tanqizhi/.agents/skills/ssh-linux-diagnose/
```

Expected: installed `SKILL.md` exists in the personal skill directory.

### Task 9: Final Verification

Run:

```bash
sed -n '1,80p' /Users/tanqizhi/.agents/skills/ssh-linux-diagnose/SKILL.md
find /Users/tanqizhi/.agents/skills/ssh-linux-diagnose -type f | sort
```

Expected: frontmatter is valid, references are present, and eval file exists.

## Execution Note

This projectless workspace is not a git repository, so commits are not available here. Preserve the plan and design documents under `docs/plans/` and install the skill into the personal skills directory after verification.
