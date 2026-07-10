from pathlib import Path
import re


ROOT = Path(__file__).parents[1]


def test_skill_contract_mentions_required_workflow():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: network-security-integrated-scanner\n")
    assert "TODO" not in text
    for phrase in [
        "External",
        "Internal",
        "Both",
        "全面检查",
        "定向检查",
        "report.md",
        "executive-report.html",
        "findings.json",
        "evidence/",
    ]:
        assert phrase in text


def test_skill_references_only_existing_local_resources():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    referenced = re.findall(r"\]\((references/[^)]+)\)", text)
    assert referenced
    assert all((ROOT / path).is_file() for path in referenced)


def test_agent_metadata_matches_skill_name():
    text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "Network Security Integrated Scanner"' in text
    assert "$network-security-integrated-scanner" in text


def test_skill_scripts_never_hide_scanner_or_ssh_subprocesses():
    scripts = (ROOT / "scripts").rglob("*.py")
    assert all("import subprocess" not in path.read_text(encoding="utf-8") for path in scripts)
