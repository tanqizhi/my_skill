"""Render deterministic technical, executive, and machine-readable reports."""

from dataclasses import asdict, dataclass
from html import escape
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote

from .models import Finding


@dataclass(frozen=True)
class RunSummary:
    mode: str
    generated_at: str
    title: str
    findings: tuple[Finding, ...]
    completed_checks: int
    total_checks: int
    coverage_gaps: tuple[str, ...] = ()
    scope_violations: tuple[str, ...] = ()


_WEIGHTS = {"critical": 25, "high": 10, "medium": 4, "low": 1, "info": 0, "unknown": 0}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}


def posture_score(findings: tuple[Finding, ...]) -> int:
    deduction = 0.0
    for finding in findings:
        multiplier = 1.0 if finding.status == "confirmed" else 0.5 if finding.status == "probable" else 0.0
        deduction += _WEIGHTS.get(finding.severity, 0) * multiplier
    return max(0, min(100, int(round(100 - deduction))))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _finding_dict(finding: Finding) -> dict[str, object]:
    payload = asdict(finding)
    for key, value in tuple(payload.items()):
        if isinstance(value, tuple):
            payload[key] = list(value)
    return payload


def _markdown(summary: RunSummary, score: int, coverage: int) -> str:
    lines = [
        f"# {escape(summary.title)}",
        "",
        f"- 模式：`{summary.mode}`",
        f"- 生成时间：`{summary.generated_at}`",
        f"- 安全态势分：**{score}/100**（评估指标，不等同合规认证）",
        f"- 检查覆盖率：**{coverage}%**（{summary.completed_checks}/{summary.total_checks}）",
        "",
        "## 覆盖缺口",
        "",
    ]
    gaps = summary.coverage_gaps or ("无已知覆盖缺口",)
    lines.extend(f"- {escape(gap)}" for gap in gaps)
    lines.extend([
        "",
        "> 未检查、不可评估或已停止的项目不能视为安全。",
        "",
        "## 发现",
        "",
    ])
    for finding in sorted(summary.findings, key=lambda item: (_SEVERITY_ORDER.get(item.severity, 9), item.finding_id)):
        lines.extend([
            f"### {finding.finding_id} · {escape(finding.title)}",
            "",
            f"- 资产：`{escape(finding.asset)}`",
            f"- 组件：`{escape(finding.component)}`",
            f"- 风险：`{finding.severity}`；状态：`{finding.status}`；可信度：`{finding.confidence}`",
            f"- 影响：{escape(finding.impact or '待结合业务确认')}",
            f"- 修复建议：{escape(finding.remediation or '根据厂商建议制定整改方案')}",
            f"- 复测：{escape(finding.retest_method or '在相同范围内重复验证')}",
            "- 证据：" + (", ".join(
                f"[{escape(reference)}](evidence/{quote(reference, safe='/:')})"
                for reference in finding.evidence_refs
            ) or "无可保存证据"),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _risk_bars(findings: tuple[Finding, ...]) -> str:
    counts = {
        severity: sum(1 for item in findings if item.severity == severity)
        for severity in ("critical", "high", "medium", "low")
    }
    maximum = max(counts.values(), default=0) or 1
    labels = {"critical": "严重", "high": "高危", "medium": "中危", "low": "低危"}
    return "".join(
        f'<div class="bar-row"><span>{labels[key]}</span><div class="bar"><i style="width:{round(value / maximum * 100)}%"></i></div><b>{value}</b></div>'
        for key, value in counts.items()
    )


def _finding_rows(findings: tuple[Finding, ...]) -> str:
    ordered = sorted(findings, key=lambda item: (_SEVERITY_ORDER.get(item.severity, 9), item.finding_id))
    if not ordered:
        return '<tr><td colspan="5">本次未形成有效发现；请结合覆盖率和缺口判断。</td></tr>'
    return "".join(
        "<tr>"
        f"<td><span class=\"pill\">{escape(item.finding_id)}</span></td>"
        f"<td>{escape(item.asset)}</td>"
        f"<td class=\"{escape(item.severity)}\">{escape(item.severity)}</td>"
        f"<td>{escape(item.title)}</td>"
        f"<td>{escape(item.remediation or '制定整改并复测')}</td>"
        "</tr>"
        for item in ordered[:12]
    )


def _html(summary: RunSummary, score: int, coverage: int) -> str:
    template_path = Path(__file__).parents[2] / "assets" / "executive-report-template.html"
    template = template_path.read_text(encoding="utf-8")
    top_risk = sum(1 for item in summary.findings if item.severity in {"critical", "high"})
    gaps = "<ul>" + "".join(f"<li>{escape(gap)}</li>" for gap in summary.coverage_gaps) + "</ul>"
    if not summary.coverage_gaps:
        gaps = "<p>无已知覆盖缺口。</p>"
    replacements = {
        "{{TITLE}}": escape(summary.title),
        "{{MODE}}": escape(summary.mode),
        "{{GENERATED_AT}}": escape(summary.generated_at),
        "{{SCORE}}": str(score),
        "{{COVERAGE}}": str(coverage),
        "{{TOP_RISK_COUNT}}": str(top_risk),
        "{{FINDING_COUNT}}": str(len(summary.findings)),
        "{{RISK_BARS}}": _risk_bars(summary.findings),
        "{{FINDING_ROWS}}": _finding_rows(summary.findings),
        "{{COVERAGE_GAPS}}": gaps,
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    return template


def render_reports(run_directory: Path, summary: RunSummary) -> tuple[Path, ...]:
    run_directory = run_directory.resolve()
    run_directory.mkdir(parents=True, exist_ok=True)
    if summary.total_checks < 0 or not 0 <= summary.completed_checks <= summary.total_checks:
        raise ValueError("coverage counts are inconsistent")
    score = posture_score(summary.findings)
    coverage = round(summary.completed_checks / summary.total_checks * 100) if summary.total_checks else 0
    machine_payload = {
        "schema_version": 1,
        "assessment": {
            "mode": summary.mode,
            "generated_at": summary.generated_at,
            "title": summary.title,
            "posture_score": score,
            "scope_violations": list(summary.scope_violations),
        },
        "coverage": {
            "completed": summary.completed_checks,
            "total": summary.total_checks,
            "gaps": list(summary.coverage_gaps),
        },
        "findings": [_finding_dict(finding) for finding in summary.findings],
    }
    markdown_path = run_directory / "report.md"
    html_path = run_directory / "executive-report.html"
    json_path = run_directory / "findings.json"
    _atomic_write(markdown_path, _markdown(summary, score, coverage))
    _atomic_write(html_path, _html(summary, score, coverage))
    _atomic_write(json_path, json.dumps(machine_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return markdown_path, html_path, json_path
