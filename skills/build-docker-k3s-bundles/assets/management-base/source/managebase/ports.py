"""Read actual port publishing for containers owned by the selected project."""

import ipaddress
import re

from . import compose
from .layout import Installation
from .model import ManagementError
from .runner import run_readonly


INSPECT_FORMAT = (
    '{"ID":{{json .Id}},"Name":{{json .Name}},"Running":{{json .State.Running}},'
    '"State":{{json .State.Status}},"Mode":{{json .HostConfig.NetworkMode}},'
    '"Ports":{{json .NetworkSettings.Ports}}}'
)


def published(installation: Installation) -> list[dict]:
    try:
        records = compose.records_from_json(run_readonly(
            compose.command(installation, "status"), installation.root))
        containers = {}
        for record in records:
            identity = compose.text_field(record, "ID")
            service = compose.text_field(record, "Service")
            if not re.fullmatch(r"[0-9a-f]{64}", identity) or not service or identity in containers:
                raise ValueError
            containers[identity] = service
        rows, inspected = [], set()
        ids = list(containers)
        for start in range(0, len(ids), 64):
            batch = ids[start:start + 64]
            output = run_readonly(
                compose.docker_command(installation) + [
                    "inspect", "--type", "container", "--format", INSPECT_FORMAT, *batch],
                installation.root)
            for item in compose.records_from_json(output):
                identity = compose.text_field(item, "ID")
                if identity not in batch or identity in inspected or type(item.get("Running")) is not bool:
                    raise ValueError
                inspected.add(identity)
                base = {
                    "service": containers[identity], "container_id": identity,
                    "container": compose.text_field(item, "Name").removeprefix("/"),
                    "state": compose.text_field(item, "State"),
                    "network_mode": compose.text_field(item, "Mode"),
                }
                ports = {} if item.get("Ports") is None else item["Ports"]
                if not isinstance(ports, dict):
                    raise ValueError
                published_rows = []
                if item["Running"] and base["network_mode"] != "host":
                    for target, bindings in ports.items():
                        match = re.fullmatch(r"([0-9]{1,5})/(tcp|udp|sctp)", target)
                        if not match or not 1 <= int(match[1]) <= 65535:
                            raise ValueError
                        if bindings is None:
                            continue
                        if not isinstance(bindings, list):
                            raise ValueError
                        for binding in bindings:
                            if not isinstance(binding, dict):
                                raise ValueError
                            address = compose.text_field(binding, "HostIp")
                            if address:
                                ipaddress.ip_address(address)
                            port = compose.text_field(binding, "HostPort")
                            if port and (not port.isascii() or not port.isdecimal()
                                         or not 1 <= int(port) <= 65535):
                                raise ValueError
                            published_rows.append({
                                **base, "listen_ip": address or None,
                                "host_port": int(port) if port else None,
                                "container_port": int(match[1]), "protocol": match[2],
                                "publishing_status": "已发布映射" if port else "无宿主机端口映射",
                            })
                if published_rows:
                    rows.extend(published_rows)
                else:
                    status = "未发布端口"
                    if not item["Running"]:
                        status = "容器未运行"
                    elif base["network_mode"] == "host":
                        status = "host 网络（共享主机端口）"
                    rows.append({**base, "listen_ip": None, "host_port": None,
                                 "container_port": None, "protocol": None,
                                 "publishing_status": status})
        if inspected != set(ids):
            raise ValueError
        return sorted(rows, key=lambda row: (row["service"], row["container"],
                      row["protocol"] or "", row["listen_ip"] or "", row["host_port"] or 0))
    except (ValueError, UnicodeError, RecursionError):
        raise ManagementError("端口映射输出格式不受支持，未显示原始内容。", 5) from None
