"""Redact and atomically persist evidence inside a bounded run directory."""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


class EvidencePathError(ValueError):
    """Raised when an evidence path escapes the run directory."""


@dataclass(frozen=True)
class EvidenceRecord:
    path: str
    sha256: str
    size: int


_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_AUTHORIZATION = re.compile(r"(?im)^(authorization\s*:)\s*.*$")
_COOKIE = re.compile(r"(?im)^(set-cookie|cookie)\s*:\s*.*$")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|api[_-]?key|secret)\s*([=:])\s*[^\s,;]+"
)
_SUDO_PROMPT = re.compile(r"(?im)^\[sudo\]\s+password\s+for\s+[^:]+:.*$")


def redact_text(value: str) -> str:
    redacted = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    redacted = _AUTHORIZATION.sub(r"\1 [REDACTED]", redacted)
    redacted = _COOKIE.sub(r"\1: [REDACTED]", redacted)
    redacted = _BEARER.sub("Bearer [REDACTED]", redacted)
    redacted = _ASSIGNMENT.sub(r"\1\2[REDACTED]", redacted)
    return _SUDO_PROMPT.sub("[sudo] password prompt [REDACTED]", redacted)


class EvidenceStore:
    def __init__(self, run_directory: Path):
        self.run_directory = run_directory.resolve()
        self.evidence_directory = self.run_directory / "evidence"
        self.evidence_directory.mkdir(parents=True, exist_ok=True)
        self._records: list[EvidenceRecord] = []

    def _target(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise EvidencePathError(f"evidence path escapes run directory: {relative_path}")
        target = (self.evidence_directory / relative).resolve()
        try:
            target.relative_to(self.evidence_directory.resolve())
        except ValueError as error:
            raise EvidencePathError(
                f"evidence path escapes run directory: {relative_path}"
            ) from error
        return target

    @staticmethod
    def _atomic_write(target: Path, payload: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, target)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def write_text(self, relative_path: str, content: str) -> EvidenceRecord:
        target = self._target(relative_path)
        payload = redact_text(content).encode("utf-8")
        self._atomic_write(target, payload)
        record = EvidenceRecord(
            path=target.relative_to(self.evidence_directory).as_posix(),
            sha256=hashlib.sha256(payload).hexdigest(),
            size=len(payload),
        )
        self._records.append(record)
        return record

    def write_manifest(self) -> Path:
        target = self.evidence_directory / "manifest.json"
        payload = json.dumps(
            {
                "schema_version": 1,
                "files": [asdict(record) for record in sorted(self._records, key=lambda item: item.path)],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        self._atomic_write(target, payload)
        return target
