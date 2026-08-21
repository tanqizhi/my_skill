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
|-- config/
|   `-- *.env.example
|-- scripts/
|   |-- lib/
|   |-- install-runtime.sh
|   |-- import-images.sh
|   |-- deploy-services.sh
|   |-- manage-services.sh
|   |-- upgrade.sh
|   `-- rollback.sh
|-- inventory/
|   |-- nodes.example.yaml
|   `-- images.yaml
`-- reports/
    |-- validation.md
    |-- image-sources.yaml
    `-- security-exceptions.yaml
```

Omit directories that are irrelevant to the selected package mode. An `images-only` package does not need runtime installation or service deployment modules.

## Module Boundaries

- Preflight: verify OS, architecture, disk, ports, runtime state, permissions, files, and required external dependencies.
- Runtime adapter: install or validate Docker, Compose, or K3s without mixing service-specific logic into runtime setup.
- Image acquisition: pull, copy, load, verify, inventory, and classify images.
- Deployment adapter: translate common service metadata into Docker or K3s deployment artifacts.
- Management: start, stop, restart, status, version, import, switch, and health operations based on the bundle manifest.
- Upgrade: calculate current-to-target differences, validate compatibility, back up configuration, apply changes, and retain rollback data.
- Remote K3s: distribute only approved artifacts, verify node identity and architecture, execute bounded operations, and report per-node results.

## K3s Considerations

Before generating remote installation behavior, confirm:

- server and agent roles;
- node addresses and expected host keys;
- SSH key or password mechanism;
- K3s token injection method;
- image distribution strategy for every required node;
- private registry and certificate strategy;
- storage class, persistent paths, ingress, load balancing, DNS, and required ports;
- upgrade ordering and rollback limitations.

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
- Offer `--dry-run` for impactful operations where practical.
- Offer non-interactive execution with explicit configuration inputs.
- Produce useful exit codes and stage-aware logs.
- Redact secrets from logs and diagnostic output.
- Check prerequisites before making changes.
- Back up files before replacement and record how to restore them.
- Separate generated defaults from user-managed overrides.

## Validation Levels

1. Manifest validation: required fields, references, categories, dependency graph, duplicate IDs, versions, digests, and target platforms.
2. Static validation: shell syntax, YAML parsing, configuration consistency, file references, executable permissions, and secret scanning.
3. Package validation: checksums, archive completeness, expected image count, runtime binaries, architecture, and reproducibility metadata.
4. Local installation: clean-host install, repeated install, start, stop, restart, status, and uninstall behavior where supported.
5. Upgrade validation: supported old version to target version, configuration migration, data preservation, and rollback.
6. K3s validation: server bootstrap, agent join, image availability on required nodes, workload scheduling, persistence, and node-specific failure reporting.

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
