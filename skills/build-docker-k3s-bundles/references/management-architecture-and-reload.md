# Management Architecture And Configuration Reload

Read this reference whenever generating or modifying `manage.sh`, adding a management command, dispatching complex work to Python, or supporting reload after an operator manually edits Docker Compose or K3s YAML configuration.

## Current Portable Implementation Takes Precedence

For new bundles, use `portable-management.md` and the supplied Python manager. The old Shell layout and registry examples below apply only to legacy implementations or approved adapter design; they do not require generating Shell modules, `management/commands.yaml`, or a second dispatcher. The actual layout is root `manage.sh` + `manage.pyz`, bundled `runtime/python/`, and `management/release.json`. Its explicit allowlist is `managebase.operations.COMMANDS`; parsing, locks and operation lifecycle live in Python, not the launcher.

This release does not implement the quick-reload command surface below. Those sections are safety/design requirements for a future scoped extension, not copy-ready supported commands. Installation, reinstall, uninstall and upgrade orchestration remain installer responsibilities. Do not package upgrade orchestration inside the management base.

## Legacy Shell Entrypoint

For an explicitly retained legacy Shell implementation only, `manage.sh` is a stable front controller, not the implementation of every feature. The following Shell duties and registry example are not instructions for the portable launcher. Limit a legacy front controller to:

- resolving and validating the installed bundle root
- loading a small common bootstrap library
- reading the explicit command registry
- parsing global options such as `--help`, `--non-interactive`, and `--dry-run`
- establishing authorization, locks, state paths, audit logs, and redaction
- dispatching exactly one registered command module
- preserving the selected module's exit code and printing its recovery information

Put concrete behavior such as service control, reload, backup, exposure, firewall and diagnostics in separate modules. Do not use `eval`, filename-derived execution, or automatic discovery from operator-writable directories.

Legacy Shell framework example (new portable bundles use the paths above):

```text
manage.sh
management/
|-- commands.yaml
|-- commands/
|   |-- services.sh
|   |-- reload.sh
|   |-- exposure.sh
|   `-- firewall.sh
|-- lib/
|   |-- bootstrap.sh
|   |-- dispatch.sh
|   |-- state.sh
|   `-- runtime-adapters.sh
`-- python/
    `-- bundle_manage/
```

For legacy bundles, retain existing names only under the explicit legacy/migration policy in `installation-layout.md`; do not create a parallel framework.

## Command Registry And Module Contract

The portable implementation uses the Python `COMMANDS` allowlist. A retained legacy implementation may use a declarative, bundle-owned allowlist mapping command paths to implementation type and entrypoint; validate its schema and ownership before dispatch.

Conceptual registry entry:

```yaml
commands:
  reload:
    type: shell
    entrypoint: management/commands/reload.sh
  diagnostics collect:
    type: python
    entrypoint: bundle_manage.diagnostics
```

Every command module must provide the same observable lifecycle where applicable:

1. parse and validate command-specific arguments
2. discover current state
3. build an explicit plan
4. preview and authorize impactful changes
5. create backups or rollback metadata
6. apply the change
7. verify the result
8. roll back changes from the current operation when verification fails
9. atomically record the result and recovery command

Use shared helpers for locks, logging, state, confirmation, ownership checks, runtime selection, and redaction. Keep service-specific decisions inside the relevant module or manifest adapter.

Modules return documented exit codes and a small structured result containing status, summary, changed resources, verification, and recovery command. Avoid parsing human-oriented console prose between modules.

## Python-Backed Management

The portable base keeps business logic in Python. Do not add Shell modules to it. The following shared safety contract also applies to retained legacy Python-backed implementations.

- Dispatch Python through a single verified wrapper rather than invoking an arbitrary interpreter from each module.
- Prefer a bundle-contained Python runtime for offline or version-sensitive behavior. A system Python may be used only after checking the required version and modules.
- Vendor wheels or dependencies needed offline and verify them with package checksums. Never run an implicit network `pip install` during management.
- Pass structured input through validated JSON or protected state files. Do not put secrets in command-line arguments or environment dumps.
- Keep the same preview, approval, locking, audit, verification, and rollback contract as shell modules.
- Preserve stdout for operator output and use a documented channel or result file for machine-readable results.

The bundle manifest should declare whether Python-backed management is enabled, the runtime source and version, dependency inventory, platform support, and verification status.

## Quick Reload Interface

Provide a convenient default command and explicit runtime forms:

```text
./manage.sh reload [--dry-run]
./manage.sh reload compose [<service>...] [--file <path>] [--dry-run]
./manage.sh reload k3s [--file <path>] [--namespace <name>] [--dry-run]
./manage.sh reload status
./manage.sh reload rollback <reload-id>
```

`./manage.sh reload` should use the fixed installed paths, manifest, installed runtime, and stored fingerprints to identify changes only within registered inputs. Never search the host or current directory for candidate configuration. If exactly one safe scope is determined, preview and reload it. If both Docker and K3s are enabled, multiple unrelated files changed, or the affected scope is ambiguous, show the candidates and require an explicit runtime or file selection.

By default accept only files declared by the bundle manifest or registered as user-managed overrides beneath approved configuration roots. Reject path traversal, symlink escapes, device files, and unrelated arbitrary YAML. Supporting `--file` does not grant permission to apply any host file.

Reload means revalidate and reapply configuration. It must not implicitly pull images, build images, upgrade versions, prune resources, remove volumes, delete PVCs, remove orphans, or restart unaffected services.

## Common Reload Flow

Before applying either runtime:

1. acquire the bundle management lock
2. resolve the full ordered input set, including Compose overrides or K3s multi-document files
3. compare current fingerprints with last successfully applied fingerprints
4. parse the files with a structured YAML or runtime-native parser
5. render and validate the effective configuration
6. calculate and display the affected resources and likely restart or rollout scope
7. store the edited files, last-known-good files, rendered configuration, and live-state metadata in a protected reload backup
8. apply only the approved scope
9. run runtime verification and declared service health checks
10. record a reload ID, new fingerprints, observed results, and an exact rollback command

If validation fails, do not change runtime state. Show the file and runtime error with secret values redacted.

If apply or verification fails, automatically roll back only when the rollback plan is complete and safe. Otherwise stop, preserve the backup, and print the exact `reload rollback <reload-id>` command with an explanation of what remains changed.

## Docker Compose Reload

Use the exact Compose project name, environment files, profiles, and ordered `-f` file list recorded by the installation state. Do not run against a different implicit project because the current directory changed.

Required behavior:

- validate with the installed Compose implementation's configuration renderer before apply
- retain a redacted rendered-config snapshot for comparison while protecting secrets
- identify changed services where reliable; allow the operator to choose targeted or whole-project reconciliation when dependencies make the scope uncertain
- use declarative reconciliation equivalent to `compose up -d` for the approved services, adding `--no-deps` only when dependency analysis proves it appropriate
- explicitly use `--pull never` and `--no-build` for offline reconciliation; do not enable pulling/building, `--remove-orphans`, volume removal or pruning unless separately requested, previewed and confirmed
- verify container state and declared health checks after reconciliation
- restore the last-known-good Compose inputs and reconcile them during rollback

Manual edits may change port bindings, mounts, networks, environment, or dependencies and therefore recreate a container. The preview must state which services are expected to be recreated and the likely interruption.

## K3s YAML Reload

Resolve namespace, context, cluster identity, and selected node authorization from installation state. Refuse to apply when the current context does not match the recorded cluster unless the operator explicitly selects and confirms another authorized target.

Required behavior:

- parse every YAML document and reject unknown or empty accidental inputs according to bundle policy
- run client-side validation and, when the authorized API server is reachable, server-side dry-run or equivalent validation
- show a diff before apply when the installed `kubectl` supports it
- back up the last-known-good declarative files and the minimum live metadata needed for recovery
- apply only the selected files and namespace scope
- wait for rollout of affected workload controllers and run declared health checks
- treat ConfigMaps, Secrets, Services, storage, CRDs, and immutable-field changes according to resource-specific rollback limits
- never delete resources merely because they disappeared from an edited file unless an explicit prune policy and ownership allowlist were separately confirmed

For rollback, prefer the previous declarative bundle-owned manifest. `rollout undo` alone is insufficient for changes to Services, ConfigMaps, Secrets, storage, or other non-workload resources. Protect secret-bearing backups with restrictive permissions and redact them from logs and reports.

## State And Concurrency

Record reload operations separately from installation checkpoints. Each record should include:

- reload ID, timestamp, operator mode, runtime, cluster or Compose project identity
- selected source files and before/after fingerprints
- affected services or Kubernetes resources
- validation, preview, apply, rollout, and health results
- backup locations, rollback eligibility, and rollback result
- final status and exact recovery command

Use atomic writes and one mutation lock shared with other management commands that could change the same workloads. `reload status` must identify successful, failed, rolled-back, partially rolled-back, and externally superseded reloads.

## Documentation And Validation

The Simplified Chinese operations guide must explain:

- where operators may safely edit Compose and K3s configuration
- the fast `manage.sh reload` path and explicit runtime forms
- validation and preview behavior
- when Compose may recreate containers or K3s may roll out workloads
- rollback commands, backup locations, and limitations
- that reload does not pull, build, upgrade, prune, or delete storage by default

At minimum, validate:

- unknown commands cannot execute arbitrary modules
- only the selected operation executes; shared Python imports must have no workload side effects
- Python runtime and offline dependencies pass checksum and version checks
- a no-change reload exits idempotently without restarting workloads
- invalid YAML and invalid effective Compose configuration stop before apply
- ambiguous runtime or changed-file selection requires an explicit choice
- Compose project identity and ordered override files are preserved
- targeted Compose reload does not restart unrelated services
- K3s context mismatch and namespace escape are rejected
- dry-run and diff do not mutate runtime state
- successful reload updates fingerprints and health results
- failed verification exercises rollback and preserves recovery data
- concurrent reload, exposure, service, and upgrade operations respect the shared lock
