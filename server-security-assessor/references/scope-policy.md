# Scope policy

Freeze the user-supplied boundary before any command is generated. Keep external and internal scopes separate in Both mode.

- Full coverage means the full checklist inside supplied assets, not discovery of related assets.
- Targeted coverage permits only the listed hosts, ports, URL prefixes, services, directories, files, logs, and time ranges.
- Report-directed validation permits only the report targets and findings.
- Windows supports External only. Linux supports External, Internal, or Both.
- Reject redirects, DNS answers, sibling hosts, virtual hosts, mounted paths, or symlink destinations outside the frozen boundary.

