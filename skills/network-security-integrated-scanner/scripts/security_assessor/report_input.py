"""Canonical import boundary for third-party vulnerability reports."""

import csv
from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import urlsplit

from .models import AssessmentMode, AssessmentRequest, Coverage, VerificationTarget


class ReportInputError(ValueError):
    """Raised when a report row is ambiguous or lacks provenance."""


@dataclass(frozen=True)
class ReportFinding:
    report_id: str
    title: str
    target: str
    port: int | None
    protocol: str
    url: str
    vulnerability_id: str
    source_ref: str
    verification_method: str = ""


def _row_to_finding(row: dict[str, object], *, row_number: int) -> ReportFinding:
    required = ("report_id", "title", "target", "source_ref")
    missing = [field for field in required if not str(row.get(field, "")).strip()]
    if missing:
        raise ReportInputError(f"row {row_number} missing required fields: {', '.join(missing)}")

    port_value = row.get("port")
    try:
        port = int(port_value) if port_value not in (None, "") else None
    except (TypeError, ValueError) as error:
        raise ReportInputError(f"row {row_number} has invalid port") from error
    if port is not None and not 1 <= port <= 65535:
        raise ReportInputError(f"row {row_number} port is outside 1..65535")

    target = str(row["target"]).strip().lower()
    protocol = str(row.get("protocol", "")).strip().lower()
    url = str(row.get("url", "")).strip()
    if not url:
        if not protocol or port is None:
            raise ReportInputError(
                f"row {row_number} requires exact url or protocol plus port"
            )
        url = f"{protocol}://{target}:{port}"
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ReportInputError(f"row {row_number} has unsupported URL")
    if parsed.username or parsed.password:
        raise ReportInputError(f"row {row_number} URL must not contain credentials")
    if parsed.hostname.lower() != target:
        raise ReportInputError(f"row {row_number} URL host does not match target")

    return ReportFinding(
        report_id=str(row["report_id"]).strip(),
        title=str(row["title"]).strip(),
        target=target,
        port=port,
        protocol=protocol or parsed.scheme,
        url=url,
        vulnerability_id=str(row.get("vulnerability_id", "")).strip().upper(),
        source_ref=str(row["source_ref"]).strip(),
        verification_method=str(row.get("verification_method", "")).strip(),
    )


def load_report_findings(path: Path) -> tuple[ReportFinding, ...]:
    try:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                raise ReportInputError("JSON report requires schema_version 1")
            rows = payload.get("findings")
            if not isinstance(rows, list):
                raise ReportInputError("JSON report findings must be an array")
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        else:
            raise ReportInputError("only canonical JSON or CSV can be loaded directly")
    except (OSError, json.JSONDecodeError) as error:
        raise ReportInputError(f"cannot read report input {path}: {error}") from error

    findings = tuple(
        _row_to_finding(row, row_number=index)
        for index, row in enumerate(rows, start=1)
        if isinstance(row, dict)
    )
    if len(findings) != len(rows):
        raise ReportInputError("every report row must be an object")
    if not findings:
        raise ReportInputError("report contains no findings")
    return findings


def build_report_request(
    findings: tuple[ReportFinding, ...], *, allow_safe_poc: bool
) -> AssessmentRequest:
    targets = tuple(dict.fromkeys(finding.url for finding in findings))
    ports = tuple(sorted({finding.port for finding in findings if finding.port is not None}))
    verifications: list[VerificationTarget] = []
    for finding in findings:
        tool, separator, selector = finding.verification_method.partition(":")
        if separator and tool in {"nuclei", "xray"} and selector:
            verifications.append(VerificationTarget(finding.url, tool, selector))
    return AssessmentRequest(
        mode=AssessmentMode.EXTERNAL,
        coverage=Coverage.TARGETED,
        external_targets=targets,
        external_ports=ports,
        report_directed=True,
        allow_safe_poc=allow_safe_poc,
        verifications=tuple(verifications),
    )
