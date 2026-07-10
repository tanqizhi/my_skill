import json

from security_assessor.correlate import correlate_findings
from security_assessor.evidence import EvidenceStore
from security_assessor.models import Finding
from security_assessor.report import RunSummary, render_reports


def test_render_reports_creates_safe_technical_executive_and_json_outputs(tmp_path):
    evidence = EvidenceStore(tmp_path)
    evidence.write_text("scan/nuclei.jsonl", '{"template-id":"example"}\n')
    evidence.write_manifest()
    findings = correlate_findings((
        Finding(
            source="nuclei",
            asset="app.example.test",
            component="CVE-2024-1234",
            title="<script>alert(1)</script> Web vulnerability",
            severity="high",
            status="probable",
            confidence="medium",
            identifiers=("CVE-2024-1234",),
            evidence_refs=("scan/nuclei.jsonl",),
            impact="May expose application data",
            remediation="Apply the vendor update",
            retest_method="Run the exact template again",
            baseline_mappings=("CIS-L1:2.2",),
        ),
    ))
    summary = RunSummary(
        mode="external",
        generated_at="2026-07-11T00:00:00+08:00",
        title="授权业务安全评估",
        findings=findings,
        completed_checks=8,
        total_checks=10,
        coverage_gaps=("SSH 未纳入本次范围",),
    )

    outputs = render_reports(tmp_path, summary)

    assert {path.name for path in outputs} == {
        "report.md", "executive-report.html", "findings.json"
    }
    html = (tmp_path / "executive-report.html").read_text()
    markdown = (tmp_path / "report.md").read_text()
    payload = json.loads((tmp_path / "findings.json").read_text())
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "https://" not in html and "http://" not in html
    assert payload["assessment"]["posture_score"] == 95
    assert payload["coverage"]["completed"] == 8
    assert "覆盖缺口" in markdown
    assert "不能视为安全" in markdown
