import json

import pytest

from security_assessor.evidence import EvidenceStore, EvidencePathError


def test_evidence_store_redacts_secrets_and_writes_verified_manifest(tmp_path):
    store = EvidenceStore(tmp_path)
    record = store.write_text(
        "ssh/session.txt",
        "Authorization: Bearer fake-token-123\n"
        "Cookie: session=fake-cookie-456\n"
        "password=fake-password-789\n"
        "api_key=fake-api-key-321\n"
        "[sudo] password for audit: fake-sudo-secret\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key-material\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
    )
    manifest_path = store.write_manifest()

    saved = (tmp_path / "evidence" / "ssh" / "session.txt").read_text()
    serialized = saved + manifest_path.read_text()
    for secret in [
        "fake-token-123", "fake-cookie-456", "fake-password-789",
        "fake-api-key-321", "fake-sudo-secret", "fake-key-material",
    ]:
        assert secret not in serialized
    manifest = json.loads(manifest_path.read_text())
    assert manifest["files"][0]["path"] == "ssh/session.txt"
    assert manifest["files"][0]["sha256"] == record.sha256

    with pytest.raises(EvidencePathError):
        store.write_text("../escape.txt", "blocked")
