from security_assessor.command_plan import ToolPaths, build_external_plan
from security_assessor.models import AssessmentMode, AssessmentRequest, Coverage


TOOLS = ToolPaths(
    nmap="/usr/local/bin/nmap",
    nuclei="/usr/local/bin/nuclei",
    chaitin_xray="/opt/security/xray_darwin_arm64",
)


def external_request(**overrides):
    values = dict(
        mode=AssessmentMode.EXTERNAL,
        coverage=Coverage.TARGETED,
        external_targets=("https://app.example.test/admin",),
        internal_paths=(),
        report_directed=False,
        allow_safe_poc=False,
        external_ports=(443,),
    )
    values.update(overrides)
    return AssessmentRequest(**values)


def test_web_target_adds_nuclei_and_optional_xray_as_argv():
    plan = build_external_plan(
        external_request(),
        open_services=(("app.example.test", 443, "https"),),
        enable_xray=True,
        tools=TOOLS,
        output_dir="/tmp/assessment-run",
    )

    assert any(cmd.tool == "nuclei" and "-jsonl" in cmd.argv for cmd in plan)
    assert any(cmd.tool == "chaitin-xray" and "webscan" in cmd.argv for cmd in plan)
    assert all(cmd.shell is False for cmd in plan)
    assert all(isinstance(cmd.argv, tuple) for cmd in plan)


def test_report_validation_skips_discovery_and_xray_crawler():
    plan = build_external_plan(
        external_request(report_directed=True),
        open_services=(("app.example.test", 443, "https"),),
        enable_xray=True,
        tools=TOOLS,
        output_dir="/tmp/assessment-run",
    )

    assert not any(cmd.tool == "nmap" for cmd in plan)
    argv = [arg for cmd in plan for arg in cmd.argv]
    assert "--basic-crawler" not in argv
    assert "--url" in argv


def test_internal_only_request_produces_no_external_commands():
    request = AssessmentRequest(
        mode=AssessmentMode.INTERNAL,
        coverage=Coverage.TARGETED,
        internal_paths=("/etc/ssh",),
    )
    plan = build_external_plan(
        request,
        open_services=(("app.example.test", 443, "https"),),
        enable_xray=True,
        tools=TOOLS,
        output_dir="/tmp/assessment-run",
    )
    assert plan == ()


def test_xray_requires_an_in_scope_web_service():
    plan = build_external_plan(
        external_request(),
        open_services=(("other.example.test", 443, "https"),),
        enable_xray=True,
        tools=TOOLS,
        output_dir="/tmp/assessment-run",
    )
    assert not any(cmd.tool == "chaitin-xray" for cmd in plan)
