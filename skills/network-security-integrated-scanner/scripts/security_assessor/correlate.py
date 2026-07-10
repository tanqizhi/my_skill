"""Deterministically deduplicate and link external/internal findings."""

from dataclasses import replace
import hashlib

from .models import Finding


_SEVERITY = {"unknown": 0, "info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
_STATUS = {"not-assessable": 0, "not-reproduced": 1, "probable": 2, "confirmed": 3}
_CONFIDENCE = {"low": 0, "medium": 1, "high": 2}


def _strong_identifier(finding: Finding) -> str | None:
    strong = sorted(
        identifier.upper()
        for identifier in finding.identifiers
        if identifier.upper().startswith(("CVE-", "GHSA-"))
    )
    return strong[0] if strong else None


def _dedupe_key(finding: Finding) -> str:
    asset = finding.asset.strip().lower()
    strong = _strong_identifier(finding)
    if strong:
        return f"strong|{asset}|{strong}"
    return (
        f"exact|{asset}|{finding.component.strip().lower()}|"
        f"{finding.title.strip().lower()}"
    )


def _finding_id(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"NSIS-{digest}"


def _best(values: list[str], ranking: dict[str, int], fallback: str) -> str:
    return max(values, key=lambda value: ranking.get(value, -1), default=fallback)


def _merge_group(key: str, group: list[Finding]) -> Finding:
    ordered = sorted(group, key=lambda item: (item.source, item.component, item.title))
    sources = sorted({source for item in ordered for source in item.source.split("+")})
    identifiers = tuple(sorted({identifier for item in ordered for identifier in item.identifiers}))
    evidence = tuple(sorted({reference for item in ordered for reference in item.evidence_refs}))
    strong = next((_strong_identifier(item) for item in ordered if _strong_identifier(item)), None)
    components = sorted({item.component for item in ordered})
    descriptions = sorted({item.description for item in ordered if item.description})
    return replace(
        ordered[0],
        source="+".join(sources),
        component=strong or components[0],
        severity=_best([item.severity for item in ordered], _SEVERITY, "unknown"),
        status=_best([item.status for item in ordered], _STATUS, "not-assessable"),
        confidence=_best([item.confidence for item in ordered], _CONFIDENCE, "low"),
        identifiers=identifiers,
        evidence_refs=evidence,
        description="\n".join(descriptions),
        finding_id=_finding_id(key),
        exposure_conditions=tuple(sorted({value for item in ordered for value in item.exposure_conditions})),
        baseline_mappings=tuple(sorted({value for item in ordered for value in item.baseline_mappings})),
        related_finding_ids=(),
    )


def _is_external(finding: Finding) -> bool:
    return bool(set(finding.source.split("+")).intersection({"nmap", "nuclei", "xray", "external"}))


def _is_internal(finding: Finding) -> bool:
    return bool(set(finding.source.split("+")).intersection({"ssh", "internal", "forensics"}))


def correlate_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(_dedupe_key(finding), []).append(finding)
    merged = [_merge_group(key, group) for key, group in sorted(grouped.items())]

    related: dict[str, set[str]] = {finding.finding_id: set() for finding in merged}
    for index, left in enumerate(merged):
        for right in merged[index + 1 :]:
            same_asset = left.asset.strip().lower() == right.asset.strip().lower()
            same_component = left.component.strip().lower() == right.component.strip().lower()
            crosses_boundary = (_is_external(left) and _is_internal(right)) or (
                _is_internal(left) and _is_external(right)
            )
            if same_asset and same_component and crosses_boundary:
                related[left.finding_id].add(right.finding_id)
                related[right.finding_id].add(left.finding_id)

    return tuple(
        replace(finding, related_finding_ids=tuple(sorted(related[finding.finding_id])))
        for finding in sorted(merged, key=lambda item: item.finding_id)
    )
