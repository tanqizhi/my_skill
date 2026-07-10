# Network Security Integrated Scanner Skill Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build one installable Codex skill that safely assesses authorized servers through external scanning, report-directed validation, read-only Linux SSH checks, optional forensics, and consistent technical/executive outputs.

**Architecture:** `SKILL.md` is the orchestrator and risk gate. Markdown/JSON references define external, internal, forensic, and baseline workflows; small Python standard-library modules generate reviewed command plans, normalize tool output, enforce scope, correlate evidence, and render reports. Scanner and SSH commands remain visible Codex tool calls so host approvals are never bypassed.

**Tech Stack:** Codex skill Markdown/YAML, Python 3.11+ standard library, pytest, JSON/JSONL/XML, self-contained HTML/CSS, Nmap, ProjectDiscovery Nuclei, optional Chaitin Xray, OpenSSH.

---

## Implementation constraints

- Work in a dedicated feature worktree or branch from commit `85a7e6e`.
- Use `@skill-creator` for Codex skill structure/evals, `@tdd` for each red-green-refactor loop, and `@executing-plans` to execute this document.
- Do not add automatic remediation in this version.
- Python code may produce argv arrays and parse outputs, but must not directly launch scanners, SSH, package managers, or downloads. `SKILL.md` presents those commands through Codex so normal approvals apply.
- Do not bundle Nmap, Nuclei, Xray, templates, licenses, or third-party PoCs in the repository.
- Real-business tests are manual gated tests. CI must never contain a routable production target or stored credential.

## Bootstrap commands

Run from repository root:

```bash
git switch -c feat/network-security-integrated-scanner
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

Expected: branch is created and `.venv/bin/python --version` reports Python 3.11 or newer.

### Task 1: Scaffold the skill and contract tests

**Files:**
- Create: `.gitignore`
- Create: `network-security-integrated-scanner/SKILL.md`
- Create: `network-security-integrated-scanner/pyproject.toml`
- Create: `network-security-integrated-scanner/scripts/security_assessor/__init__.py`
- Create: `network-security-integrated-scanner/tests/test_skill_contract.py`

**Step 1: Write the failing contract test**

Create `test_skill_contract.py` with tests that require valid frontmatter, the three modes, the scope question, the report outputs, and progressive references:

```python
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_skill_contract_mentions_required_workflow():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: network-security-integrated-scanner\n")
    for phrase in [
        "External", "Internal", "Both", "全面检查", "定向检查",
        "report.md", "executive-report.html", "findings.json", "evidence/",
    ]:
        assert phrase in text


def test_skill_references_only_existing_local_resources():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    referenced = [line.split("`", 2)[1] for line in text.splitlines()
                  if line.startswith("- Read `")]
    assert referenced
    assert all((ROOT / path).exists() for path in referenced)
```

**Step 2: Run the test and verify it fails**

Run: `.venv/bin/python -m pip install -e 'network-security-integrated-scanner[dev]' && .venv/bin/pytest network-security-integrated-scanner/tests/test_skill_contract.py -v`

Expected: FAIL because `SKILL.md` and referenced resources are absent or incomplete.

**Step 3: Add the minimum skill skeleton**

Use this frontmatter and top-level sequence in `SKILL.md`:

```markdown
---
name: network-security-integrated-scanner
description: Assess authorized Linux or Windows server exposure using External, Internal SSH, or Both modes; validate existing vulnerability reports; optionally perform safe Web and forensic checks; and produce evidence-backed Markdown, HTML, and JSON reports. Use when the user asks to audit, scan, verify, harden-assess, or investigate the security of a server or Web service.
---

# Network Security Integrated Scanner

1. Treat user-supplied targets as authorized, but never expand beyond them.
2. Ask for mode: External, Internal, or Both.
3. Ask for scope: 全面检查 or 定向检查.
4. Ask whether safe PoC is allowed when the selected mode includes External.
5. Run the relevant progressive workflow references.
6. Normalize evidence and always produce `report.md`, `executive-report.html`, `findings.json`, and `evidence/`.
7. Never remediate in version 1.
```

Add placeholder reference files named by the skeleton so the second contract test passes; later tasks replace their contents.

**Step 4: Run the contract test**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_skill_contract.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add .gitignore network-security-integrated-scanner
git commit -m "feat: scaffold server security assessor skill"
```

### Task 2: Implement the canonical request model and scope gate

**Files:**
- Create: `network-security-integrated-scanner/scripts/security_assessor/models.py`
- Create: `network-security-integrated-scanner/scripts/security_assessor/scope.py`
- Create: `network-security-integrated-scanner/tests/test_scope.py`
- Create: `network-security-integrated-scanner/references/scope-policy.md`

**Step 1: Write failing scope tests**

```python
import pytest
from security_assessor.models import AssessmentMode, AssessmentRequest, Coverage
from security_assessor.scope import ScopeViolation, assert_external_target, assert_internal_path


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
    req = request()
    with pytest.raises(ScopeViolation):
        assert_external_target(req, "https://api.example.test/")
    with pytest.raises(ScopeViolation):
        assert_external_target(req, "https://app.example.test/")


def test_internal_scope_rejects_unlisted_directory():
    with pytest.raises(ScopeViolation):
        assert_internal_path(request(), "/home")


def test_report_directed_request_cannot_expand_scope():
    req = request(report_directed=True)
    with pytest.raises(ScopeViolation):
        assert_external_target(req, "https://app.example.test/admin/other")
```

**Step 2: Run the tests and verify failure**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_scope.py -v`

Expected: FAIL with missing `models` and `scope` modules.

**Step 3: Implement the immutable request and strict containment rules**

Define string enums `AssessmentMode(EXTERNAL, INTERNAL, BOTH)` and `Coverage(FULL, TARGETED)`. Define a frozen `AssessmentRequest` dataclass with mode, coverage, target/path tuples, `report_directed`, `allow_safe_poc`, optional custom baseline paths, and optional forensic mode. Normalize hostnames to lowercase and paths without resolving symlinks. For targeted URLs, require exact origin and require the candidate path to be equal to or below the explicitly supplied path; for report-directed runs, require exact URL unless the report finding explicitly includes a path prefix. Never infer sibling domains, resolved IPs, CIDRs, or redirects as in-scope.

Document the same rules in `scope-policy.md`, including Windows external-only validation and separate external/internal scopes for Both mode.

**Step 4: Run tests**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_scope.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add network-security-integrated-scanner/scripts network-security-integrated-scanner/references/scope-policy.md network-security-integrated-scanner/tests/test_scope.py
git commit -m "feat: enforce assessment mode and target scope"
```

### Task 3: Add tool preflight and reviewed command planning

**Files:**
- Create: `network-security-integrated-scanner/scripts/security_assessor/preflight.py`
- Create: `network-security-integrated-scanner/scripts/security_assessor/command_plan.py`
- Create: `network-security-integrated-scanner/tests/test_preflight.py`
- Create: `network-security-integrated-scanner/tests/test_command_plan.py`
- Create: `network-security-integrated-scanner/references/tool-installation.md`
- Create: `network-security-integrated-scanner/references/external-assessment.md`

**Step 1: Write failing tests**

Test that preflight identifies Darwin/Linux, `arm64`/`amd64`, package-manager candidates, and exact executable paths. Add a collision test where `xray version` identifies XTLS/Xray-core and must be rejected as the Chaitin scanner.

Test command plans as argv arrays, not shell strings:

```python
from security_assessor.command_plan import build_external_plan


def test_web_target_adds_optional_xray_without_shell_interpolation(request):
    plan = build_external_plan(request, open_services=[("app.example.test", 443, "https")], enable_xray=True)
    assert any(cmd.tool == "nuclei" and "-jsonl" in cmd.argv for cmd in plan)
    assert any(cmd.tool == "chaitin-xray" and "webscan" in cmd.argv for cmd in plan)
    assert all(cmd.shell is False for cmd in plan)


def test_report_validation_never_uses_xray_crawler(report_request):
    plan = build_external_plan(report_request, open_services=[], enable_xray=True)
    argv = [arg for cmd in plan for arg in cmd.argv]
    assert "--basic-crawler" not in argv
```

Also test that an Internal-only request produces no Nmap/Nuclei/Xray commands, and unsafe characters remain one literal argv element.

**Step 2: Verify failures**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_preflight.py network-security-integrated-scanner/tests/test_command_plan.py -v`

Expected: FAIL because the modules do not exist.

**Step 3: Implement preflight and command plans**

`preflight.py` must only inspect OS/architecture, `PATH`, executable version text supplied by the caller, and package-manager availability. It returns data; it does not install anything.

`command_plan.py` returns frozen `PlannedCommand(tool, argv, purpose, risk, shell=False)` objects. Generate conservative commands with structured outputs:

- Nmap: XML output and scope-selected ports; do not add host discovery or CIDR expansion that the user did not request.
- Nuclei: explicit input, JSONL output, conservative rate/concurrency, no cloud upload, and only selected template classes.
- Chaitin Xray: only for identified Web services; crawler allowed in full active scans, exact URL/plugin validation in targeted or report-directed scans.

`tool-installation.md` must define reviewed install actions for Homebrew, APT, DNF/YUM, official Nuclei binaries, and the Chaitin Xray binary. Require Xray license acceptance, architecture matching, official checksum verification, an absolute resolved executable path, and the configured `http://127.0.0.1:7890` proxy when foreign downloads require it. Do not confuse Chaitin Xray with XTLS/Xray-core.

**Step 4: Run tests**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_preflight.py network-security-integrated-scanner/tests/test_command_plan.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add network-security-integrated-scanner
git commit -m "feat: plan reviewed external security commands"
```

### Task 4: Normalize Nmap, Nuclei, and Xray results

**Files:**
- Create: `network-security-integrated-scanner/scripts/security_assessor/parsers/__init__.py`
- Create: `network-security-integrated-scanner/scripts/security_assessor/parsers/nmap.py`
- Create: `network-security-integrated-scanner/scripts/security_assessor/parsers/nuclei.py`
- Create: `network-security-integrated-scanner/scripts/security_assessor/parsers/xray.py`
- Create: `network-security-integrated-scanner/tests/fixtures/nmap.xml`
- Create: `network-security-integrated-scanner/tests/fixtures/nuclei.jsonl`
- Create: `network-security-integrated-scanner/tests/fixtures/xray.json`
- Create: `network-security-integrated-scanner/tests/test_parsers.py`

**Step 1: Write fixture-backed failing tests**

Require each parser to return canonical `Finding` objects with source, asset, component, title, severity, status, confidence, identifiers, and evidence references. Include duplicate CVE fixtures across Nuclei and Xray. Add these Xray edge cases:

```python
def test_xray_missing_output_is_empty_only_after_success(tmp_path):
    assert parse_xray(tmp_path / "missing.json", exit_code=0) == []
    with pytest.raises(ParseFailure):
        parse_xray(tmp_path / "missing.json", exit_code=2)
```

**Step 2: Verify failure**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_parsers.py -v`

Expected: FAIL with missing parser modules and model fields.

**Step 3: Implement strict parsers**

Use `xml.etree.ElementTree` for Nmap and `json` for Nuclei/Xray. Reject malformed records individually while returning a parse-coverage object that lists accepted and rejected counts. Never interpret tool absence, truncation, or parse failure as “no vulnerabilities.” Preserve raw evidence by path/reference rather than embedding request bodies containing secrets.

**Step 4: Run parser tests**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_parsers.py -v`

Expected: PASS with all three fixtures normalized.

**Step 5: Commit**

```bash
git add network-security-integrated-scanner/scripts/security_assessor/parsers network-security-integrated-scanner/tests
git commit -m "feat: normalize external scanner evidence"
```

### Task 5: Implement report-directed validation

**Files:**
- Create: `network-security-integrated-scanner/schemas/report-findings.schema.json`
- Create: `network-security-integrated-scanner/scripts/security_assessor/report_input.py`
- Create: `network-security-integrated-scanner/references/report-validation.md`
- Create: `network-security-integrated-scanner/tests/fixtures/report-findings.json`
- Create: `network-security-integrated-scanner/tests/test_report_input.py`

**Step 1: Write failing tests**

Test a canonical imported finding with target, URL/port, vulnerability identifier, source report page/row, and optional exact verification method. Assert that generated verification requests contain only report targets and never add Nmap discovery or Xray crawling.

**Step 2: Verify failure**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_report_input.py -v`

Expected: FAIL because the schema/loader is missing.

**Step 3: Implement the canonical import boundary**

Support direct parsing for canonical JSON and common CSV columns. For PDF, HTML, Markdown, or vendor-specific reports, `report-validation.md` instructs Codex to extract rows into `report-findings.json`, retain page/row provenance, validate against the schema, show ambiguous mappings to the user, and only then build verification commands. Map results to `confirmed`, `probable`, `not-reproduced`, or `not-assessable`; never drop unverified report rows.

**Step 4: Run tests and schema validation**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_report_input.py -v`

Expected: PASS; every fixture row retains its report provenance.

**Step 5: Commit**

```bash
git add network-security-integrated-scanner/schemas network-security-integrated-scanner/scripts network-security-integrated-scanner/references/report-validation.md network-security-integrated-scanner/tests
git commit -m "feat: constrain vulnerability report validation"
```

### Task 6: Add Linux SSH and forensic check catalogs

**Files:**
- Create: `network-security-integrated-scanner/references/checks/linux-checks.json`
- Create: `network-security-integrated-scanner/references/checks/forensic-checks.json`
- Create: `network-security-integrated-scanner/references/linux-internal-assessment.md`
- Create: `network-security-integrated-scanner/references/forensics.md`
- Create: `network-security-integrated-scanner/scripts/security_assessor/ssh_plan.py`
- Create: `network-security-integrated-scanner/tests/test_ssh_plan.py`

**Step 1: Write failing catalog/plan tests**

Validate that every check has `id`, supported distro families, purpose, argv or command, `requires_root`, `high_cost`, `writes_target: false`, expected evidence, and timeout. Add tests that:

- A targeted service/directory returns only matching checks.
- A normal account marks root-only checks as requiring confirmed `sudo`.
- A root account does not prepend `sudo`.
- Forensic checks require either explicit forensic mode or a recorded upgrade confirmation.
- Catalog commands fail lint if they contain package installation, deletion, permission changes, service restarts, output redirection, persistence, or credential-dumping patterns.

**Step 2: Verify failure**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_ssh_plan.py -v`

Expected: FAIL because catalogs and planner are absent.

**Step 3: Implement catalogs and planner**

Cover Ubuntu/Debian and RHEL/CentOS/Rocky/Alma families. The standard catalog includes OS/patches, users/authentication, SSH, firewall, listeners/services, packages, permissions, kernel controls, containers, logs, scheduled jobs, startup entries, processes, and current connections. The forensic catalog adds login/process/network timelines, persistence indicators, suspicious files and hashes, but excludes memory/disk imaging by default.

`ssh_plan.py` filters catalogs by distro, scope, privilege, and forensic gate, then returns reviewed command records with expected evidence and timeout. It must not open SSH itself.

**Step 4: Run tests**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_ssh_plan.py -v`

Expected: PASS; no catalog item writes to the target.

**Step 5: Commit**

```bash
git add network-security-integrated-scanner/references network-security-integrated-scanner/scripts/security_assessor/ssh_plan.py network-security-integrated-scanner/tests/test_ssh_plan.py
git commit -m "feat: define read-only Linux and forensic checks"
```

### Task 7: Add evidence integrity, redaction, deduplication, and correlation

**Files:**
- Create: `network-security-integrated-scanner/schemas/findings.schema.json`
- Create: `network-security-integrated-scanner/scripts/security_assessor/evidence.py`
- Create: `network-security-integrated-scanner/scripts/security_assessor/correlate.py`
- Create: `network-security-integrated-scanner/references/report-schema.md`
- Create: `network-security-integrated-scanner/tests/test_evidence.py`
- Create: `network-security-integrated-scanner/tests/test_correlate.py`

**Step 1: Write failing security tests**

Test SHA-256 manifests, deterministic finding IDs, and redaction of passwords, private-key blocks, bearer tokens, cookies, authorization headers, and sudo prompts. Assert raw secret values do not occur anywhere in serialized evidence.

Test that matching asset/component/CVE findings from Nuclei and Xray merge into one finding with two evidence references, and that Both mode can link an external `443/tcp` service to its internal listener/process without merging unrelated virtual hosts.

**Step 2: Verify failure**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_evidence.py network-security-integrated-scanner/tests/test_correlate.py -v`

Expected: FAIL because integrity/redaction/correlation modules are missing.

**Step 3: Implement minimal safe transformations**

Write evidence files only inside the caller-provided run directory. Use atomic temporary-file replacement, SHA-256, restrictive file modes where supported, and a manifest containing relative paths only. Generate finding IDs from normalized asset, component, primary identifier, and title. Merge only high-confidence keys; otherwise retain separate findings and add a possible-correlation link.

Document the four statuses and the rule that `not-assessable` reduces coverage but never counts as safe.

**Step 4: Run tests**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_evidence.py network-security-integrated-scanner/tests/test_correlate.py -v`

Expected: PASS, with no fixture secret visible in output.

**Step 5: Commit**

```bash
git add network-security-integrated-scanner
git commit -m "feat: preserve and correlate assessment evidence"
```

### Task 8: Render all outputs and complete end-to-end acceptance

**Files:**
- Create: `network-security-integrated-scanner/assets/executive-report-template.html`
- Create: `network-security-integrated-scanner/scripts/security_assessor/report.py`
- Create: `network-security-integrated-scanner/scripts/validate_run.py`
- Create: `network-security-integrated-scanner/tests/fixtures/complete-run.json`
- Create: `network-security-integrated-scanner/tests/test_report.py`
- Create: `network-security-integrated-scanner/tests/test_end_to_end.py`
- Modify: `network-security-integrated-scanner/SKILL.md`
- Modify: `network-security-integrated-scanner/pyproject.toml`

**Step 1: Write failing report tests**

Require one run to produce `report.md`, `executive-report.html`, `findings.json`, and `evidence/manifest.json`. Assert:

- HTML is self-contained: no external scripts, stylesheets, fonts, tracking, or CDN URLs.
- User-controlled evidence is HTML-escaped.
- The executive report shows posture score, coverage, risk distribution, top findings, affected assets, and remediation priority.
- Technical Markdown links every finding to evidence.
- JSON validates against `findings.schema.json`.
- Partial runs visibly state missing coverage and do not claim the server is secure.

Use a deterministic posture score: begin at 100; subtract 25/10/4/1 for unique confirmed critical/high/medium/low findings and half those values for probable findings; clamp to 0..100. Show coverage separately and label the score as an assessment indicator, not compliance certification.

**Step 2: Verify failure**

Run: `.venv/bin/pytest network-security-integrated-scanner/tests/test_report.py network-security-integrated-scanner/tests/test_end_to_end.py -v`

Expected: FAIL because renderer/template are missing.

**Step 3: Implement rendering and finish SKILL.md**

Use Python standard-library HTML escaping and a checked-in template with inline CSS and print styles. Use inline SVG or CSS-only bars for charts. `validate_run.py RUN_DIR` validates required files, schema shape, evidence hashes, out-of-scope records, HTML external references, and unresolved secret markers.

Finish `SKILL.md` with the complete order:

1. mode question;
2. scope question;
3. report/no-report routing;
4. tool preflight and reviewed installation;
5. safe PoC choice;
6. External/Internal/Both execution;
7. optional/upgrade forensic gate;
8. normalization and correlation;
9. four-output rendering;
10. explicit summary of coverage, failures, and stopped checks.

**Step 4: Run the complete automated suite**

Run:

```bash
.venv/bin/pytest network-security-integrated-scanner/tests -v
.venv/bin/python -m compileall -q network-security-integrated-scanner/scripts
.venv/bin/python network-security-integrated-scanner/scripts/validate_run.py network-security-integrated-scanner/tests/fixtures/expected-run
```

Expected: all tests PASS, compileall exits 0, and validator prints `VALID` with zero scope, hash, schema, HTML, or redaction errors.

**Step 5: Perform controlled integration tests**

First run against local/isolated fixtures: one Debian-family SSH container, one RHEL-family SSH container, and an intentionally vulnerable local Web application. Use targeted scope before full scope. Expected: known findings are detected, duplicate Web findings merge, all four outputs render, and no request crosses the fixture allowlist.

Then perform a manual gated test against a user-supplied, user-owned real business target:

1. Record the exact External/Internal/Both mode and full/targeted scope.
2. Capture a health baseline and choose conservative rates/timeouts.
3. Run discovery and non-PoC checks first.
4. Enable Chaitin Xray only when the target is a Web business and its URL scope is explicit.
5. Run safe PoCs only when the run input permits them.
6. Monitor business health; stop immediately on latency, error-rate, load, or availability degradation.
7. Validate the output directory and record any stopped/not-assessable checks.

Expected: zero out-of-scope traffic, no target state changes, no material health degradation, and a complete or explicitly partial deliverable. Never store the real target or credentials in repository fixtures.

**Step 6: Commit**

```bash
git add network-security-integrated-scanner
git commit -m "feat: deliver server security assessment reports"
```

## Final verification

Run:

```bash
git status --short
.venv/bin/pytest network-security-integrated-scanner/tests -q
.venv/bin/python -m compileall -q network-security-integrated-scanner/scripts
```

Expected: clean worktree, all tests pass, and Python compilation exits 0. Review the generated HTML at desktop and print widths, confirm every report claim has evidence, and confirm no scanner/SSH subprocess is hidden inside Python code.
