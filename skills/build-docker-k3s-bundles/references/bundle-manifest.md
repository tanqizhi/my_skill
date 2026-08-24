# Bundle Manifest

The bundle manifest is the source of truth for package composition. Docker Compose files, K3s manifests, import lists, management menus, version reports, and validation reports should derive from it or be checked against it.

## Core Dimensions

- `content_scope`: `full`, `paas`, `saas`, or `custom`
- `package_mode`: `installable`, `images-only`, or `upgrade`
- `deploy_targets`: one or both of `docker` and `k3s`
- `dependency_policy`: `include`, `external`, or `layered`

These dimensions are independent. For example, a PaaS-only image archive for both runtimes is:

```yaml
content_scope: paas
package_mode: images-only
deploy_targets: [docker, k3s]
```

## Recommended Schema

```yaml
api_version: bundle.codex/v1alpha1

bundle:
  name: example-product
  version: 1.0.0
  content_scope: saas
  package_mode: installable
  deploy_targets:
    - docker
    - k3s
  dependency_policy: layered
  offline: true

localization:
  report_language: zh-CN
  manual_language: zh-CN

documentation:
  deployment_report: reports/deployment-and-operations.md
  installation_guide: docs/installation-guide.zh-CN.md
  operations_guide: docs/operations-guide.zh-CN.md

platforms:
  - os: linux
    architecture: amd64

runtime:
  docker:
    enabled: true
    version: ""
    compose_version: ""
  k3s:
    enabled: true
    version: ""

cluster:
  nodes:
    - name: server-1
      address: 192.0.2.10
      roles: [server]
    - name: agent-1
      address: 192.0.2.11
      roles: [agent]

installation:
  state_directory: state
  resume_enabled: true
  preserve_data_on_reinstall: true
  stages:
    - preflight
    - runtime
    - images
    - paas
    - dependency-init
    - saas-config
    - saas
    - exposure
    - health
    - report

uninstall:
  enabled: true
  entrypoint: install.sh
  resume_enabled: true
  preserve_data_by_default: true
  remove_images_by_default: false
  remove_runtime_by_default: false
  stages:
    - preflight
    - stop-saas
    - remove-saas
    - stop-paas
    - remove-paas
    - remove-exposure
    - remove-owned-nat
    - remove-generated-config
    - optional-images
    - optional-runtime
    - verify-retained-state
    - report

packages:
  requires:
    - name: example-product-paas
      version: ">=1.5.0,<2.0.0"

services:
  - id: application-api
    display_name: Application API
    category: saas
    enabled: true
    image:
      source_type: private-registry
      repository: registry.example.com/application-api
      tag: "2.1.0"
      digest: "sha256:replace-with-trusted-digest"
      platforms:
        - linux/amd64
    dependencies:
      - postgres
      - redis
    configuration:
      compose_file: deploy/docker/application-api.yaml
      k3s_manifest: deploy/k3s/application-api.yaml
      env_template: config/application-api.env.example
      dependency_targets:
        - id: primary-data-store
          kind: data-store
          provider: postgresql
          service: postgres
          endpoint_ref: config/postgres-endpoint
          selectors:
            database: application
          credential_ref: secrets/application-db
        - id: configuration-center
          kind: configuration-provider
          provider: nacos
          endpoint_ref: config/nacos-endpoint
          selectors:
            namespace: application
            group: DEFAULT_GROUP
          credential_ref: secrets/nacos
    healthcheck:
      type: http
      endpoint: /health
      port: 8080

  - id: postgres
    display_name: PostgreSQL
    category: paas
    enabled: false
    provided_by:
      package: example-product-paas
      version: ">=1.5.0,<2.0.0"

external_dependencies: []

saas_bootstrap:
  confirmation_required: true
  initialization_tasks:
    - id: application-schema
      owner_service: application-api
      kind: schema-migration
      provider: postgresql
      operation: apply-sql
      target_dependency: primary-data-store
      source: bootstrap/dependency-data/application.sql
      checksum: sha256:replace-with-file-digest
      run_before: application-api
      idempotency: migration-history
      backup_before_apply: true
      verify: schema-version
  configuration_checks:
    - service: application-api
      targets:
        - primary-data-store
        - configuration-center

exposure:
  docker:
    - service: application-api
      host_address: 0.0.0.0
      published_port: 8080
      container_port: 8080
      protocol: tcp
  k3s_node_ports:
    - service: application-api
      service_port: 8080
      node_port: 30080
      protocol: TCP

firewall:
  enabled: false
  backend: auto
  table: nat
  parent_chain: PREROUTING
  managed_chain: ""
  reuse_existing_chain: true
  sync_all_cluster_nodes: true
  jump_position: append
  persistence: prompt
  on_node_failure: prompt
  rules: []

security:
  vulnerability_policy:
    block_severities:
      - critical
      - high
    allow_documented_exceptions: true
  require_digest: true
  generate_source_record: true

testing:
  levels:
    - static
    - package
  remote_execution_authorized: false
```

## Service Classification

- `category` identifies business grouping: `paas` or `saas`.
- `enabled` determines whether the current bundle contains the service.
- `source_type` identifies acquisition: public registry, private registry, supplied archive, or locally built image.
- `provided_by` describes a service supplied by another bundle.
- `dependencies` expresses service relationships and must not be inferred only from image names.

## SaaS Bootstrap

- `saas_bootstrap.initialization_tasks` is an open list of dependency state required before a dependent SaaS service starts.
- An initialization task records kind, provider operation, source identity, target, order, idempotency, backup, verification, and blocked SaaS services; it never embeds credentials.
- `configuration.dependency_targets` is an open list. `kind` expresses a provider-neutral capability, `provider` selects provider-specific handling, and `selectors` carries provider-specific non-secret coordinates.
- The PostgreSQL and Nacos entries above are examples only. The same structure must support other data stores, configuration systems, caches, message brokers, storage, search, identity, policy, certificate, license, or future dependency types without changing the core schema.
- `saas_bootstrap.configuration_checks` makes all intended runtime targets auditable before SaaS starts.
- If SaaS is present and no dependency initialization is needed, record an explicit skipped decision and reason rather than leaving the question unresolved.

## Installation State and Network Management

- `installation.stages` defines checkpoint identities and dependency order. Runtime state records input fingerprints and observed results outside the declarative desired-state fields.
- `uninstall` declares the safe removal state machine. The default preserves data, configuration, images, shared runtimes, backups, reports, manuals, and resumable state; destructive scopes remain explicit.
- `exposure.docker` and `exposure.k3s_node_ports` drive management menus and deployment adapters.
- `firewall.table` is normally `nat`; `parent_chain` is normally `PREROUTING`; `managed_chain` is the bundle-owned user-defined chain.
- During modification, populate `managed_chain` with a verified existing chain name when compatible. At installation, recheck every target node before creating or reusing it.
- `sync_all_cluster_nodes` applies the desired owned NAT rules to every declared server and agent. `on_node_failure: prompt` requires an interactive continue-or-rollback decision and an exact failed-node recovery command.

## Chinese Documentation

- `localization.report_language` and `localization.manual_language` are `zh-CN` for the required Simplified Chinese outputs.
- `documentation` fixes the report, installation manual, and operations manual paths so scripts and terminal summaries can link to them.
- Commands and technical identifiers remain exact; their explanations, warnings, labels, and procedures are written in Simplified Chinese.

## Image Identity

Store both:

- `tag` for readability and operator interaction;
- `digest` for immutable identity and verification.

A locally calculated digest is useful only when compared with a digest obtained from a trusted source or previously approved artifact record.

## Generated Files

Generated deployment files should contain a marker or be listed in a generation report. During modifications, do not overwrite files identified as user-managed without explicit confirmation.
