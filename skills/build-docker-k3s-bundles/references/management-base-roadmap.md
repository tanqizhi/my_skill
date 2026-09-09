# Python Management Base Direction

## Established Decisions

- Business logic remains Python for readability. `manage.sh` is only a launcher.
- The skill includes manager source, a portable release and a pinned offline runtime input under `assets/management-base/`. Read `portable-management.md` for the maintained interface, build commands and actual acceptance evidence.
- The Linux x86_64 artifact includes a fully static musl CPython interpreter, standard library, curses and terminfo. This is not a rewrite of business logic in C, and a source zipapp alone is not the portable deliverable.
- Management never installs, reinstalls, uninstalls or orchestrates bundle upgrades. The installer creates the fixed directories and atomic installation record; management refuses missing or mismatched records.
- No arguments enters the TUI; any arguments select non-interactive CLI behavior. Arrow keys, Enter, text entry and Esc remain the interaction model. Missing arguments or authorization never trigger an interactive CLI fallback.
- Both modes share operations, validation, ownership checks, confirmations, locks and recovery.

## Reuse And Customization

1. Check target architecture, layout, external interfaces and required capabilities against the existing release and its test report.
2. Prefer matching installed configuration to the contract. Do not patch source for a different project name or installation root.
3. If architecture/native dependencies differ, prepare and test another pinned runtime; do not rewrite Python logic just for that.
4. If capability or adapter support is missing, copy the pinned source into a separate project workspace. Make scoped changes, retain safety checks, rebuild and run common plus project-specific tests.
5. Give customized builds a distinct artifact checksum and traceable source/patch/runtime identity. Never overwrite the standard skill release as a side effect of preparing one bundle.
6. Build before delivery, never run pip/compiler/network acquisition on the managed host. The supplied runtime enables offline application rebuilding; a native CPython rebuild additionally needs upstream sources and toolchain.
7. Lack of a target test facility means unverified, not passed. Do not promise all Linux architectures, kernel versions or runtimes.

## Remaining Capability Gaps

The supplied release implements Docker Compose management including status tables, image operations, lifecycle controls, service addition, configuration validation, backups and runtime DOCKER-USER rule insertion. Refer to the portable contract for exact limits.

K3s, remote/rootless Docker adapters, generic configuration reload, external exposure CRUD, automatic generic restore and installer/upgrade orchestration are not provided by this release. Requirements elsewhere in the skill remain requirements for bundles that need those capabilities; they are not evidence of implementation. Resolve a gap explicitly instead of generating a parallel ad hoc manager.
