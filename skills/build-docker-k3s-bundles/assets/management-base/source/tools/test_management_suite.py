"""Run the management-only regression suite against the packaged modules."""

import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "outputs/manage.pyz"
sys.path[:0] = [str(ARTIFACT), str(ROOT / "tests"), str(ROOT)]

MODULES = (
    "test_foundation", "test_terminal", "test_status_table", "test_images", "test_locations",
    "test_menu_views", "test_network", "test_lifecycle", "test_image_import", "test_management_changes",
    "test_firewall_rules",
)


if __name__ == "__main__":
    if not ARTIFACT.is_file():
        raise SystemExit("Build outputs/manage.pyz first")
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "artifact_sha256": hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
        "success": result.wasSuccessful(),
        "scope": "Packaged modules, source entrypoints, real local Compose configuration parser, mocked mutations",
        "remote_deployment": "Not evaluated by this local suite; see separate deployed reports",
        "runtime_mutation_integration": "Not evaluated by this local suite; see separate integration reports",
    }
    destination = ROOT / "outputs/reports/remaining-management-local.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"REPORT: {destination}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
