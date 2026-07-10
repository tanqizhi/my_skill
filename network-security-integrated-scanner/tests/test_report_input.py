from pathlib import Path
import pytest

from security_assessor.command_plan import ToolPaths, build_external_plan
from security_assessor.report_input import (
    ReportInputError,
    build_report_request,
    load_report_findings,
)


FIXTURES = Path(__file__).parent / "fixtures"
TOOLS = ToolPaths(
    nmap="/usr/local/bin/nmap",
    nuclei="/usr/local/bin/nuclei",
    chaitin_xray="/opt/security/xray_darwin_arm64",
)


def test_canonical_report_rows_keep_provenance_and_only_plan_exact_verification():
    rows = load_report_findings(FIXTURES / "report-findings.json")
    request = build_report_request(rows, allow_safe_poc=False)
    plan = build_external_plan(
        request,
        open_services=(("app.example.test", 443, "https"),),
        enable_xray=True,
        tools=TOOLS,
        output_dir="/tmp/assessment-run",
    )

    assert rows[0].source_ref == "page 7"
    assert rows[0].vulnerability_id == "CVE-2024-1234"
    assert request.report_directed
    assert request.external_targets == ("https://app.example.test/admin?id=1",)
    assert not any(command.tool == "nmap" for command in plan)
    assert not any(command.tool == "chaitin-xray" for command in plan)
    nuclei = next(command for command in plan if command.tool == "nuclei")
    assert nuclei.argv[nuclei.argv.index("-t") + 1] == "CVE-2024-1234"
    assert "--basic-crawler" not in [arg for command in plan for arg in command.argv]


def test_canonical_csv_is_supported_and_ambiguous_rows_are_rejected(tmp_path):
    csv_path = tmp_path / "report.csv"
    csv_path.write_text(
        "report_id,title,target,port,protocol,url,vulnerability_id,source_ref,verification_method\n"
        "V-2,TLS issue,app.example.test,443,https,https://app.example.test/,CVE-2025-0001,row 2,nuclei:CVE-2025-0001\n",
        encoding="utf-8",
    )
    assert load_report_findings(csv_path)[0].source_ref == "row 2"

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(
        '{"schema_version":1,"findings":[{"report_id":"V-3","title":"Unknown","target":"app.example.test"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ReportInputError, match="source_ref"):
        load_report_findings(bad_path)
