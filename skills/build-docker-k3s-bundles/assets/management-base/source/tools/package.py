"""Build a source zipapp, not a native executable or a bundled interpreter."""

import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build_application(root: Path, artifact: Path) -> None:
    """Fixed metadata and ordering make identical sources reproducible."""
    artifact.parent.mkdir(parents=True, exist_ok=True)
    entries = {"__main__.py": b"from managebase.cli import entrypoint\nentrypoint()\n"}
    for source, prefix in (
        (root / "managebase", "managebase"),
        (root / "vendor/ruamel", "ruamel"),
        (root / "vendor/ruamel.yaml-0.18.6.dist-info", "ruamel.yaml-0.18.6.dist-info"),
    ):
        for path in sorted(source.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                entries[f"{prefix}/{path.relative_to(source).as_posix()}"] = path.read_bytes()
    with artifact.open("wb") as stream:
        stream.write(b"#!/usr/bin/env python3\n")
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, (2024, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
    artifact.chmod(0o755)


def main() -> None:
    output = ROOT / "outputs"
    artifact = output / "manage.pyz"
    build_application(ROOT, artifact)
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (output / "manage.pyz.sha256").write_text(
        f"{checksum}  manage.pyz\n", encoding="utf-8")
    print(f"Created {artifact} (requires Python 3.10+; curses for interactive mode)")


if __name__ == "__main__":
    main()
