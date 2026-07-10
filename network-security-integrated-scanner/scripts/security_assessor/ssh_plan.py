"""Load and filter read-only SSH check catalogs without opening SSH."""

from dataclasses import dataclass
import json
from pathlib import Path


class CatalogError(ValueError):
    """Raised when a check catalog violates its safety contract."""


class ForensicGateError(ValueError):
    """Raised when forensic commands are requested without confirmation."""


@dataclass(frozen=True)
class SSHCheck:
    id: str
    categories: tuple[str, ...]
    distros: tuple[str, ...]
    purpose: str
    argv: tuple[str, ...]
    requires_root: bool
    high_cost: bool
    writes_target: bool
    expected_evidence: str
    timeout_seconds: int
    paths: tuple[str, ...] = ()
    forensic: bool = False


@dataclass(frozen=True)
class PlannedSSHCheck:
    id: str
    argv: tuple[str, ...]
    purpose: str
    expected_evidence: str
    timeout_seconds: int
    high_cost: bool
    requires_confirmation: bool


_REQUIRED_FIELDS = {
    "id", "categories", "distros", "purpose", "argv", "requires_root",
    "high_cost", "writes_target", "expected_evidence", "timeout_seconds",
}

_FORBIDDEN_EXECUTABLES = {
    "rm", "mv", "cp", "chmod", "chown", "tee", "truncate", "dd", "mkfs",
    "reboot", "shutdown", "poweroff", "kill", "pkill", "useradd", "usermod",
    "userdel", "passwd", "unshadow", "john", "hashcat", "nc", "ncat",
}
_FORBIDDEN_PACKAGE_ACTIONS = {"install", "upgrade", "update", "remove", "erase", "downgrade"}
_FORBIDDEN_SYSTEMCTL_ACTIONS = {
    "start", "stop", "restart", "reload", "enable", "disable", "mask",
    "unmask", "daemon-reload",
}


def _reject_forbidden_argv(check_id: str, argv: list[str]) -> None:
    executable = Path(argv[0]).name
    lowered = {arg.lower() for arg in argv[1:]}
    if executable in _FORBIDDEN_EXECUTABLES:
        raise CatalogError(f"{check_id} uses forbidden executable {executable}")
    if executable in {"sh", "bash", "zsh", "fish"}:
        raise CatalogError(f"{check_id} uses a forbidden shell")
    if executable in {"apt", "apt-get", "dnf", "yum"} and lowered.intersection(_FORBIDDEN_PACKAGE_ACTIONS):
        raise CatalogError(f"{check_id} uses a forbidden package action")
    if executable == "rpm" and lowered.intersection({"-i", "-u", "-e", "--install", "--upgrade", "--erase"}):
        raise CatalogError(f"{check_id} uses a forbidden rpm action")
    if executable == "systemctl" and lowered.intersection(_FORBIDDEN_SYSTEMCTL_ACTIONS):
        raise CatalogError(f"{check_id} uses a forbidden systemctl action")
    if executable == "find" and lowered.intersection({"-delete", "-exec", "-execdir", "-ok"}):
        raise CatalogError(f"{check_id} uses a forbidden find action")
    if lowered.intersection({">", ">>", "2>", "1>"}):
        raise CatalogError(f"{check_id} uses forbidden output redirection")


def load_catalog(path: Path) -> tuple[SSHCheck, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"cannot load check catalog {path}: {error}") from error
    if not isinstance(payload, list):
        raise CatalogError("check catalog must be an array")

    checks: list[SSHCheck] = []
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            raise CatalogError(f"record {index} is not an object")
        missing = _REQUIRED_FIELDS - record.keys()
        if missing:
            raise CatalogError(f"record {index} missing: {', '.join(sorted(missing))}")
        if record["writes_target"] is not False:
            raise CatalogError(f"{record['id']} must declare writes_target false")
        argv = record["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
            raise CatalogError(f"{record['id']} argv must be a non-empty string array")
        _reject_forbidden_argv(str(record["id"]), argv)
        checks.append(SSHCheck(
            id=str(record["id"]),
            categories=tuple(record["categories"]),
            distros=tuple(record["distros"]),
            purpose=str(record["purpose"]),
            argv=tuple(argv),
            requires_root=bool(record["requires_root"]),
            high_cost=bool(record["high_cost"]),
            writes_target=False,
            expected_evidence=str(record["expected_evidence"]),
            timeout_seconds=int(record["timeout_seconds"]),
            paths=tuple(record.get("paths", ())),
            forensic=bool(record.get("forensic", False)),
        ))
    return tuple(checks)


def _path_matches(check_path: str, requested_path: str) -> bool:
    check_base = check_path.rstrip("/") or "/"
    requested_base = requested_path.rstrip("/") or "/"
    return (
        check_base == requested_base
        or check_base.startswith(requested_base + "/")
        or requested_base.startswith(check_base + "/")
    )


def build_ssh_plan(
    checks: tuple[SSHCheck, ...],
    *,
    distro_family: str,
    categories: tuple[str, ...] = (),
    paths: tuple[str, ...] = (),
    account_is_root: bool,
    sudo_confirmed: bool,
    forensic_enabled: bool,
    forensic_upgrade_confirmed: bool,
) -> tuple[PlannedSSHCheck, ...]:
    requested_categories = set(categories)
    forensic_allowed = forensic_enabled or forensic_upgrade_confirmed
    if "forensics" in requested_categories and not forensic_allowed:
        raise ForensicGateError("forensic checks require explicit mode or upgrade confirmation")

    planned: list[PlannedSSHCheck] = []
    for check in checks:
        if distro_family not in check.distros:
            continue
        if check.forensic and not forensic_allowed:
            continue
        if requested_categories or paths:
            category_match = bool(requested_categories.intersection(check.categories))
            path_match = any(
                _path_matches(check_path, requested_path)
                for check_path in check.paths
                for requested_path in paths
            )
            if not category_match and not path_match:
                continue

        needs_sudo = check.requires_root and not account_is_root
        argv = check.argv
        if needs_sudo and sudo_confirmed:
            argv = ("sudo", "--", *argv)
        planned.append(PlannedSSHCheck(
            id=check.id,
            argv=argv,
            purpose=check.purpose,
            expected_evidence=check.expected_evidence,
            timeout_seconds=check.timeout_seconds,
            high_cost=check.high_cost,
            requires_confirmation=needs_sudo and not sudo_confirmed,
        ))
    return tuple(planned)
