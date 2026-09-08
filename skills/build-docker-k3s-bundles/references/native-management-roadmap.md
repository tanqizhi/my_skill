# Native Management Base Roadmap

Recorded: 2026-09-08. Status: design direction only; implementation language, interface library, supported platform matrix, source location within the skill, and artifact layout are not yet selected. No usable native binary or successful compatibility test is implied by this document.

Read before designing management tooling or preparing a future bundle that might reuse the management base. Preserve these decisions rather than rediscovering them or generating a new unrelated implementation.

## Agreed Direction

- Build a reusable native management program statically linked with musl, rather than a new Bash management implementation per project. musl is the C library/build target, not a programming language.
- The earlier Bash plus dialog proposal is superseded as the preferred direction for this new base. Language and terminal UI library remain open; do not infer that C, dialog, or a particular framework has been selected.
- Focus this project on management tooling. Installation bundles establish the fixed installed directory contract; the management program reads and modifies explicitly registered files there. Do not expand the management base into an installer or image acquisition system without an explicit decision.
- Keep the source, build instructions, tests, and verified compiled artifacts with this skill once implemented. Their exact directories and release process must be decided before adding them; do not create empty implementations or placeholder binaries now.
- Both interaction modes share the same operations, validation, ownership checks, locking, logging, and recovery behavior.

## Invocation Contract

- No arguments: enter the interactive terminal interface.
- Any arguments: remain non-interactive, including help and invalid commands. Missing required inputs or authorization result in a useful error and nonzero exit, never a prompt or fallback into a menu.
- Interactive navigation should support arrow keys, Enter, text editing, and cancellation/back navigation. Precise key mappings, terminal resizing, Chinese display, and terminal restoration require design and testing.
- With no arguments and no usable interactive terminal, explain how to use commands and exit rather than waiting for input.
- Non-interactive impactful operations require explicit authorization appropriate to their scope. A generic confirmation flag must not silently authorize data deletion or public exposure.
- Executable name and migration of the existing `manage.sh` interface remain undecided.

## Planned Bundle Preparation Flow

1. Read the required capabilities, deployment target, fixed-directory contract version, CPU architecture, instruction baseline, kernel baseline, and external runtime versions.
2. Inspect existing artifacts and their checksums, source revisions, build/dependency records, supported capabilities, and actual test evidence.
3. Reuse a compatible verified artifact and run project-specific configuration and integration checks.
4. If no artifact qualifies, classify why before making changes:
   - Project parameters differ: change declared configuration, not common code.
   - Architecture or build baseline differs: rebuild the same pinned source.
   - A project capability is missing: add an isolated project module or patch.
   - Common behavior is defective: fix the common implementation and run shared regression tests.
   - Target test facilities are missing: record compatibility as unverified, not incompatible or passed.
5. Clone or copy a pinned source revision into a separate build workspace. Apply scoped changes there; do not overwrite the skill's standard source or binaries as a side effect of producing one project bundle.
6. Build during package preparation, not on the installation target. Record source revision, project patches, compiler/toolchain and dependency versions, target, checksum, and tests for the resulting artifact.
7. Package only artifacts that meet the agreed acceptance policy. Report unexecuted tests and unresolved compatibility instead of claiming universal Linux support. Require an explicit decision before delivering an unverified target build.

Remote acquisition, host changes, credentials, and destructive tests remain subject to the existing authorization rules. Do not bypass them to rebuild an artifact.

## Customization And Compatibility Boundaries

- Keep command dispatch, terminal interaction, configuration I/O, logging, locks, confirmation, backup, and recovery in a stable shared core.
- Prefer project configuration, then explicit project modules. Avoid unrestricted per-project rewrites of the shared core.
- Give customized builds distinct identities with traceable patches. Do not automatically promote a project build to the common release; promotion requires explicit review and common regression tests.
- Source and binaries must remain traceable to the same revision. Updating source does not make previously compiled artifacts current.
- Static linking is not a promise of all architectures or all kernels. Validate native artifact dependencies and any required runtime data, including terminal capability data if applicable.
- Docker, Compose, K3s, and any invoked external utilities remain separately declared and verified dependencies. Self-contained management does not imply a self-contained container runtime.
- Offline builds require a separately prepared toolchain and dependency inventory. Keeping source in the skill alone does not guarantee offline rebuilding.

## Pending Decisions And Transition

Next define the capability list and project configuration interface, then choose language/UI dependencies and supported systems. Validate a small prototype for startup, both modes, Chinese input/display, terminal recovery, and target compatibility before implementing the full management feature set.

The installed-layout contract remains active. Existing Shell/Python, `manage.sh`, registry, and module rules elsewhere in this skill describe the current bundle interface, not the architecture of the proposed native implementation. This roadmap does not silently replace those rules or authorize generating a new Shell fallback. If a bundle needs management before the native base is available, disclose that gap and confirm the interim approach.

When the native design is approved and implemented, update the entrypoint, installation-layout version if needed, module contract, manifest/template, manuals, and validation rules together. Preserve existing operation-safety requirements regardless of language. Do not claim native-management support until real source, artifacts, and tests exist.
