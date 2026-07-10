"""Normalize Nmap XML open-service evidence."""

from pathlib import Path
import xml.etree.ElementTree as ET

from ..models import Finding, ParseResult
from . import ParseFailure


def parse_nmap(path: Path) -> ParseResult:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ParseFailure(f"cannot parse Nmap XML {path}: {error}") from error

    findings: list[Finding] = []
    for host in root.findall("host"):
        hostname_node = host.find("hostnames/hostname")
        address_node = host.find("address")
        asset = (
            hostname_node.get("name")
            if hostname_node is not None and hostname_node.get("name")
            else address_node.get("addr") if address_node is not None else "unknown"
        )
        for port in host.findall("ports/port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            protocol = port.get("protocol", "unknown")
            port_id = port.get("portid", "unknown")
            service = port.find("service")
            service_name = service.get("name", "unknown") if service is not None else "unknown"
            product = service.get("product", "") if service is not None else ""
            version = service.get("version", "") if service is not None else ""
            description = " ".join(part for part in (product, version) if part)
            findings.append(Finding(
                source="nmap",
                asset=asset,
                component=f"{port_id}/{protocol}",
                title=f"Open service: {service_name}",
                severity="info",
                status="confirmed",
                confidence="high",
                identifiers=(f"service:{service_name}",),
                evidence_refs=(path.name,),
                description=description,
            ))

    return ParseResult(tuple(findings), accepted=len(findings), rejected=0)
