# Python Management Base Roadmap

Updated: 2026-09-08. The user selected Python for readability and maintainability, superseding the native C/musl implementation direction. A separate development project is building a read-only Python foundation; it is not yet a supported skill release. Offline interpreter packaging, supported platform matrix, source location within the skill, and release artifact layout remain undecided.

Read before designing management tooling or preparing a future bundle that might reuse the management base. Preserve these decisions rather than rediscovering them or generating a new unrelated implementation.

## Agreed Direction

- Build a reusable Python management program, rather than a new implementation per project. Keep ordinary modules readable to an operator with limited software engineering experience.
- Earlier Bash/dialog and native C/musl proposals are superseded. The initial development implementation uses Python standard-library curses for interaction, lazily loaded so command mode does not depend on the terminal UI module. Do not promise a musl static executable or switch back to C without a new user decision.
- Focus this project on management tooling. Installation bundles establish the fixed installed directory contract; the management program reads and modifies explicitly registered files there. Do not expand the management base into an installer or image acquisition system without an explicit decision.
- Keep source, packaging instructions, tests, and verified release artifacts with this skill after acceptance. A Python zipapp contains application code, not an interpreter; any offline interpreter and native extension dependencies must be separately supplied and verified.
- Both interaction modes share the same operations, validation, ownership checks, locking, logging, and recovery behavior.

## Invocation Contract

- No arguments: enter the interactive terminal interface.
- Any arguments: remain non-interactive, including help and invalid commands. Missing required inputs or authorization result in a useful error and nonzero exit, never a prompt or fallback into a menu.
- Interactive navigation should support arrow keys, Enter, text editing, and cancellation/back navigation. Precise key mappings, terminal resizing, Chinese display, and terminal restoration require design and testing.
- With no arguments and no usable interactive terminal, explain how to use commands and exit rather than waiting for input.
- Non-interactive impactful operations require explicit authorization appropriate to their scope. A generic confirmation flag must not silently authorize data deletion or public exposure.
- Executable name and migration of the existing `manage.sh` interface remain undecided.

## Planned Bundle Preparation Flow

1. Read required capabilities, deployment target, directory contract version, Python version/modules, interpreter architecture and OS/library baseline, terminal requirements, and external runtime versions.
2. Inspect existing artifacts and their checksums, source revisions, build/dependency records, supported capabilities, and actual test evidence.
3. Reuse a compatible verified artifact and run project-specific configuration and integration checks.
4. If no artifact qualifies, classify why before making changes:
   - Project parameters differ: change declared configuration, not common code.
   - Interpreter architecture, native dependencies, or OS baseline differs: select or rebuild a compatible pinned runtime; do not rewrite Python business logic for that reason.
   - A project capability is missing: add an isolated project module or patch.
   - Common behavior is defective: fix the common implementation and run shared regression tests.
   - Target test facilities are missing: record compatibility as unverified, not incompatible or passed.
5. Clone or copy a pinned source revision into a separate build workspace. Apply scoped changes there; do not overwrite the skill's standard source or binaries as a side effect of producing one project bundle.
6. Package during bundle preparation, not on the installation target. Record source revision, project patches, interpreter and dependency versions, any compiler/toolchain used for native dependencies, target, checksum, and test evidence. Never implicitly install dependencies online during management.
7. Package only artifacts that meet the agreed acceptance policy. Report unexecuted tests and unresolved compatibility instead of claiming universal Linux support. Require an explicit decision before delivering an unverified target build.

Remote acquisition, host changes, credentials, and destructive tests remain subject to the existing authorization rules. Do not bypass them to rebuild an artifact.

## Customization And Compatibility Boundaries

- Keep command dispatch, terminal interaction, configuration I/O, logging, locks, confirmation, backup, and recovery in a stable shared core.
- Prefer project configuration, then explicit project modules. Avoid unrestricted per-project rewrites of the shared core.
- Give customized builds distinct identities with traceable patches. Do not automatically promote a project build to the common release; promotion requires explicit review and common regression tests.
- Source and packaged application code must trace to the same revision; record the interpreter/runtime identity separately. Updating source does not make previously packaged artifacts current.
- Python source portability is not proof of interpreter compatibility. Verify Python version, curses/native libraries and any required terminal data. musl may be evaluated for a future interpreter build, but is not a current deliverable promise.
- Docker, Compose, K3s, and any invoked external utilities remain separately declared and verified dependencies. Self-contained management does not imply a self-contained container runtime.
- Offline builds require a separately prepared toolchain and dependency inventory. Keeping source in the skill alone does not guarantee offline rebuilding.

## Pending Decisions And Transition

The initial foundation is limited to tool diagnostics, fixed-path validation, Compose status and configuration validation, and dry-run previews. Continue validating both modes, Chinese input/display, terminal recovery, and actual target compatibility before adding write operations. Native static artifacts, K3s, legacy migration, configuration writes, restart, upgrade, and rollback are not implemented capabilities of this foundation.

The installed-layout contract remains active. Existing Shell/Python, `manage.sh`, registry, and module rules elsewhere in this skill describe the current bundle interface, not a requirement to implement the new base in Shell. This roadmap does not silently replace those rules or authorize generating a new Shell fallback. If a bundle needs management before the Python base is accepted, disclose that gap and confirm the interim approach.

When the Python base is accepted for release, update the entrypoint, installation-layout version if needed, module contract, manifest/template, manuals, and validation rules together. Preserve all existing operation-safety requirements. Do not promote a development source zipapp as a verified standalone offline runtime.
