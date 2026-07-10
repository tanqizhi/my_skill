#!/usr/bin/env python3
"""Validate a generated assessment run without network access."""

import argparse
import hashlib
import json
from pathlib import Path
import re


_FINDING_ID = re.compile(r"^NSIS-[A-F0-9]{12}$")
_EXTERNAL_HTML = re.compile(
    r"<(?:script|link|img|iframe)\b[^>]*(?:src|href)\s*=\s*['\"]https?://",
    re.IGNORECASE,
)
_SECRET_MARKERS = (
    re.compile(r"-----BEGIN [^-\r\n]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"authorization\s*:\s*bearer\s+(?!\[REDACTED\])", re.IGNORECASE),
    re.compile(r"\bpassword\s*=\s*(?!\[REDACTED\])\S+", re.IGNORECASE),
)
_STATUSES = {"confirmed", "probable", "not-reproduced", "not-assessable"}
_SEVERITIES = {"critical", "high", "medium", "low", "info", "unknown"}


def _safe_evidence_path(evidence_directory: Path, relative: str) -> Path | None:
    candidate_path = Path(relative)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        return None
    candidate = (evidence_directory / candidate_path).resolve()
    try:
        candidate.relative_to(evidence_directory.resolve())
    except ValueError:
        return None
    return candidate


def validate_run(run_directory: Path) -> tuple[str, ...]:
    run_directory = run_directory.resolve()
    errors: list[str] = []
    required = (
        run_directory / "report.md",
        run_directory / "executive-report.html",
        run_directory / "findings.json",
        run_directory / "evidence" / "manifest.json",
    )
    for path in required:
        if not path.is_file():
            errors.append(f"missing required output: {path.name}")
    if errors:
        return tuple(errors)

    try:
        findings_payload = json.loads((run_directory / "findings.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("findings.json is not valid JSON")
        findings_payload = {}
    if findings_payload.get("schema_version") != 1:
        errors.append("findings.json schema_version must be 1")
    assessment = findings_payload.get("assessment", {})
    if assessment.get("scope_violations"):
        errors.append("run contains scope violations")
    coverage = findings_payload.get("coverage", {})
    completed = coverage.get("completed")
    total = coverage.get("total")
    if not isinstance(completed, int) or not isinstance(total, int) or not 0 <= completed <= total:
        errors.append("coverage counts are invalid")
    for index, finding in enumerate(findings_payload.get("findings", []), start=1):
        if not isinstance(finding, dict):
            errors.append(f"finding {index} is not an object")
            continue
        if not _FINDING_ID.fullmatch(str(finding.get("finding_id", ""))):
            errors.append(f"finding {index} has invalid finding_id")
        if finding.get("status") not in _STATUSES:
            errors.append(f"finding {index} has invalid status")
        if finding.get("severity") not in _SEVERITIES:
            errors.append(f"finding {index} has invalid severity")
        if not isinstance(finding.get("evidence_refs"), list):
            errors.append(f"finding {index} evidence_refs must be an array")

    html = (run_directory / "executive-report.html").read_text(encoding="utf-8")
    if _EXTERNAL_HTML.search(html):
        errors.append("executive report contains an external HTML dependency")

    evidence_directory = run_directory / "evidence"
    try:
        manifest = json.loads((evidence_directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("evidence manifest is not valid JSON")
        manifest = {}
    for record in manifest.get("files", []):
        if not isinstance(record, dict):
            errors.append("evidence manifest contains a non-object record")
            continue
        relative = str(record.get("path", ""))
        path = _safe_evidence_path(evidence_directory, relative)
        if path is None:
            errors.append("evidence manifest contains an unsafe path")
            continue
        if not path.is_file():
            errors.append(f"evidence file is missing: {relative}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record.get("sha256"):
            errors.append(f"evidence hash mismatch: {relative}")

    text_paths = [run_directory / "report.md", run_directory / "executive-report.html"]
    text_paths.extend(
        path for path in evidence_directory.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    )
    for path in text_paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in _SECRET_MARKERS):
            errors.append(f"unredacted secret marker found in {path.name}")

    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    arguments = parser.parse_args()
    errors = validate_run(arguments.run_directory)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
