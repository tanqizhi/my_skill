# Scope policy

Freeze the user-supplied boundary before any command is generated. Keep external and internal scopes separate in Both mode.

- Full coverage means the full checklist inside supplied assets, not discovery of related assets.
- Targeted coverage permits only the listed hosts, ports, URL prefixes, services, directories, files, logs, and time ranges.
- Report-directed validation permits only the report targets and findings.
- Windows supports External only. Linux supports External, Internal, or Both.
- Reject redirects, DNS answers, sibling hosts, virtual hosts, mounted paths, or symlink destinations outside the frozen boundary.

## Canonicalization

- Lowercase URL schemes and hostnames. Preserve explicit ports, paths, and query strings.
- Treat a targeted URL path as a prefix boundary only for active scans. `/admin` includes `/admin/users`, but not `/`, `/api`, or `/administrator`.
- Require an exact URL, including query string, during report-directed validation unless the imported report row explicitly declares a path prefix.
- Accept only absolute internal paths. Reject `..`, null bytes, and lexical lookalikes such as `/etc/ssh-old` when `/etc/ssh` is allowed.
- Do not follow redirects or symlinks automatically. Present the resolved destination and require it to be independently in scope.

## Mode validation

- External requires at least one explicit IP, hostname, URL, or report asset.
- Internal requires Linux, an SSH destination, and a supplied account.
- Both requires independently valid external and internal inputs; one side may be full while the other is targeted.
- For full coverage, expand checks only within supplied assets. Never add adjacent ports, hosts, domains, cloud resources, or internal mounts merely because a tool discovers them.
