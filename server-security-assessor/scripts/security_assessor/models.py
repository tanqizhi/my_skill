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
class AssessmentRequest:
    mode: AssessmentMode
    coverage: Coverage
    external_targets: tuple[str, ...] = ()
    internal_paths: tuple[str, ...] = ()
    report_directed: bool = False
    allow_safe_poc: bool = False
    custom_baselines: tuple[str, ...] = ()
    forensic_mode: bool = False

    def __post_init__(self) -> None:
        if self.mode in (AssessmentMode.EXTERNAL, AssessmentMode.BOTH):
            if not self.external_targets:
                raise ValueError("external mode requires at least one target")

