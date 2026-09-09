"""Read DOCKER-USER from IPv4/IPv6 filter snapshots; never reset counters."""

import re
import shlex
import shutil

from .layout import Installation
from .model import ManagementError
from .runner import run_readonly


CHAIN = "DOCKER-USER"
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
SELECTORS = {
    "-p": "protocol", "--protocol": "protocol",
    "-s": "source_ip", "--source": "source_ip", "--src-range": "source_ip",
    "-d": "destination_ip", "--destination": "destination_ip", "--dst-range": "destination_ip",
    "--sport": "source_port", "--source-port": "source_port",
    "--sports": "source_port", "--source-ports": "source_port",
    "--dport": "destination_port", "--destination-port": "destination_port",
    "--dports": "destination_port", "--destination-ports": "destination_port",
    "-i": "input_interface", "--in-interface": "input_interface",
    "-o": "output_interface", "--out-interface": "output_interface",
}


def commands() -> dict[str, list[str] | None]:
    return {
        family: [binary, "-c", "-t", "filter"] if
        (binary := shutil.which(program, path=SAFE_PATH)) else None
        for family, program in (("IPv4", "iptables-save"), ("IPv6", "ip6tables-save"))
    }


def parse_rule(line: str, family: str, number: int) -> dict:
    counters = re.match(r"^\[(\d+):(\d+)\]\s+", line)
    body = line[counters.end():] if counters else line
    tokens = shlex.split(body)
    if tokens[:2] != ["-A", CHAIN]:
        raise ValueError
    fields = {key: [] for key in set(SELECTORS.values())}
    extra, action = [], "CONTINUE"
    index = 2
    while index < len(tokens):
        inverted = tokens[index] == "!"
        if inverted:
            index += 1
        if index >= len(tokens):
            raise ValueError
        option = tokens[index]
        index += 1
        if option in ("-j", "--jump", "-g", "--goto"):
            if inverted or index >= len(tokens):
                raise ValueError
            action = ("GOTO " if option in ("-g", "--goto") else "") + tokens[index]
            extra.extend(tokens[index + 1:])
            break
        if option in SELECTORS or option in ("-m", "--match", "--comment"):
            if option in SELECTORS and index < len(tokens) and tokens[index] == "!":
                inverted = not inverted
                index += 1
            if index >= len(tokens):
                raise ValueError
            value = tokens[index]
            index += 1
            if option in SELECTORS:
                fields[SELECTORS[option]].append(("! " if inverted else "") + value)
            else:
                extra.extend((["!"] if inverted else []) + [option, value])
        else:
            extra.extend((["!"] if inverted else []) + [option])
    row = {key: " & ".join(values) if values else "未限定" for key, values in fields.items()}
    if row["protocol"] == "未限定":
        row["protocol"] = "all"
    return {
        **row, "family": family, "chain": CHAIN, "number": number,
        "packets": int(counters[1]) if counters else None,
        "bytes": int(counters[2]) if counters else None,
        "action": action, "extra_matches": shlex.join(extra), "raw_rule": line,
    }


def parse_snapshot(output: bytes, family: str) -> dict:
    inside, declared, finished = False, False, False
    rules = []
    for line in output.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("*"):
            if inside or finished or line != "*filter":
                raise ValueError
            inside = True
            continue
        if line == "COMMIT":
            if not inside:
                raise ValueError
            finished = True
            inside = False
            continue
        if not inside:
            raise ValueError
        if line.startswith(f":{CHAIN} "):
            if declared or not re.fullmatch(r":DOCKER-USER - \[\d+:\d+\]", line):
                raise ValueError
            declared = True
        if not (line.startswith(":") or re.match(r"^(?:\[\d+:\d+\]\s+)?-A \S+(?:\s|$)", line)):
            raise ValueError
        if re.match(r"^(?:\[\d+:\d+\]\s+)?-A DOCKER-USER(?:\s|$)", line):
            rules.append(parse_rule(line, family, len(rules) + 1))
    if inside or (rules and not declared) or (declared and not finished):
        raise ValueError
    return {"family": family, "chain": CHAIN, "status": "present" if declared else "missing",
            "rules": rules, "message": "" if declared else "当前 iptables 视图中链不存在"}


def inspect_chain(installation: Installation) -> dict:
    chains = []
    for family, argv in commands().items():
        if argv is None:
            chains.append({"family": family, "chain": CHAIN, "status": "unavailable", "rules": [],
                           "message": "查询工具未安装"})
            continue
        try:
            snapshot = run_readonly(argv, installation.root, max_output=4 * 1024 * 1024)
            chain = parse_snapshot(snapshot, family)
        except ManagementError:
            chain = {"family": family, "chain": CHAIN, "status": "unavailable", "rules": [],
                     "message": "读取失败，请检查权限和防火墙后端；未判定为空链"}
        except (ValueError, UnicodeError, RecursionError):
            chain = {"family": family, "chain": CHAIN, "status": "unavailable", "rules": [],
                     "message": "规则格式无法解析；未判定为空链"}
        chains.append(chain)
    return {"chains": chains, "complete": all(chain["status"] != "unavailable" for chain in chains)}
