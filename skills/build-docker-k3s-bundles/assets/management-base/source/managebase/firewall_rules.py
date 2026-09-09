"""Add one explicitly confirmed rule to the existing host DOCKER-USER chain."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat

from . import config_io, firewall
from .layout import Installation
from .lifecycle import instance_lock
from .model import ManagementError, Result
from .runner import run_command, run_readonly

COMMAND = "firewall-add"
HOST_LOCK = Path("/run/lock/managebase-docker-firewall.lock")


def port(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}(?::[0-9]{1,5})?", value):
        raise ManagementError("端口须为 0–65535 的数字或起始:结束范围；留空表示任意。", 2)
    numbers = [int(part) for part in value.split(":")]
    if any(number > 65535 for number in numbers) or numbers[0] > numbers[-1]:
        raise ManagementError("端口范围无效，起始值不能大于结束值。", 2)
    return ":".join(str(number) for number in numbers)


@dataclass(frozen=True)
class Rule:
    position: int
    protocol: str
    source: str
    source_port: str
    destination: str
    destination_port: str
    action: str
    family: int

    @classmethod
    def parse(cls, *, position, protocol, source="", source_port="",
              destination="", destination_port="", action):
        if isinstance(position, str) and re.fullmatch(r"-1|[1-9][0-9]{0,8}", position):
            position = int(position)
        if type(position) is not int or position < -1 or position == 0 or position > 999999999:
            raise ManagementError("行号必须是从 1 开始的正整数，或 -1（最后一行）。", 2)
        if protocol not in ("IP", "tcp", "udp", "icmp"):
            raise ManagementError("协议仅支持 IP、tcp、udp、icmp；IP 表示所有协议。", 2)
        if action not in ("ACCEPT", "REJECT"):
            raise ManagementError("动作仅支持通过（ACCEPT）或拒绝（REJECT）。", 2)
        networks = []
        for value in (source, destination):
            if value in ("", None):
                networks.append(None)
                continue
            try:
                if not isinstance(value, str) or "%" in value:
                    raise ValueError
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                raise ManagementError("地址须为有效 IP 或 CIDR；不接受域名、多个地址或作用域后缀。", 2) from None
        families = {network.version for network in networks if network is not None}
        if len(families) > 1:
            raise ManagementError("源地址与目标地址不能混用 IPv4 和 IPv6。", 2)
        family = next(iter(families), 4)
        any_address = "0.0.0.0/0" if family == 4 else "::/0"
        source_port, destination_port = port(source_port), port(destination_port)
        if protocol in ("IP", "icmp") and (source_port or destination_port):
            raise ManagementError("IP 和 icmp 不接受端口条件。", 2)
        return cls(position, protocol, str(networks[0]) if networks[0] is not None else any_address,
                   source_port, str(networks[1]) if networks[1] is not None else any_address,
                   destination_port, action, family)

    def specification(self, marker):
        args = ["-s", self.source, "-d", self.destination]
        if self.protocol != "IP":
            protocol = "ipv6-icmp" if self.protocol == "icmp" and self.family == 6 else self.protocol
            args += ["-p", protocol]
        if self.protocol in ("tcp", "udp"):
            args += ["-m", self.protocol]
            if self.source_port:
                args += ["--sport", self.source_port]
            if self.destination_port:
                args += ["--dport", self.destination_port]
        return args + ["-m", "comment", "--comment", marker, "-j", self.action]

    def summary(self):
        return {**self.__dict__, "chain": firewall.CHAIN, "table": "filter",
                "scope": "host-wide Docker forwarding; post-DNAT addresses and ports",
                "persistence": "runtime-only"}


def binary_for(family):
    binary = shutil.which("iptables" if family == 4 else "ip6tables", path=firewall.SAFE_PATH)
    if binary is None:
        raise ManagementError("目标地址族的 iptables 工具未安装；未安装或切换防火墙后端。", 4)
    return binary


def base(binary):
    return [binary, "-w", "5", "-t", "filter"]


def read(argv, root):
    try:
        return run_readonly(argv, root, timeout=15, max_output=4 * 1024 * 1024)
    except ManagementError as error:
        raise ManagementError(str(error).replace("Docker", "防火墙"), error.code) from None


def snapshot(binary, root):
    raw = read(base(binary) + ["-S", firewall.CHAIN], root)
    try:
        rules, declared = [], False
        for line in raw.decode("utf-8").splitlines():
            tokens = shlex.split(line)
            if tokens == ["-N", firewall.CHAIN] and not declared:
                declared = True
            elif tokens[:2] == ["-A", firewall.CHAIN]:
                rules.append(tuple(tokens))
            else:
                raise ValueError
        if not declared:
            raise ValueError
        return tuple(rules)
    except (ValueError, UnicodeError):
        raise ManagementError("DOCKER-USER 链不存在或规则格式无法识别；不会创建链。", 4) from None


@dataclass(frozen=True)
class Plan:
    installation: Installation
    rule: Rule
    binary: str
    version: bytes
    before: tuple
    operation_id: str

    @property
    def marker(self):
        return "managebase:" + self.operation_id

    def argv(self, action):
        args = base(self.binary) + [action, firewall.CHAIN]
        if action == "-I":
            args += [str(self.rule.position)]
        return args + self.rule.specification(self.marker)

    def summary(self):
        return {**self.rule.summary(), "existing_rules": len(self.before),
                "effective_position": len(self.before) + 1 if self.rule.position == -1 else self.rule.position,
                "argv": self.argv("-A" if self.rule.position == -1 else "-I"),
                "warning": "主机级规则，可能影响其他项目；匹配 DNAT 后地址/端口。"
                           "前置 ACCEPT/REJECT/DROP/RETURN 可能使新规则无法命中；不自动持久化。"}


def prepare(installation, rule):
    binary = binary_for(rule.family)
    version = read([binary, "--version"], installation.root)
    before = snapshot(binary, installation.root)
    if rule.position != -1 and rule.position > len(before) + 1:
        raise ManagementError(f"行号超出范围：当前 {len(before)} 条规则，可填写 1–{len(before) + 1} 或 -1。", 2)
    return Plan(installation, rule, binary, version, before, config_io.operation_id("firewall-add"))


@contextmanager
def host_lock():
    descriptor = -1
    try:
        descriptor = os.open(HOST_LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise ManagementError("主机防火墙管理锁的类型或所有者无效。", 4)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ManagementError("其他管理实例正在修改主机防火墙，请稍后重试。", 4) from None
        yield
    except OSError:
        raise ManagementError("无法获取主机防火墙锁，请检查 /run/lock 权限。", 4) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def owned(rules, marker):
    return [index for index, tokens in enumerate(rules)
            if any(tokens[i:i + 2] == ("--comment", marker) for i in range(len(tokens) - 1))]


def apply(plan, *, confirmed=False, progress=None):
    if not confirmed:
        return Result("未确认，未修改防火墙。", 2)
    backup, attempted = None, False
    record = {"operation_id": plan.operation_id, **plan.summary()}
    root = plan.installation.root
    try:
        with instance_lock(root), host_lock():
            if Installation.load(root) != plan.installation or binary_for(plan.rule.family) != plan.binary:
                raise ManagementError("安装记录或防火墙工具已变化，请重新确认。", 4)
            if read([plan.binary, "--version"], root) != plan.version or snapshot(plan.binary, root) != plan.before:
                raise ManagementError("防火墙后端或规则顺序已变化，请重新填写行号并确认。", 4)
            try:
                backup = config_io.private_directory(root, "backups/" + plan.operation_id)
                config_io.write_private(backup / "before.json",
                                        json.dumps(plan.before, ensure_ascii=False, indent=2).encode())
                config_io.write_private(backup / "plan.json", json.dumps(record, ensure_ascii=False).encode())
                recovery = ("仅撤销本次新增规则；先确认唯一 comment 及现场规则，不整体恢复主机防火墙。\n"
                            + shlex.join(plan.argv("-D")) + "\n")
                config_io.write_private(backup / "recovery.txt", recovery.encode())
            except OSError:
                raise ManagementError("防火墙规则备份失败，未添加规则。", 5) from None
            if snapshot(plan.binary, root) != plan.before:
                raise ManagementError("备份期间规则已变化，未添加规则，请重新确认。", 4)
            try:
                attempted = True
                if progress:
                    progress("规则快照及撤销命令已保存，正在添加一条 DOCKER-USER 规则…", False)
                run_command(plan.argv("-A" if plan.rule.position == -1 else "-I"), root,
                            timeout=15, tick=(lambda: progress("正在等待防火墙命令…", True)) if progress else None)
                after = snapshot(plan.binary, root)
                selected = owned(after, plan.marker)
                expected = len(plan.before) if plan.rule.position == -1 else plan.rule.position - 1
                if selected != [expected] or tuple(row for i, row in enumerate(after) if i not in selected) != plan.before:
                    raise ManagementError("添加后规则顺序或其他规则发生变化，不能确认执行结果。", 5)
                read(plan.argv("-C"), root)
                record["status"] = "complete"
                config_io.write_private(backup / "result.json", json.dumps(record, ensure_ascii=False).encode())
                return Result("防火墙规则已添加并核对；仅当前运行时生效，未设置重启恢复。",
                              data={"backup": str(backup), **plan.summary()})
            except (ManagementError, OSError, KeyboardInterrupt) as error:
                record["status"] = "failed"
                try:
                    current = snapshot(plan.binary, root)
                    matches = owned(current, plan.marker)
                    if matches:
                        if len(matches) != 1:
                            raise ManagementError("标记不唯一，拒绝自动删除。", 5)
                        read(plan.argv("-C"), root)
                        run_command(plan.argv("-D"), root, timeout=15)
                    record["own_rule_absent"] = not owned(snapshot(plan.binary, root), plan.marker)
                except ManagementError:
                    record["recovery_incomplete"] = True
                record["message"] = (str(error).replace("Docker", "防火墙") if isinstance(error, ManagementError)
                                     else "用户中断了防火墙操作。" if isinstance(error, KeyboardInterrupt)
                                     else "结果记录失败。")
                try:
                    config_io.write_private(backup / "failure.json", json.dumps(record, ensure_ascii=False).encode())
                except (OSError, ManagementError):
                    pass
                suffix = (" 本次规则已撤销或未添加，其他规则未自动回退。" if record.get("own_rule_absent")
                          else " 规则状态不确定，请立即核对 DOCKER-USER 及备份中的撤销命令。")
                return Result(record["message"] + suffix, 130 if isinstance(error, KeyboardInterrupt) else 5,
                              {"backup": str(backup), "recovery": record})
    except (ManagementError, OSError) as error:
        message = str(error) if isinstance(error, ManagementError) else "防火墙备份或权限检查失败。"
        return Result(message, error.code if isinstance(error, ManagementError) else 5,
                      {"backup": str(backup) if backup else None, "attempted": attempted})
