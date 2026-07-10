from security_assessor.correlate import correlate_findings
from security_assessor.models import Finding


def finding(**overrides):
    values = dict(
        source="nuclei",
        asset="app.example.test",
        component="CVE-2024-1234",
        title="Example vulnerability",
        severity="high",
        status="probable",
        confidence="medium",
        identifiers=("CVE-2024-1234",),
        evidence_refs=("nuclei.jsonl:1",),
    )
    values.update(overrides)
    return Finding(**values)


def test_duplicate_scanner_findings_merge_with_stable_id_and_all_evidence():
    nuclei = finding()
    xray = finding(
        source="xray",
        component="sqldet",
        evidence_refs=("xray.json:1",),
    )

    correlated = correlate_findings((nuclei, xray))

    assert len(correlated) == 1
    merged = correlated[0]
    assert merged.source == "nuclei+xray"
    assert merged.evidence_refs == ("nuclei.jsonl:1", "xray.json:1")
    assert merged.finding_id
    assert merged.finding_id == correlate_findings((xray, nuclei))[0].finding_id


def test_both_mode_links_matching_listener_without_linking_other_virtual_host():
    external = finding(
        source="nmap",
        component="443/tcp",
        title="Open service: https",
        severity="info",
        status="confirmed",
        confidence="high",
        identifiers=("service:https",),
        evidence_refs=("nmap.xml",),
    )
    internal = finding(
        source="ssh",
        component="443/tcp",
        title="nginx listener",
        severity="info",
        status="confirmed",
        confidence="high",
        identifiers=("process:nginx",),
        evidence_refs=("ssh/listeners.txt",),
    )
    unrelated = finding(
        source="ssh",
        asset="other.example.test",
        component="443/tcp",
        title="other listener",
        identifiers=("process:other",),
        evidence_refs=("ssh/other.txt",),
    )

    correlated = correlate_findings((external, internal, unrelated))
    by_title = {item.title: item for item in correlated}
    assert by_title["nginx listener"].finding_id in by_title["Open service: https"].related_finding_ids
    assert by_title["other listener"].finding_id not in by_title["Open service: https"].related_finding_ids
