from pathlib import Path
import json
import pytest

from security_assessor.ssh_plan import (
    CatalogError,
    ForensicGateError,
    build_ssh_plan,
    load_catalog,
)


ROOT = Path(__file__).parents[1]
LINUX = ROOT / "references" / "checks" / "linux-checks.json"
FORENSIC = ROOT / "references" / "checks" / "forensic-checks.json"


def test_check_catalogs_are_complete_and_read_only():
    checks = load_catalog(LINUX) + load_catalog(FORENSIC)
    required_categories = {
        "system", "patches", "accounts", "ssh", "firewall", "services",
        "packages", "permissions", "kernel", "containers", "logs",
        "scheduled-jobs", "startup", "processes", "connections", "forensics",
    }
    assert required_categories <= {category for check in checks for category in check.categories}
    assert all(check.writes_target is False for check in checks)
    assert all(check.timeout_seconds > 0 for check in checks)
    assert all(check.expected_evidence for check in checks)
    assert all(check.argv and check.argv[0] not in {"sh", "bash", "zsh"} for check in checks)


def test_targeted_ssh_plan_filters_scope_and_marks_sudo_confirmation():
    plan = build_ssh_plan(
        load_catalog(LINUX),
        distro_family="debian",
        categories=("ssh",),
        paths=("/etc/ssh",),
        account_is_root=False,
        sudo_confirmed=False,
        forensic_enabled=False,
        forensic_upgrade_confirmed=False,
    )

    assert {check.id for check in plan} == {
        "linux.ssh.effective-config",
        "linux.ssh.config-metadata",
    }
    root_check = next(check for check in plan if check.id == "linux.ssh.effective-config")
    assert root_check.requires_confirmation
    assert root_check.argv[0] == "sshd"


def test_catalog_loader_rejects_state_changing_commands(tmp_path):
    record = {
        "id": "unsafe.delete",
        "categories": ["forensics"],
        "distros": ["debian"],
        "purpose": "unsafe",
        "argv": ["rm", "-rf", "/"],
        "requires_root": True,
        "high_cost": False,
        "writes_target": False,
        "expected_evidence": "none",
        "timeout_seconds": 10,
    }
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(CatalogError, match="forbidden"):
        load_catalog(path)


def test_root_runs_directly_while_confirmed_normal_account_uses_sudo():
    checks = load_catalog(LINUX)
    root_plan = build_ssh_plan(
        checks,
        distro_family="debian",
        categories=("ssh",),
        account_is_root=True,
        sudo_confirmed=False,
        forensic_enabled=False,
        forensic_upgrade_confirmed=False,
    )
    root_check = next(check for check in root_plan if check.id == "linux.ssh.effective-config")
    assert root_check.argv[0] == "sshd"
    assert not root_check.requires_confirmation

    sudo_plan = build_ssh_plan(
        checks,
        distro_family="debian",
        categories=("ssh",),
        account_is_root=False,
        sudo_confirmed=True,
        forensic_enabled=False,
        forensic_upgrade_confirmed=False,
    )
    sudo_check = next(check for check in sudo_plan if check.id == "linux.ssh.effective-config")
    assert sudo_check.argv[:3] == ("sudo", "--", "sshd")


def test_forensics_requires_mode_or_upgrade_confirmation():
    checks = load_catalog(FORENSIC)
    with pytest.raises(ForensicGateError):
        build_ssh_plan(
            checks,
            distro_family="debian",
            categories=("forensics",),
            account_is_root=True,
            sudo_confirmed=False,
            forensic_enabled=False,
            forensic_upgrade_confirmed=False,
        )

    plan = build_ssh_plan(
        checks,
        distro_family="debian",
        categories=("forensics",),
        account_is_root=True,
        sudo_confirmed=False,
        forensic_enabled=False,
        forensic_upgrade_confirmed=True,
    )
    assert plan
    assert all(check.id.startswith("forensics.") for check in plan)
