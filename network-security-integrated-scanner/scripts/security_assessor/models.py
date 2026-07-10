"""Canonical inputs and findings shared by assessment workflows."""

from dataclasses import dataclass
from enum import Enum


class AssessmentMode(str, Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    BOTH = "both"


class Coverage(str, Enum):
    FULL = "full"
    TARGETED = "targeted"


@dataclass(frozen=True)
class VerificationTarget:
    url: str
    tool: str
    selector: str


@dataclass(frozen=True)
class AssessmentRequest:
    mode: AssessmentMode
    coverage: Coverage
    external_targets: tuple[str, ...] = ()
    external_ports: tuple[int, ...] = ()
    internal_paths: tuple[str, ...] = ()
    report_directed: bool = False
    allow_safe_poc: bool = False
    verifications: tuple[VerificationTarget, ...] = ()
    custom_baselines: tuple[str, ...] = ()
    forensic_mode: bool = False

    def __post_init__(self) -> None:
        if self.mode in (AssessmentMode.EXTERNAL, AssessmentMode.BOTH):
            if not self.external_targets:
                raise ValueError("external mode requires at least one target")
        if any(port < 1 or port > 65535 for port in self.external_ports):
            raise ValueError("external ports must be between 1 and 65535")


@dataclass(frozen=True)
class Finding:
    source: str
    asset: str
    component: str
    title: str
    severity: str
    status: str
    confidence: str
    identifiers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class ParseResult:
    findings: tuple[Finding, ...]
    accepted: int
    rejected: int
    errors: tuple[str, ...] = ()
