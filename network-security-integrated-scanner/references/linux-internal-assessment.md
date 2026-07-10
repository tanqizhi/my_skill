# Linux internal assessment

Use this workflow only for Internal or Both modes. Support Ubuntu/Debian and RHEL/CentOS/Rocky/Alma families.

## Connect and freeze scope

1. Record the SSH host, port, account type, host-key fingerprint, requested categories, paths, logs, and time range.
2. Stop on a host-key change. Never pass passwords, private-key contents, or sudo secrets in command arguments.
3. Identify the distro family with the minimal OS-release check.
4. Load `checks/linux-checks.json` and build a plan filtered by distro and the frozen full/targeted scope.

The planner returns argv records; it does not open SSH. Review each record before execution.

## Apply privilege rules

- Run unprivileged checks first for a normal account.
- Mark root-only checks as pending. Ask before prefixing an individual check with `sudo --`.
- When the supplied account is root, run the same read-only argv directly without `sudo`.
- Never request a sudo password in a command or persist it in logs.

## Execute safely

Capture stdout/stderr locally with the check ID, timestamp, exit status, timeout, and account privilege. Avoid remote temporary files. Apply conservative timeouts to package, log, and process inventories. Stop on target load or health degradation.

Redact the shadow hash field, credentials, tokens, cookies, environment secrets, and sensitive process arguments before evidence is saved. If a command is absent, denied, or timed out, mark the check `not-assessable` and continue with independent checks.

Cover system/patches, accounts, SSH, firewall, services, packages, permissions, kernel controls, containers, logs, scheduled jobs, startup entries, processes, and network connections. Do not install packages, change configuration, restart services, or remediate.

