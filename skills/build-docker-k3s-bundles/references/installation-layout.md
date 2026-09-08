# Installation Layout Contract

This is the mandatory `layout.version: 1` contract for newly generated bundles. It defines the files an independent management tool can rely on after installation. It takes precedence over illustrative layouts elsewhere in this skill.

## Root And Package Modes

- Default installed root: `/opt/bundles/<bundle.name>`. Restrict bundle and service IDs used in paths to lowercase letters, digits, and hyphens, beginning with a letter.
- An explicitly selected absolute `--install-dir` may override the root on first installation. Show the resolved root in the requirement summary and installation preview. Internal relative paths below are fixed, not individually configurable.
- Distinguish the extracted package directory from the installed root. Never choose the installed root implicitly from the current working directory or extraction location. Install required artifacts before invoking installed management commands.
- Persist the canonical installed root and instance identity in `state/installation.json`. Subsequent operations must use that root and identity; reject mismatches or missing state rather than searching the host or silently initializing a new instance. Recovery of incomplete installation belongs to the installer.
- Entrypoints locate their root from their own canonical installed location, not `$PWD`. Parse metadata as structured data; do not source it as shell code.
- Reject `/` as an install root, traversal, unexpected symlink escapes, overlapping instance roots, and an existing directory with unknown ownership. Do not overwrite or adopt an unrelated installation.
- `installable` packages must establish this layout. `upgrade` packages may contain only changed artifacts, but must preserve the target instance's root, paths, and identity. `images-only` packages use the applicable package paths below without creating installed state or management entrypoints.
- For K3s, install node-local artifacts under the recorded root on each managed node and record which node owns each artifact. This contract does not relocate Docker, K3s, CNI, or operating-system-managed directories.

## Fixed Paths

All paths below are relative to the installed root, or to the package root for shipped artifacts. Omit runtime-specific artifacts only when that runtime is disabled. Runtime-created directories must exist before their first use.

| Path | Purpose and ownership |
| --- | --- |
| `bundle.yaml` | Installed declarative manifest; installer-maintained, contains no secrets |
| `install.sh`, `manage.sh` | Stable public entrypoints |
| `management/commands.yaml` | Explicit management command registry |
| `management/commands/`, `management/lib/`, `management/python/` | Management implementation; not operator-editable configuration |
| `scripts/`, `scripts/lib/` | Installer helpers and lifecycle modules |
| `deploy/docker/compose.yaml` | Single base Compose project file, shipped by the package |
| `config/compose.override.yaml` | Operator-maintained Compose overrides, always loaded after the base |
| `config/compose.env` | Non-secret Compose interpolation inputs, explicitly loaded |
| `config/services/<service-id>/` | Application configuration, non-secret service environment files, endpoint settings |
| `secrets/<service-id>/` | Runtime-created credentials; never populated with real credentials in the archive |
| `deploy/k3s/<service-id>.yaml` | Declared service workload manifests; enumerate any shared resource files under `deploy/k3s/` explicitly |
| `config/k3s/` | Optional explicitly registered user-managed K3s inputs; never applied via a recursive glob |
| `data/<service-id>/` | Default persistent bind-mounted application data |
| `logs/management/` | Installer and management logs |
| `logs/services/<service-id>/` | Application file logs when needed; runtime stdout logs remain runtime-managed |
| `state/installation.json` | Atomic installed-layout and instance record |
| `state/install/`, `state/uninstall/`, `state/reload/`, `state/exposure/`, `state/firewall/` | Separate checkpoints and operation records |
| `state/locks/` | Shared mutation-lock location |
| `backups/<operation-id>/` | Protected configuration snapshots and rollback metadata |
| `runtime/docker/`, `runtime/compose/`, `runtime/k3s/`, `runtime/python/` | Applicable offline runtime artifacts, not runtime-owned system data |
| `images/paas/`, `images/saas/` | Offline image artifacts |
| `bootstrap/dependency-data/` | Declared dependency initialization inputs |
| `inventory/` | Image inventory and node inventory |
| `reports/`, `docs/` | Reports and Chinese manuals at the existing required filenames |
| `README.md`, `checksums.txt` | Package entry documentation and shipped-artifact checksums |

Do not invent alternative configuration roots such as `conf/`, `etc/`, or service directories alongside the installed root. Application-native filenames beneath `config/services/<service-id>/` are allowed, but must be explicitly listed in the service manifest. Do not locate inputs by scanning for `*.yaml`, choosing the first match, or falling back to the extraction directory.

External storage is an explicit exception, not an alternative configuration layout. For an approved external bind path, named volume, or PVC, declare its exact identity, owning service, ownership, and preservation policy in the manifest and installation state. Never infer ownership from a mount path. Shared runtime storage retains its native location.

## Configuration And Installed State

- Docker uses exactly `deploy/docker/compose.yaml`, then `config/compose.override.yaml`, with `config/compose.env` explicitly selected. The installer initializes missing override and env files to valid, non-secret defaults, including a valid no-op override when no customization is needed.
- Use the installed root as the explicit Compose project directory. Author bind paths and referenced files consistently with this base and validate the rendered configuration. Record the exact project name, ordered file list, env file list, and enabled profiles. Do not rely on implicit `.env` discovery, ambient `COMPOSE_*` settings, or the caller's working directory.
- Service-specific Compose configuration points to the shared base file and declares the exact Compose service name. Put service env files at `config/services/<service-id>/service.env`; do not treat env files as executable scripts.
- K3s inputs and their ordering, namespace, context, and cluster identity are explicit. Register each applicable file under `deploy/k3s/` or `config/k3s/`; a directory's existence is not authorization to apply all of its contents. Secret-bearing runtime manifests, if required, live under `secrets/<service-id>/` and require an explicit protected reference.
- `state/installation.json` records at least `layout_version`, `bundle_name`, `bundle_version`, `instance_id`, `install_root`, `deploy_targets`, the applicable `compose` or `k3s` identities and input lists, and `storage` ownership records. Use JSON objects/lists, not serialized shell commands. Update atomically; do not claim deployment success merely because this record exists.
- All mutable and secret-bearing files must have appropriate ownership and restrictive permissions. Management executables and the command registry must not be writable by application service accounts. Never recursively chmod/chown persistent application data to impose a generic permission scheme.
- Preserve operator changes in `config/`, `secrets/`, and manually edited deployment files during reinstall and upgrade. Preview differences and back up affected files before any approved replacement; never blindly unpack a new archive over the installed instance.
- Keep last-known-good configuration separately from newly edited input. Backups that include secrets require the same protection and redaction as the originals.
- Default uninstall retains configuration, secrets, data, backups, logs, reports, manuals, and recovery state. Existing explicit destructive-scope and resource-ownership rules still apply.
- Do not ship runtime state, production data, real credentials, or execution logs in a new installation archive. Checksums describe shipped artifacts; record mutable installed fingerprints separately.

## Existing Bundles

Inspect existing paths and their consumers before modifying an older bundle. Do not silently move files, rename Compose projects, change mount sources, or create a second configuration tree. If it does not satisfy version 1, report the differences and request approval for an explicit migration with backups and rollback. Until migrated and verified, label it legacy rather than claiming layout-version-1 compatibility. Normal non-migration maintenance may retain its existing layout.

## Required Validation

Before delivery, record static/package checks for:

1. Manifest layout version, fixed paths, service configuration references, enabled-runtime artifacts, and absence of unresolved placeholders.
2. Agreement between installation destinations, management inputs, Compose mounts, K3s references, manuals, and the directory contract.
3. No embedded credentials, packaged runtime state, traversal, unexpected symlink escapes, or unregistered configuration discovery.
4. Explicit storage exceptions and preservation defaults; no implicit deletion of shared or externally owned storage.

On an authorized Linux test host, additionally verify:

1. Installation from an unrelated extraction directory into the default root and an explicitly selected alternate root.
2. Management from another working directory, using the same project identity and effective inputs.
3. Missing or mismatched installation records stop management with a recovery explanation instead of guessing.
4. Reinstall and upgrade preserve edited configuration, credentials, and data; default uninstall retains them.
5. Independent instances do not share unintended Compose identities, state, or data.

The Chinese installation manual must include the actual absolute directory table, file purposes, editable locations, and storage exceptions. Distinguish executed static checks from unexecuted host tests in the validation report.
