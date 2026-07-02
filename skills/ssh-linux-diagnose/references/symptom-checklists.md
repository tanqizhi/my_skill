# Symptom Checklists

Use these as diagnosis menus, not scripts to run blindly. Every remote command still needs AI second review from `command-safety.md`.

## Baseline Linux Health

Clarify the role of the host, then collect a read-only baseline: OS and kernel, time, uptime, load, CPU saturation, memory and swap, disk and inode usage, mounts, top processes, listening ports, routes, DNS, recent reboot clues, and key service status.

Common evidence files: `/etc/os-release`, `/proc/meminfo`, `/proc/cpuinfo`, `/etc/fstab`, `/var/log/messages`, `/var/log/syslog`, `/var/log/kern.log`, service logs, and application logs.

Human-repeatable evidence commands: `date`, `uptime`, `free -m`, `df -h`, `df -i`, `ps aux --sort=-%cpu | head`, `ps aux --sort=-%mem | head`, `ss -lntup`, `ip route`, `systemctl status <service>`.

## Service Failure

Check service status, recent journal logs, dependency availability, ports, config syntax if the checker is read-only, recent deployments, and restart history. Do not restart or reload without confirmation.

Evidence files: systemd unit files, app config files, `/var/log/`, service-specific log directories.

## Resource Pressure

For CPU, memory, disk, inode, or IO complaints, separate current pressure from historical pressure. Look for OOM kills, runaway processes, rapidly growing logs, full partitions, inode exhaustion, and high IO wait. Cleanup, truncation, or process killing requires confirmation.

## Network, DNS, And Ports

Check listening sockets, local routes, DNS resolution, connectivity to dependencies, proxy/firewall clues, certificate dates, and recent network changes. Firewall and route mutations require confirmation.

## Containers And Kubernetes

If Docker or Kubernetes is in scope, inspect running containers, images, logs, restart counts, pod status, events, and node health. Mutating commands such as restarts, deletes, rollouts, and scaling require confirmation.

## Vulnerability Verification

First ask for CVE ID, component, affected version range, scanner or advisory source, scanner evidence, target host, exposure path, production status, and whether remediation is allowed.

Verify whether the component exists, which version is installed or running, whether it is exposed, whether configuration mitigates it, and whether scanner evidence matches the actual host. Classify results as:

- Confirmed affected
- Suspected affected, needs more evidence
- No affected evidence found
- Likely scanner false positive
- Unable to verify because information is missing

Remediation such as package upgrade, config change, image replacement, service restart, or firewall change requires confirmation. After remediation, repeat read-only verification and compare before/after evidence.

## Compromise Or Attack Trace Check

First ask why compromise is suspected, the time window, alerts seen, whether evidence preservation matters, and what actions are forbidden.

Check login records, failed logins, auth logs, sudo traces, new users, SSH keys, cron jobs, systemd persistence, suspicious processes, listening ports, outbound connections, recent file changes, web access logs, and application logs.

Do not delete files, kill processes, disable accounts, rotate passwords, block IPs, isolate hosts, or change credentials without confirmation.

Conclusion categories:

- Clear compromise evidence found
- Suspicious clues found, more confirmation needed
- No obvious compromise traces found
- Insufficient evidence to judge

## Vague Business Slowness

When a non-technical user says a server or business is slow, ask what is slow, when it started, whether it is constant or intermittent, who is affected, whether there are errors or timeouts, what changed recently, and what role the target host plays.

If the user cannot answer, run a conservative server-side read-only baseline and say clearly that no host-level anomaly does not prove the business is healthy.
