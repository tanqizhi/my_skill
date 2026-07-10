"""Read-only assessment-machine capability discovery."""

from dataclasses import dataclass
import platform
import shutil
from typing import Mapping


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class EnvironmentStatus:
    system: str
    architecture: str
    package_managers: tuple[str, ...]
    tools: dict[str, ToolStatus]


def _architecture(machine: str) -> str:
    normalized = machine.lower()
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    if normalized in {"x86_64", "amd64"}:
        return "amd64"
    return normalized


def _looks_like_xray_core(output: str) -> bool:
    lowered = output.lower()
    signatures = (
        "anti-censorship",
        "penetrates everything",
        "xray-core",
        "xtls",
        "vmess",
        "vless",
    )
    return any(signature in lowered for signature in signatures)


def _looks_like_chaitin_xray(output: str) -> bool:
    lowered = output.lower()
    return "chaitin" in lowered or "长亭" in output or "webscan" in lowered


def inspect_environment(
    *,
    system: str | None = None,
    machine: str | None = None,
    version_outputs: Mapping[str, str] | None = None,
) -> EnvironmentStatus:
    """Inspect local names and caller-supplied version text without executing tools."""
    detected_system = (system or platform.system()).lower()
    architecture = _architecture(machine or platform.machine())
    version_outputs = version_outputs or {}

    manager_names = {
        "darwin": ("brew",),
        "linux": ("apt-get", "dnf", "yum"),
    }.get(detected_system, ())
    managers = tuple(name for name in manager_names if shutil.which(name))

    tools: dict[str, ToolStatus] = {}
    for name in ("nmap", "nuclei"):
        path = shutil.which(name)
        tools[name] = ToolStatus(name, path, bool(path), "" if path else "not found")

    candidates = (
        "chaitin-xray",
        f"xray_{'darwin' if detected_system == 'darwin' else detected_system}_{architecture}",
        "xray",
    )
    xray_path = next((path for name in candidates if (path := shutil.which(name))), None)
    if not xray_path:
        tools["chaitin-xray"] = ToolStatus(
            "chaitin-xray", None, False, "not found"
        )
    elif _looks_like_xray_core(version_outputs.get(xray_path, "")):
        tools["chaitin-xray"] = ToolStatus(
            "chaitin-xray",
            xray_path,
            False,
            "resolved executable is XTLS/Xray-core, not Chaitin Xray",
        )
    elif not _looks_like_chaitin_xray(version_outputs.get(xray_path, "")):
        tools["chaitin-xray"] = ToolStatus(
            "chaitin-xray",
            xray_path,
            False,
            "executable identity was not validated as Chaitin Xray",
        )
    else:
        tools["chaitin-xray"] = ToolStatus("chaitin-xray", xray_path, True)

    return EnvironmentStatus(
        system=detected_system,
        architecture=architecture,
        package_managers=managers,
        tools=tools,
    )
