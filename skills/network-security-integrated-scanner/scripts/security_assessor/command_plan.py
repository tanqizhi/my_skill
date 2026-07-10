"""Generate reviewable argv records; never execute subprocesses."""

from dataclasses import dataclass
import os
from urllib.parse import urlsplit

from .models import AssessmentMode, AssessmentRequest, Coverage


@dataclass(frozen=True)
class ToolPaths:
    nmap: str
    nuclei: str
    chaitin_xray: str | None = None

    def __post_init__(self) -> None:
        for path in (self.nmap, self.nuclei, self.chaitin_xray):
            if path is not None and not os.path.isabs(path):
                raise ValueError("tool paths must be absolute")


@dataclass(frozen=True)
class PlannedCommand:
    tool: str
    argv: tuple[str, ...]
    purpose: str
    risk: str = "read-only"
    shell: bool = False


def _host(target: str) -> str:
    parsed = urlsplit(target)
    return parsed.hostname or target


def _target_port(target: str) -> int | None:
    parsed = urlsplit(target)
    if parsed.port:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


def build_external_plan(
    request: AssessmentRequest,
    *,
    open_services: tuple[tuple[str, int, str], ...],
    enable_xray: bool,
    tools: ToolPaths,
    output_dir: str,
) -> tuple[PlannedCommand, ...]:
    if request.mode is AssessmentMode.INTERNAL:
        return ()

    commands: list[PlannedCommand] = []
    for index, target in enumerate(request.external_targets):
        if not request.report_directed:
            ports = request.external_ports
            if not ports and request.coverage is Coverage.TARGETED:
                inferred = _target_port(target)
                ports = (inferred,) if inferred else ()
            port_arg = ",".join(str(port) for port in sorted(set(ports)))
            nmap_argv = [
                tools.nmap,
                "-Pn",
                "-sV",
                "--version-light",
                "-T3",
                "--max-retries",
                "2",
                "--host-timeout",
                "30m",
                "-oX",
                os.path.join(output_dir, f"nmap-{index}.xml"),
            ]
            if request.coverage is Coverage.FULL and not port_arg:
                nmap_argv.extend(("-p-",))
            elif port_arg:
                nmap_argv.extend(("-p", port_arg))
            nmap_argv.append(_host(target))
            commands.append(PlannedCommand(
                tool="nmap",
                argv=tuple(nmap_argv),
                purpose="bounded port and service discovery",
            ))

        if not request.report_directed:
            commands.append(PlannedCommand(
                tool="nuclei",
                argv=(
                    tools.nuclei,
                    "-u",
                    target,
                    "-jsonl",
                    "-o",
                    os.path.join(output_dir, f"nuclei-{index}.jsonl"),
                    "-rate-limit",
                    "25",
                    "-c",
                    "5",
                    "-bulk-size",
                    "5",
                    "-no-color",
                    "-silent",
                ),
                purpose="template-based vulnerability and exposure checks",
            ))

    if request.report_directed:
        for index, verification in enumerate(request.verifications):
            if verification.tool == "nuclei":
                commands.append(PlannedCommand(
                    tool="nuclei",
                    argv=(
                        tools.nuclei,
                        "-u",
                        verification.url,
                        "-t",
                        verification.selector,
                        "-jsonl",
                        "-o",
                        os.path.join(output_dir, f"nuclei-verify-{index}.jsonl"),
                        "-rate-limit",
                        "10",
                        "-c",
                        "2",
                        "-no-color",
                        "-silent",
                    ),
                    purpose="report-directed Nuclei verification",
                ))
            elif (
                verification.tool == "xray"
                and enable_xray
                and tools.chaitin_xray
            ):
                commands.append(PlannedCommand(
                    tool="chaitin-xray",
                    argv=(
                        tools.chaitin_xray,
                        "webscan",
                        "--plugins",
                        verification.selector,
                        "--url",
                        verification.url,
                        "--json-output",
                        os.path.join(output_dir, f"xray-verify-{index}.json"),
                    ),
                    purpose="report-directed Xray verification",
                    risk="bounded-active",
                ))
        return tuple(commands)

    if enable_xray and tools.chaitin_xray:
        for index, target in enumerate(request.external_targets):
            target_host = _host(target).lower()
            target_port = _target_port(target)
            has_matching_web_service = any(
                service_host.lower() == target_host
                and protocol.lower() in {"http", "https", "ssl/http"}
                and (target_port is None or service_port == target_port)
                for service_host, service_port, protocol in open_services
            )
            if not has_matching_web_service:
                continue
            commands.append(PlannedCommand(
                tool="chaitin-xray",
                argv=(
                    tools.chaitin_xray,
                    "webscan",
                    "--basic-crawler",
                    target,
                    "--json-output",
                    os.path.join(output_dir, f"xray-{index}.json"),
                ),
                purpose="additional Web vulnerability checks",
                risk="bounded-active",
            ))

    return tuple(commands)
