---
name: build-docker-k3s-bundles
description: Create or modify reproducible container installation bundles for Docker, Docker Compose, or K3s, including full, PaaS-only, SaaS-only, custom, image-only, installable, and upgrade packages. Use when Codex needs to collect deployment requirements, organize public/private/provided images, prepare SaaS dependency initialization and configuration, generate resumable installers and management scripts, manage external ports or bundle-owned NAT rules, prepare offline artifacts, or validate an existing container bundle. Do not use for routine operation of an already deployed cluster unless the requested work changes or rebuilds the bundle.
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
5. When the bundle includes SaaS, inventory every PaaS or external dependency regardless of type, confirm whether dependency data or configuration must be imported before SaaS starts, and validate every SaaS service's effective dependency configuration.
6. When modifying an existing bundle, inspect its network-management code before designing NAT rules. Reuse a verified existing bundle-owned chain name and placement instead of creating a parallel chain.
7. Build or update the bundle manifest according to `references/bundle-manifest.md`.
8. Follow the applicable path in `references/workflow.md`, the engineering rules in `references/implementation-guidance.md`, and the SaaS, resumability, exposure, and firewall rules in `references/saas-bootstrap-and-network-management.md`.
9. For every installable bundle, make the installation entrypoint generate a concise post-install deployment and operations report according to `references/implementation-guidance.md`.
10. Validate generated configuration, checksums, image metadata, scripts, report generation, resumability, reinstall behavior, exposure and firewall management, upgrade behavior, rollback behavior, and package contents before reporting completion.

## Interaction Rules

- Ask grouped questions when missing information blocks a safe or materially correct decision.
- Do not ask about trivial naming or formatting choices that can use safe defaults.
- Show assumptions in the requirement summary before implementation.
- Ask immediately before destructive actions, remote installation, host configuration changes, credential use, or security-risk acceptance.
- Never treat approval to generate a bundle as approval to modify a live host or remote node.
- Never place SSH, registry, sudo, token, or application secrets directly in generated source files, logs, or the bundle manifest.
- When the user is unavailable, stop at the affected step and preserve completed non-destructive work.
- During a multi-node NAT rollout, if any node fails, show its node name, IP address, failure reason, and an exact local recovery command, then ask whether to continue or roll back. Do not infer the choice from silence.

## Required Invariants

- Use immutable image digests when available; retain human-readable tags as metadata.
- Record image source, platform architecture, business category, owning service, and verification result.
- Do not remove a private image from the acquisition plan merely because it is categorized as PaaS. Remove it only when a verified supplied artifact or reachable source replaces the download.
- Do not loop indefinitely searching for a vulnerability-free version. Offer compatible upgrade, mitigation, documented risk acceptance, or failure.
- Make installation and management operations idempotent where practical.
- Installable bundles must persist atomic stage checkpoints and support status, resume, restart-from-stage, and reinstall. Reinstall preserves persistent data and user configuration unless destructive cleanup is explicitly requested and confirmed.
- Back up affected configuration and retain rollback metadata before upgrades.
- Treat Docker and K3s differences as deployment adapters; share image, service, dependency, and security metadata.
- Do not start a SaaS service until every declared dependency-initialization task has completed or been explicitly skipped and its dependency configuration has passed validation.
- Management scripts must support external port discovery and CRUD for Docker port publishing and K3s NodePort services, with conflict checks, preview, backup, verification, and rollback.
- Treat `nat` as the iptables table, `PREROUTING` as its built-in chain, and the bundle-specific object as a user-defined chain. Manage only a verified bundle-owned chain and its jump; do not alter Docker, K3s, CNI, or unrelated user rules.
- At build-modification time and again at installation time, detect existing NAT chains and jumps. Reuse a compatible same-name chain idempotently, repair only missing owned entries, and stop for ambiguous ownership or incompatible contents.
- For a cluster, synchronize the desired bundle-owned NAT rules to every declared server and agent node, detect per-node drift, and record per-node results.
- The exposure and firewall pseudocode examples are design references only. Never execute, package, or copy them verbatim; replace every adapter stub with an implementation derived from the actual bundle, runtime, firewall backend, ownership rules, and authorization boundaries.
- Generate a validation report even when no Linux test host is available, clearly distinguishing static validation from installation testing.
- Every installable bundle must generate `reports/deployment-and-operations.md` when its installation entrypoint finishes. Generate the report for successful, partially successful, and failed runs when the filesystem remains writable; never let report-generation failure hide the installation result.
- Base the post-install report on observed execution results rather than planned state. Redact secrets, state which checks were not executed, and print the report path in the final console summary.

## References

- Full decision flow and management flow: `references/workflow.md`
- Questions, confirmations, and stopping rules: `references/requirements.md`
- Bundle manifest fields and example: `references/bundle-manifest.md`
- Package layout, module boundaries, security, and tests: `references/implementation-guidance.md`
- SaaS bootstrap, resumable installation, external exposure, and bundle-owned NAT management: `references/saas-bootstrap-and-network-management.md`
- Reference-only external exposure pseudocode: `references/examples/manage-exposure.pseudocode.sh`
- Reference-only bundle-owned NAT pseudocode: `references/examples/manage-firewall.pseudocode.sh`
- Starter manifest: `assets/templates/bundle.yaml`
