"""Reproducible manager release builder; no pip, compiler or network at rebuild time."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from package import ROOT, build_application

UPSTREAM_SHA256 = "2b89d2b76515cd89007f6b7c7ef7a5b0815aa2ff871a1572324374b1a063f52a"
UPSTREAM_NAME = "cpython-3.12.14+20260901-x86_64-unknown-linux-musl-lto+static-full.tar.zst"
MUSL_SHA256 = "a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4"
PLATFORM = "linux-x86_64-static"
LAUNCHER = """#!/bin/sh
set -eu
# Resolve using shell builtins only. Symlink entrypoints are intentionally unsupported.
entry=$0
case "$entry" in
  */*) ;;
  *) entry=$(command -v "$entry") ;;
esac
case "$entry" in */*) ;; *) entry="./$entry" ;; esac
if [ -L "$entry" ]; then
  printf '%s\\n' 'Use the real installed manage.sh path, not a symbolic link.' >&2
  exit 2
fi
root=$(CDPATH= cd -P -- "${entry%/*}" && pwd -P)
TERMINFO="$root/runtime/python/share/terminfo"
TERMINFO_DIRS="$TERMINFO"
LC_ALL=C.UTF-8
export TERMINFO TERMINFO_DIRS LC_ALL
exec "$root/runtime/python/bin/python3.12" -I -B -X utf8 "$root/manage.pyz" "$@"
"""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def tree_checksums(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): digest(p) for p in files(root)}


def archive_tree(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                                mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as archive:
            for path in files(root):
                name = path.relative_to(root).as_posix()
                info = tarfile.TarInfo(name)
                info.size = path.stat().st_size
                info.mode = 0o755 if name in ("manage.sh", "manage.pyz",
                                            "runtime/python/bin/python3.12") else 0o644
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
    output.with_name(output.name + ".sha256").write_text(
        f"{digest(output)}  {output.name}\n", encoding="utf-8")


def extract_runtime(archive_path: Path, destination: Path, expected: str) -> None:
    if digest(archive_path) != expected:
        raise ValueError("Runtime input checksum mismatch")
    with tarfile.open(archive_path, "r:gz") as archive:
        seen = set()
        for member in archive:
            parts = member.name.split("/")
            if (not member.isfile() or parts[:2] != ["runtime", "python"]
                    or any(p in ("", ".", "..") for p in parts) or member.name in seen):
                raise ValueError(f"Unexpected runtime archive member: {member.name}")
            seen.add(member.name)
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            target.chmod(0o755 if member.name.endswith("/bin/python3.12") else 0o644)


def curate(args: argparse.Namespace) -> None:
    if digest(args.upstream_archive) != UPSTREAM_SHA256:
        raise ValueError("Upstream archive checksum mismatch")
    if digest(args.musl_archive) != MUSL_SHA256:
        raise ValueError("musl source checksum mismatch")
    # Extract the verified archive ourselves, never trust an unrelated unpacked directory.
    with tempfile.TemporaryDirectory(prefix="manager-runtime-") as temp:
        base = Path(temp)
        subprocess.run(["tar", "--use-compress-program=" + args.zstd, "-xf",
                        str(args.upstream_archive.resolve()), "-C", str(base)], check=True)
        upstream = base / "python"
        stage = base / "curated"
        runtime = stage / "runtime/python"
        (runtime / "bin").mkdir(parents=True)
        shutil.copy2(upstream / "install/bin/python3.12", runtime / "bin/python3.12")
        subprocess.run(["strip", "--strip-debug", str(runtime / "bin/python3.12")], check=True)
        elf = subprocess.check_output(["readelf", "-l", str(runtime / "bin/python3.12")])
        dynamic = subprocess.check_output(["readelf", "-d", str(runtime / "bin/python3.12")])
        if b"INTERP" in elf or b"NEEDED" in dynamic:
            raise ValueError("Runtime is not fully static")
        shutil.copytree(upstream / "install/lib/python3.12", runtime / "lib/python3.12",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "site-packages",
                                                     "test", "tests", "ensurepip", "idlelib",
                                                     "tkinter", "config-3.12-*"))
        shutil.copytree(upstream / "install/share/terminfo", runtime / "share/terminfo",
                        symlinks=False)
        shutil.copytree(upstream / "licenses", runtime / "licenses")
        shutil.copy2(upstream / "PYTHON.json", runtime / "upstream-PYTHON.json")
        shutil.copytree(args.notices, runtime / "provenance")
        with tarfile.open(args.musl_archive, "r:gz") as musl:
            with musl.extractfile("musl-1.2.5/COPYRIGHT") as stream:
                (runtime / "licenses/LICENSE.musl.txt").write_bytes(stream.read())
        write_json(runtime / "provenance/runtime.json", {
            "platform": PLATFORM, "python": "3.12.14", "musl": "1.2.5",
            "upstream_archive": UPSTREAM_NAME, "upstream_sha256": UPSTREAM_SHA256,
            "build": "20260901, baseline x86_64, lto+static",
            "curation": "strip-debug; no pip, tests, tkinter, idle, build objects; all terminfo",
            "native_extensions": "builtin only; dynamically loaded .so unsupported",
        })
        archive_tree(stage, args.output)


def build(args: argparse.Namespace) -> None:
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix="manager-release-") as temp:
        stage = Path(temp)
        extract_runtime(args.runtime, stage, args.runtime_sha256)
        build_application(source, stage / "manage.pyz")
        (stage / "manage.sh").write_text(LAUNCHER, encoding="utf-8")
        (stage / "manage.sh").chmod(0o755)
        doctor = json.loads(subprocess.check_output(
            [str(stage / "manage.sh"), "doctor", "--json"], timeout=30,
            env={"PATH": "/usr/bin:/bin", "TERM": "xterm-256color"}))["data"]
        source_manifest = {}
        for prefix in ("managebase", "vendor", "tools", "tests"):
            for path in files(source / prefix):
                if "__pycache__" not in path.parts and path.suffix != ".pyc":
                    source_manifest[path.relative_to(source).as_posix()] = digest(path)
        for name in ("manage.py", "Makefile"):
            if (source / name).is_file():
                source_manifest[name] = digest(source / name)
        write_json(stage / "management/release.json", {
            "format": 1, "kind": "management-only", "platform": PLATFORM,
            "release_name": args.release_name, "application_version": doctor["version"],
            "capabilities": doctor["capabilities"],
            "layout_version": 1, "runtime_sha256": args.runtime_sha256,
            "application_sha256": digest(stage / "manage.pyz"),
            "source_files": source_manifest,
            "external_interfaces": ["POSIX /bin/sh (launcher only)",
                                    "local Docker CLI and Compose v2",
                                    "unix:///var/run/docker.sock",
                                    "host iptables/ip6tables for firewall operations"],
            "unsupported": ["K3s", "ARM64 in this artifact", "dynamic Python .so extensions",
                            "generic reload", "exposure CRUD", "generic automatic restore",
                            "installation/uninstallation/upgrade orchestration"],
        })
        checksums = tree_checksums(stage)
        (stage / "management/checksums.txt").write_text(
            "".join(f"{sha}  {name}\n" for name, sha in checksums.items()), encoding="utf-8")
        archive_tree(stage, args.output)
    print(f"{digest(args.output)}  {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    curate_parser = commands.add_parser("curate")
    curate_parser.add_argument("--upstream-archive", type=Path, required=True)
    curate_parser.add_argument("--musl-archive", type=Path, required=True)
    curate_parser.add_argument("--notices", type=Path, required=True)
    curate_parser.add_argument("--zstd", default="zstd")
    curate_parser.add_argument("--output", type=Path, required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--source", type=Path, default=ROOT)
    build_parser.add_argument("--runtime", type=Path, required=True)
    build_parser.add_argument("--runtime-sha256", required=True)
    build_parser.add_argument("--release-name", default="managebase")
    build_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    (curate if args.command == "curate" else build)(args)


if __name__ == "__main__":
    main()
