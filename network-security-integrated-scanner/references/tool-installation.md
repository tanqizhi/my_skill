# Assessment-machine tool installation

Install tools only on the assessment machine, never on the target. Present the exact action through Codex and wait for normal host approval.

## Preflight

1. Detect operating system, CPU architecture, package managers, and absolute executable paths.
2. Record versions and paths in run metadata.
3. For `xray`, combine version output with `webscan --help`. Reject XTLS/Xray-core signatures such as “anti-censorship”, VMess, VLESS, or XTLS.

## Nmap and Nuclei

- macOS with Homebrew: propose `brew install nmap nuclei`.
- Debian/Ubuntu: propose `apt-get update` and `apt-get install nmap`; install Nuclei from an official ProjectDiscovery release or a current Go toolchain.
- RHEL/Rocky/Alma: propose the supported `dnf`/`yum` Nmap package; install Nuclei from an official ProjectDiscovery release or a current Go toolchain.
- Verify `nmap --version` and `nuclei -version` before use.

Do not use `curl | sh`, unverified mirrors, or an unauthenticated binary. Keep Nuclei cloud upload disabled. Update templates explicitly and record their version.

## Chaitin Xray

1. Show the Chaitin Xray license and require acceptance on first download.
2. Download the official binary matching `darwin_amd64`, `darwin_arm64`, `linux_amd64`, or `linux_arm64`.
3. Download official `sha256.txt` and verify the binary before making it executable.
4. Resolve and record the absolute path. Do not install it globally under the ambiguous name `xray` unless identity validation remains possible.
5. Verify that the binary exposes the `webscan` command.

Xray is optional. If the license is declined, the architecture is unsupported, or validation fails, continue with Nmap/Nuclei and record reduced Web coverage.

## Network proxy

When a foreign download is inaccessible, use `http://127.0.0.1:7890` as HTTP and HTTPS proxy. Preserve TLS and checksum verification; never bypass certificate validation merely to complete installation.
