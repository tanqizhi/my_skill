# Command Safety

Use this reference before any command reaches a remote Linux server or before giving a command to a user for manual execution on an unreachable intranet host.

## Command Classes

### Low-Risk Read-Only

Examples include `hostname`, `uname -a`, `cat /etc/os-release`, `date`, `uptime`, `free -m`, `df -h`, `df -i`, `ps`, `ss -lntup`, `ip addr`, `ip route`, `systemctl status`, bounded `journalctl` reads, log reads with `sed -n`, and package version queries.

These still require AI second review before execution.

### Read-Only But Human Confirmation Required

Any command whose text contains high-risk words requires human confirmation even if it is diagnostic. This covers commands such as:

```bash
journalctl -u app --since "2026-07-01 09:00" | grep "poweroff"
history | grep "halt"
grep -R "shutdown" /var/log/
last -x | grep reboot
```

The reason is that quoting, concatenation, shell parsing, or copy/paste mistakes can turn a diagnostic command into a destructive action.

### State-Changing

Always require human confirmation before state-changing commands, including service restarts, package installs or upgrades, config edits, file deletion or truncation, permission changes, firewall or route mutation, process killing, container deletion or restart, Kubernetes mutations, database writes, reboot, shutdown, or remediation actions.

## High-Risk Words And Effects

Treat these as confirmation triggers when they appear in command text or effect:

`halt`, `poweroff`, `reboot`, `shutdown`, `init 0`, `init 6`, `rm`, `truncate`, `mkfs`, `dd`, `kill`, `pkill`, `systemctl stop`, `systemctl restart`, `docker stop`, `docker rm`, `kubectl delete`, `kubectl rollout restart`, `kubectl scale`, `iptables`, `nft`, route changes, recursive `chmod`, recursive `chown`, SQL `DROP`, SQL `DELETE`, SQL `UPDATE`.

## AI Second Review Block

Use this before remote execution or manual relay:

```markdown
## Remote Command Review
- Target host:
- Access mode: direct / jump-vpn / manual
- Command:
- Purpose:
- Class: read-only / read-only with high-risk word / state-changing
- AI second review:
  - Target matches the user's intent: pass / fail
  - Purpose matches current hypothesis: pass / fail
  - Quoting and escaping checked: pass / fail
  - Pipes, variables, globs, command substitutions checked: pass / fail
  - High-risk words: none / hit <word>
  - State-change risk: none / present
  - Credential exposure risk: none / present
- Human confirmation required: yes / no
- Expected result:
```

Do not execute if any review item fails. Fix the command or ask the user.

## Human Confirmation Block

Use this exact shape when confirmation is required:

```markdown
I need your confirmation before this runs.

Target host:
Command:
Reason:
Risk point:
Why I believe it is acceptable:
Expected result:
Rollback or recovery path, if applicable:

Please reply with `confirm run` if you want me to execute it.
```

For manual execution mode, replace the last line with: `Please reply with confirm manual, then run it on the server and paste the output.`
