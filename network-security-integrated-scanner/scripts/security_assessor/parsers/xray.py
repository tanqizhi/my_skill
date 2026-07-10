"""Normalize Chaitin Xray JSON evidence."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from ..models import Finding, ParseResult
from . import ParseFailure


def _records(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("vulnerabilities"), list):
        return payload["vulnerabilities"]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("Xray output must be an object or array")


def parse_xray(path: Path, *, exit_code: int) -> ParseResult:
    if exit_code != 0:
        raise ParseFailure(f"Xray exited with status {exit_code}; output may be incomplete")
    if not path.exists():
        return ParseResult((), accepted=0, rejected=0)
    try:
        records = _records(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ParseFailure(f"cannot parse Xray JSON {path}: {error}") from error

    findings: list[Finding] = []
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        try:
            if not isinstance(record, dict):
                raise ValueError("record is not an object")
            plugin = str(record.get("plugin") or record.get("plugin_name") or "unknown")
            target = record.get("target")
            target_url = target.get("url", "") if isinstance(target, dict) else str(target or "")
            detail = record.get("detail")
            if not target_url and isinstance(detail, dict):
                target_url = str(detail.get("addr") or "")
            asset = urlsplit(target_url).hostname or target_url
            if not asset:
                raise ValueError("missing target URL")
            cves = record.get("cve", [])
            if isinstance(cves, str):
                cves = [cves]
            identifiers = [str(cve).upper() for cve in cves if cve]
            identifiers.append(f"xray:{plugin}")
        except (TypeError, ValueError) as error:
            errors.append(f"record {index}: {type(error).__name__}: {error}")
            continue

        findings.append(Finding(
            source="xray",
            asset=asset,
            component=plugin,
            title=str(record.get("vuln_class") or record.get("title") or plugin),
            severity=str(record.get("level") or record.get("severity") or "unknown").lower(),
            status="probable",
            confidence="medium",
            identifiers=tuple(dict.fromkeys(identifiers)),
            evidence_refs=(f"{path.name}:{index}",),
            description=target_url,
        ))

    return ParseResult(
        findings=tuple(findings),
        accepted=len(findings),
        rejected=len(errors),
        errors=tuple(errors),
    )
