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

## Image Identity

Store both:

- `tag` for readability and operator interaction;
- `digest` for immutable identity and verification.

A locally calculated digest is useful only when compared with a digest obtained from a trusted source or previously approved artifact record.

## Generated Files

Generated deployment files should contain a marker or be listed in a generation report. During modifications, do not overwrite files identified as user-managed without explicit confirmation.
