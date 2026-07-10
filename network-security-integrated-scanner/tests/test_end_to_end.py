import json
from pathlib import Path

from security_assessor.evidence import EvidenceStore
from security_assessor.report import RunSummary, render_reports
from validate_run import validate_run


def test_run_validator_accepts_complete_run_and_detects_tampering(tmp_path):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "complete-run.json").read_text()
    )
    evidence = EvidenceStore(tmp_path)
    evidence.write_text("checks/os-release.txt", "NAME=Test Linux\n")
    evidence.write_manifest()
    render_reports(
        tmp_path,
        RunSummary(
            mode=fixture["mode"],
            generated_at=fixture["generated_at"],
            title=fixture["title"],
            findings=(),
            completed_checks=fixture["completed_checks"],
            total_checks=fixture["total_checks"],
            coverage_gaps=tuple(fixture["coverage_gaps"]),
        ),
    )

    assert validate_run(tmp_path) == ()

    (tmp_path / "evidence" / "checks" / "os-release.txt").write_text("tampered")
    errors = validate_run(tmp_path)
    assert any("hash mismatch" in error for error in errors)

    html_path = tmp_path / "executive-report.html"
    html_path.write_text(html_path.read_text() + '<script src="https://outside.invalid/x.js"></script>')
    errors = validate_run(tmp_path)
    assert any("external HTML dependency" in error for error in errors)
