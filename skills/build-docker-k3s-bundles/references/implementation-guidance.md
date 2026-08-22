# Implementation Guidance

## Suggested Package Layout

```text
bundle-name/
|-- bundle.yaml
|-- README.md
|-- install.sh
|-- manage.sh
|-- checksums.txt
|-- images/
|   |-- paas/
|   `-- saas/
|-- runtime/
|   |-- docker/
|   |-- compose/
|   `-- k3s/
|-- deploy/
|   |-- docker/
|   `-- k3s/
|-- bootstrap/
|   `-- dependency-data/
|-- config/
|   `-- *.env.example
|-- scripts/
|   |-- lib/
|   |-- install-runtime.sh
|   |-- import-images.sh
|   |-- initialize-dependencies.sh
|   |-- deploy-services.sh
|   |-- manage-services.sh
|   |-- manage-exposure.sh
|   |-- manage-firewall.sh
|   |-- upgrade.sh
|   `-- rollback.sh
|-- state/                       Generated at runtime
|-- inventory/
|   |-- nodes.example.yaml
|   `-- images.yaml
`-- reports/
    |-- validation.md
    |-- deployment-and-operations.md
    |-- image-sources.yaml
    `-- security-exceptions.yaml
```

Omit directories that are irrelevant to the selected package mode. An `images-only` package does not need runtime installation or service deployment modules.
For an installable bundle, `deployment-and-operations.md` is created or refreshed by the installation entrypoint from the actual execution result; it is not a prefilled claim that deployment succeeded.

## Module Boundaries

- Preflight: verify OS, architecture, disk, ports, runtime state, permissions, files, and required external dependencies.
- Runtime adapter: install or validate Docker, Compose, or K3s without mixing service-specific logic into runtime setup.
- Image acquisition: pull, copy, load, verify, inventory, and classify images.
- Deployment adapter: translate common service metadata into Docker or K3s deployment artifacts.
- SaaS bootstrap: apply declared data or configuration initialization for any dependency type only after its target is ready and before dependent SaaS starts.
- Installation state: persist atomic stage checkpoints, input fingerprints, observed results, failure details, and recovery commands.
- Management: start, stop, restart, status, version, import, switch, health, external exposure, and bundle-owned NAT operations based on the bundle manifest.
- Upgrade: calculate current-to-target differences, validate compatibility, back up configuration, apply changes, and retain rollback data.
- Remote K3s: distribute only approved artifacts, verify node identity and architecture, execute bounded operations, and report per-node results.

## K3s Considerations

Before generating remote installation behavior, confirm:

- server and agent roles;
- node addresses and expected host keys;
- SSH key or password mechanism;
- K3s token injection method;
- image distribution strategy for every required node;
- the exact node name and IP address for every server and agent so failed NAT work can be identified and recovered;
- private registry and certificate strategy;
- storage class, persistent paths, ingress, load balancing, DNS, and required ports;
- upgrade ordering and rollback limitations.
- whether bundle-owned NAT rules must be synchronized to every server and agent node and how rule persistence is managed.

Do not bundle `sshpass` by default. Use it only when password automation is explicitly required and approved. Prefer SSH keys and avoid recording credentials in command lines or logs.

## Security and Provenance

- Resolve platform-compatible versions before acquisition.
- Record registry or source URL, tag, digest, acquisition time, target platforms, and verification result.
- Scan the exact digest included in the package.
- If no acceptable fixed version exists, present compatible upgrade, mitigation, exception, or failure choices.
- Track documented exceptions separately from the main manifest so operators can review accepted risks.
- Avoid insecure registries and disabled TLS verification unless explicitly approved and documented.
- Generate an SBOM when suitable tooling is available; otherwise generate an image source and component inventory.

## Script Behavior

- Use strict error handling appropriate to the implementation language.
- Support repeated execution without duplicating resources or corrupting state.
- Provide `--status`, `--resume`, `--restart-from <stage>`, and `--reinstall <service-or-stage>`. Preserve persistent data and user configuration during reinstall unless a separately confirmed clean mode is requested.
- Store each completed stage with an input fingerprint and observed output using an atomic replace. When inputs change, invalidate only the affected stage and its downstream dependents.
- Offer `--dry-run` for impactful operations where practical.
- Offer non-interactive execution with explicit configuration inputs.
- Produce useful exit codes and stage-aware logs.
- Redact secrets from logs and diagnostic output.
- Check prerequisites before making changes.
- Back up files before replacement and record how to restore them.
- Separate generated defaults from user-managed overrides.
- On every terminal installation outcome, attempt to write `reports/deployment-and-operations.md`, then print its path in the console summary. Preserve the installation exit code if report generation fails.

Read `saas-bootstrap-and-network-management.md` when the bundle includes SaaS, resumable installation, Docker or K3s external exposure, or bundle-owned NAT management.

## Reference Pseudocode

The files under `references/examples/` are intentionally non-executable design sketches:

- `manage-exposure.pseudocode.sh` demonstrates the discover, plan, preview, confirm, backup, apply, verify, and rollback shape for Docker publishing and K3s NodePort management.
- `manage-firewall.pseudocode.sh` demonstrates owned-chain discovery and reuse, ordered CRUD, all-node synchronization, and the continue-or-rollback decision after a node failure.

Each example exits immediately and contains adapter stubs. Do not ship it in a generated bundle, remove its guard, or treat its placeholder calls as implementation. Generate a new module from the bundle manifest and verified target environment, then validate that module independently.

## Post-Install Deployment and Operations Report

Every installable bundle must generate a concise Markdown report at `reports/deployment-and-operations.md` after the installation entrypoint finishes. An upgrade bundle that also deploys or changes running services must refresh the same report. An `images-only` bundle is exempt.

Build the report from observed results and include:

- execution time, installation result (`success`, `partial`, or `failed`), target host or nodes, operating system, architecture, and Docker or K3s runtime version;
- deployed services, image tags and digests, service or workload state, health-check result, and exposed addresses or ports;
- dependency-initialization tasks attempted, skipped, completed, or rolled back, plus SaaS dependency-configuration validation results;
- the latest installation checkpoint, resume or reinstall activity, and any invalidated or incomplete stage;
- the bundle-owned NAT table, parent chain, user-defined chain, jump placement, rule summary, and per-node synchronization result;
- important configuration, data, log, backup, and manifest paths;
- copy-ready commands for status, start, stop, restart, health checks, and log viewing, using the bundle's generated management interface;
- the applicable backup, upgrade, rollback, and recovery entrypoints;
- failed or skipped checks, remaining manual steps, and the location of detailed installation logs.

Keep the report short and operational. For multi-node K3s, add a compact per-node result table. Mark unavailable facts as `not checked` instead of guessing. Never include passwords, tokens, private keys, registry credentials, secret environment values, or unredacted credential-bearing command lines.

Generate the report on successful, partially successful, and failed runs whenever the bundle directory is writable. Report generation is best-effort during failure handling: failure to write the report must be visible, but it must not replace or mask the original installation result and exit code.

## Validation Levels

1. Manifest validation: required fields, references, categories, dependency graph, duplicate IDs, versions, digests, and target platforms.
2. Static validation: shell syntax, YAML parsing, configuration consistency, file references, executable permissions, and secret scanning.
3. Package validation: checksums, archive completeness, expected image count, runtime binaries, architecture, and reproducibility metadata.
4. Local installation: clean-host install, repeated install, start, stop, restart, status, and uninstall behavior where supported.
5. Upgrade validation: supported old version to target version, configuration migration, data preservation, and rollback.
6. K3s validation: server bootstrap, agent join, image availability on required nodes, workload scheduling, persistence, and node-specific failure reporting.
7. Resume and reinstall validation: controlled failures at representative stages, correct checkpoint reuse and invalidation, data-preserving reinstall, explicitly confirmed clean reinstall, and preservation of the original failure exit code.
8. SaaS bootstrap validation: provider-neutral task modeling, initialization ordering, idempotency, target-specific selectors, backup and rollback, provider-specific verification, and prevention of SaaS startup on failed prerequisites.
9. Exposure and NAT validation: Docker publishing, K3s NodePort range and collision checks, existing-chain reuse, repeated execution without duplicate chains or jumps, rule ordering, persistence, per-node drift, continue-or-rollback prompts, and exact failed-node recovery commands.

For installable bundles, also test report generation for a successful run and at least one controlled failure path. Verify that the report reflects observed state, contains the required operations commands, redacts secrets, and preserves the installation exit code.

When no Linux host is available, report only levels actually executed. Never label static checks as a successful installation test.

## Deliverables

Report:

- resolved requirements and defaults;
- generated package type and target platforms;
- included and excluded services;
- dependency decisions;
- image identities and verification status;
- security findings and accepted exceptions;
- tests executed and tests omitted;
- remaining manual steps;
- rollback and recovery instructions.
- the post-install report path and whether successful and failure-path report generation were validated.
- the installation resume state, SaaS bootstrap result, exposed ports, NAT chain reuse or creation decision, and per-node firewall synchronization status.
