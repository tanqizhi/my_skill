---
name: build-docker-k3s-bundles
description: Create or modify reproducible container installation bundles for Docker, Docker Compose, or K3s, including full, PaaS-only, SaaS-only, custom, image-only, installable, and upgrade packages. Use when Codex needs to collect deployment requirements, organize public/private/provided images, generate manifests and management scripts, prepare offline artifacts, or validate an existing container bundle. Do not use for routine operation of an already deployed cluster unless the requested work changes or rebuilds the bundle.
---

# Build Docker/K3s Bundles

Create safe, reproducible installation bundles driven by a single declarative bundle manifest rather than unrelated handwritten scripts.

## Workflow

1. Determine whether this is a new bundle or a modification of an existing bundle.
2. Read `references/requirements.md`, collect missing blocking information, and present a concise requirement summary for confirmation.
3. Model the request across three independent dimensions:
   - content scope: `full`, `paas`, `saas`, or `custom`
   - package mode: `installable`, `images-only`, or `upgrade`
   - deployment target: `docker`, `k3s`, or both
4. For SaaS-only or custom bundles, resolve dependencies using `include`, `external`, or `layered` policy. Prefer `layered` when a reusable PaaS base package is appropriate.
5. Build or update the bundle manifest according to `references/bundle-manifest.md`.
6. Follow the applicable path in `references/workflow.md` and the engineering rules in `references/implementation-guidance.md`.
7. For every installable bundle, make the installation entrypoint generate a concise post-install deployment and operations report according to `references/implementation-guidance.md`.
8. Validate generated configuration, checksums, image metadata, scripts, report generation, upgrade behavior, rollback behavior, and package contents before reporting completion.

## Interaction Rules

- Ask grouped questions when missing information blocks a safe or materially correct decision.
- Do not ask about trivial naming or formatting choices that can use safe defaults.
- Show assumptions in the requirement summary before implementation.
- Ask immediately before destructive actions, remote installation, host configuration changes, credential use, or security-risk acceptance.
- Never treat approval to generate a bundle as approval to modify a live host or remote node.
- Never place SSH, registry, sudo, token, or application secrets directly in generated source files, logs, or the bundle manifest.
- When the user is unavailable, stop at the affected step and preserve completed non-destructive work.

## Required Invariants

- Use immutable image digests when available; retain human-readable tags as metadata.
- Record image source, platform architecture, business category, owning service, and verification result.
- Do not remove a private image from the acquisition plan merely because it is categorized as PaaS. Remove it only when a verified supplied artifact or reachable source replaces the download.
- Do not loop indefinitely searching for a vulnerability-free version. Offer compatible upgrade, mitigation, documented risk acceptance, or failure.
- Make installation and management operations idempotent where practical.
- Back up affected configuration and retain rollback metadata before upgrades.
- Treat Docker and K3s differences as deployment adapters; share image, service, dependency, and security metadata.
- Generate a validation report even when no Linux test host is available, clearly distinguishing static validation from installation testing.
- Every installable bundle must generate `reports/deployment-and-operations.md` when its installation entrypoint finishes. Generate the report for successful, partially successful, and failed runs when the filesystem remains writable; never let report-generation failure hide the installation result.
- Base the post-install report on observed execution results rather than planned state. Redact secrets, state which checks were not executed, and print the report path in the final console summary.

## References

- Full decision flow and management flow: `references/workflow.md`
- Questions, confirmations, and stopping rules: `references/requirements.md`
- Bundle manifest fields and example: `references/bundle-manifest.md`
- Package layout, module boundaries, security, and tests: `references/implementation-guidance.md`
- Starter manifest: `assets/templates/bundle.yaml`
