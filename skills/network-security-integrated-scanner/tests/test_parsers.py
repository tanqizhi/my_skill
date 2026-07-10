from pathlib import Path
import pytest

from security_assessor.parsers import ParseFailure
from security_assessor.parsers.nmap import parse_nmap
from security_assessor.parsers.nuclei import parse_nuclei
from security_assessor.parsers.xray import parse_xray


FIXTURES = Path(__file__).parent / "fixtures"


def test_nmap_parser_returns_only_open_services_with_provenance():
    result = parse_nmap(FIXTURES / "nmap.xml")

    assert result.accepted == 2
    assert result.rejected == 0
    assert [finding.component for finding in result.findings] == ["22/tcp", "443/tcp"]
    assert result.findings[0].asset == "app.example.test"
    assert result.findings[0].source == "nmap"
    assert result.findings[0].evidence_refs == ("nmap.xml",)


def test_nuclei_parser_keeps_valid_findings_and_reports_bad_lines():
    result = parse_nuclei(FIXTURES / "nuclei.jsonl")

    assert result.accepted == 1
    assert result.rejected == 1
    finding = result.findings[0]
    assert finding.asset == "app.example.test"
    assert finding.severity == "high"
    assert finding.identifiers == ("CVE-2024-1234", "nuclei:CVE-2024-1234")
    assert finding.evidence_refs == ("nuclei.jsonl:1",)


def test_xray_parser_normalizes_web_finding_without_copying_payload():
    result = parse_xray(FIXTURES / "xray.json", exit_code=0)

    assert result.accepted == 1
    finding = result.findings[0]
    assert finding.asset == "app.example.test"
    assert finding.component == "sqldet"
    assert finding.identifiers == ("CVE-2024-1234", "xray:sqldet")
    assert "must-not-copy-raw-payload" not in finding.description


def test_xray_missing_output_is_empty_only_after_success(tmp_path):
    missing = tmp_path / "missing.json"
    assert parse_xray(missing, exit_code=0).findings == ()
    with pytest.raises(ParseFailure):
        parse_xray(missing, exit_code=2)


def test_nuclei_and_xray_preserve_shared_cve_for_later_correlation():
    nuclei = parse_nuclei(FIXTURES / "nuclei.jsonl").findings[0]
    xray = parse_xray(FIXTURES / "xray.json", exit_code=0).findings[0]
    assert "CVE-2024-1234" in nuclei.identifiers
    assert "CVE-2024-1234" in xray.identifiers
