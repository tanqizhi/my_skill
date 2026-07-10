import pytest

from security_assessor.models import AssessmentMode, AssessmentRequest, Coverage
from security_assessor.scope import (
    ScopeViolation,
    assert_external_target,
    assert_internal_path,
)


def request(**overrides):
    values = dict(
        mode=AssessmentMode.BOTH,
        coverage=Coverage.TARGETED,
        external_targets=("https://app.example.test/admin",),
        internal_paths=("/etc/ssh", "/var/log/auth.log"),
        report_directed=False,
        allow_safe_poc=False,
    )
    values.update(overrides)
    return AssessmentRequest(**values)


def test_external_scope_rejects_sibling_host_and_parent_path():
    assessment = request()
    with pytest.raises(ScopeViolation):
        assert_external_target(assessment, "https://api.example.test/")
    with pytest.raises(ScopeViolation):
        assert_external_target(assessment, "https://app.example.test/")
    assert_external_target(assessment, "https://app.example.test/admin/users")


def test_internal_scope_accepts_children_and_rejects_unlisted_directory():
    assessment = request()
    assert_internal_path(assessment, "/etc/ssh/sshd_config")
    with pytest.raises(ScopeViolation):
        assert_internal_path(assessment, "/home")
    with pytest.raises(ScopeViolation):
        assert_internal_path(assessment, "/etc/ssh-old")


def test_report_directed_request_requires_exact_report_url():
    assessment = request(report_directed=True)
    assert_external_target(assessment, "https://app.example.test/admin")
    with pytest.raises(ScopeViolation):
        assert_external_target(assessment, "https://app.example.test/admin/other")
