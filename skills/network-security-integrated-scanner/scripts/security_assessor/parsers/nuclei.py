"""Normalize ProjectDiscovery Nuclei JSONL evidence."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from ..models import Finding, ParseResult
from . import ParseFailure


def _identifiers(record: dict[str, object]) -> tuple[str, ...]:
    template_id = str(record.get("template-id", "unknown"))
    info = record.get("info")
    classification = info.get("classification", {}) if isinstance(info, dict) else {}
    cves = classification.get("cve-id", []) if isinstance(classification, dict) else []
    if isinstance(cves, str):
        cves = [cves]
    values = [str(cve).upper() for cve in cves if cve]
    values.append(f"nuclei:{template_id}")
    return tuple(dict.fromkeys(values))


def parse_nuclei(path: Path) -> ParseResult:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ParseFailure(f"cannot read Nuclei JSONL {path}: {error}") from error

    findings: list[Finding] = []
    errors: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("record is not an object")
            info = record.get("info")
            if not isinstance(info, dict):
                raise ValueError("missing info object")
            template_id = str(record["template-id"])
            host = str(record.get("host") or record.get("matched-at") or "")
            parsed_host = urlsplit(host).hostname
            asset = parsed_host or host
            if not asset:
                raise ValueError("missing host")
            severity = str(info.get("severity", "unknown")).lower()
            title = str(info.get("name") or template_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"line {line_number}: {type(error).__name__}: {error}")
            continue

        findings.append(Finding(
            source="nuclei",
            asset=asset,
            component=template_id,
            title=title,
            severity=severity,
            status="probable",
            confidence="medium",
            identifiers=_identifiers(record),
            evidence_refs=(f"{path.name}:{line_number}",),
            description=str(record.get("matched-at", "")),
        ))

    return ParseResult(
        findings=tuple(findings),
        accepted=len(findings),
        rejected=len(errors),
        errors=tuple(errors),
    )
