# Forensics

Use this workflow only when the user selects forensic mode directly or confirms an upgrade after suspicious evidence is shown. Record which evidence triggered an upgrade.

## Plan

Load `checks/forensic-checks.json` and filter it by distro, target scope, directories, logs, and time range. The planner must reject forensic categories unless `forensic_enabled` or `forensic_upgrade_confirmed` is true.

Order collection to preserve volatile context first: process tree, connections, login history, persistence metadata, recent temporary-file metadata, then the bounded journal timeline. Apply strict time and output-size limits.

## Preserve evidence

Capture the minimum relevant output locally. Record check ID, collection time, source host, command argv, privilege, exit status, and SHA-256. Redact secrets before writing the evidence package. Do not upload evidence or samples to third-party services.

## Boundaries

Do not deploy an agent, kill a process, quarantine or delete a file, alter persistence, dump credentials, or acquire full memory/disk images in the default workflow. Those actions require a separate explicit scope, impact review, storage plan, and authorization.

Treat a suspicious indicator as evidence requiring correlation, not proof of compromise by itself. Preserve contrary evidence and coverage gaps in the report.
