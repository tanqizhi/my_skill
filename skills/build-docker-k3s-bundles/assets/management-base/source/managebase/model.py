from dataclasses import dataclass, field
from typing import Any


class ManagementError(Exception):
    def __init__(self, message: str, code: int = 3):
        super().__init__(message)
        self.code = code


@dataclass
class Result:
    summary: str
    code: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "success" if self.code == 0 else "failed",
            "code": self.code,
            "summary": self.summary,
            "data": self.data,
        }
