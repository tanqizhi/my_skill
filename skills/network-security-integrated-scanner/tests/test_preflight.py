from security_assessor.preflight import inspect_environment


def test_preflight_identifies_darwin_arm64_and_rejects_xray_core(monkeypatch):
    paths = {
        "brew": "/opt/homebrew/bin/brew",
        "nmap": "/opt/homebrew/bin/nmap",
        "nuclei": "/opt/homebrew/bin/nuclei",
        "xray": "/opt/homebrew/bin/xray",
    }
    monkeypatch.setattr("shutil.which", paths.get)
    environment = inspect_environment(
        system="Darwin",
        machine="arm64",
        version_outputs={
            "/opt/homebrew/bin/xray": "Xray, Penetrates Everything. A unified platform for anti-censorship.",
        },
    )

    assert environment.system == "darwin"
    assert environment.architecture == "arm64"
    assert environment.package_managers == ("brew",)
    assert environment.tools["nmap"].available
    assert environment.tools["nuclei"].available
    assert not environment.tools["chaitin-xray"].available
    assert "XTLS/Xray-core" in environment.tools["chaitin-xray"].reason


def test_preflight_requires_chaitin_xray_identity_evidence(monkeypatch):
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/opt/security/xray_darwin_arm64" if name == "xray_darwin_arm64" else None,
    )
    unknown = inspect_environment(system="Darwin", machine="arm64")
    assert not unknown.tools["chaitin-xray"].available
    assert "not validated" in unknown.tools["chaitin-xray"].reason

    validated = inspect_environment(
        system="Darwin",
        machine="arm64",
        version_outputs={
            "/opt/security/xray_darwin_arm64": "Chaitin xray security scanner: webscan command available",
        },
    )
    assert validated.tools["chaitin-xray"].available
