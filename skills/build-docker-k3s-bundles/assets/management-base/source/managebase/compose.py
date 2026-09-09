import json
import re
from typing import Any

from .layout import COMPOSE_FILES, ENV_FILES, Installation
from .model import ManagementError
from .runner import run_readonly


def docker_command(installation: Installation) -> list[str]:
    args = [str(installation.docker_binary), "--host", "unix:///var/run/docker.sock"]
    if installation.docker_config:
        args += ["--config", str(installation.docker_config)]
    return args


def command(installation: Installation, action: str, *, override=None) -> list[str]:
    actions = {
        "status": ["ps", "--all", "--no-trunc", "--format", "json"],
        "config-check": ["config", "--quiet"],
        "locations": ["config", "--format", "json"],
        "up": ["up", "--detach", "--no-deps", "--no-build", "--pull", "never"],
        "create": ["up", "--no-start", "--no-deps", "--no-build", "--pull", "never"],
        "config-hash": ["config", "--hash"],
    }
    if action not in actions:
        raise ManagementError("未注册的 Compose 操作。", 2)
    args = docker_command(installation)
    args += ["compose", "--ansi", "never", "--project-name", installation.project,
            "--project-directory", str(installation.root)]
    for relative in ENV_FILES:
        args.extend(["--env-file", str(installation.root / relative)])
    for relative in COMPOSE_FILES:
        path = override if override is not None and relative == COMPOSE_FILES[1] else installation.root / relative
        args.extend(["--file", str(path)])
    for profile in installation.profiles:
        args.extend(["--profile", profile])
    return args + actions[action]


def configuration(installation, *, override=None):
    try:
        result = json.loads(run_readonly(command(installation, "locations", override=override),
                                        installation.root, max_output=4 * 1024 * 1024))
        if not isinstance(result, dict) or not isinstance(result.get("services"), dict):
            raise ValueError
        if any(not isinstance(name, str) or not isinstance(service, dict)
               for name, service in result["services"].items()):
            raise ValueError
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise ManagementError("Compose 配置解析失败，未显示可能含凭据的原始输出。", 5) from None


def records_from_json(data: bytes) -> list[dict]:
    text = data.decode("utf-8").strip()
    if not text:
        return []
    try:
        records: Any = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError
    return records


def text_field(item: dict, key: str, limit: int = 256) -> str:
    value = item.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError
    return "".join(char for char in value if char.isprintable())


# Only request display fields, never environment variables or health-check logs.
INSPECT_FORMAT = (
    '{"ID":{{json .Id}},"CreatedAt":{{json .Created}},'
    '"StartedAt":{{json .State.StartedAt}},"State":{{json .State.Status}},'
    '"Health":{{with index .State "Health"}}{{json .Status}}{{else}}""{{end}},'
    '"Image":{{json .Config.Image}},"ImageID":{{json .Image}},'
    '"RestartCount":{{json .RestartCount}}}'
)


def services(installation: Installation) -> list[dict[str, Any]]:
    data = run_readonly(command(installation, "status"), installation.root)
    try:
        records = records_from_json(data)
        selected = []
        for item in records:
            row: dict[str, Any] = {}
            for key in ("Service", "State", "Health"):
                row[key.lower()] = text_field(item, key)
            row.update({
                "container": text_field(item, "Name"),
                "id": text_field(item, "ID"),
                "image": text_field(item, "Image", 1024),
                "created_at": "", "started_at": "", "image_id": "",
                "restart_count": None,
            })
            if row["id"] and not re.fullmatch(r"[0-9a-f]{64}", row["id"]):
                raise ValueError
            selected.append(row)
        ids = list(dict.fromkeys(row["id"] for row in selected if row["id"]))
        details = {}
        for start in range(0, len(ids), 64):
            batch = ids[start:start + 64]
            output = run_readonly(
                docker_command(installation) + ["inspect", "--type", "container",
                                                "--format", INSPECT_FORMAT, *batch],
                installation.root)
            for item in records_from_json(output):
                identity = text_field(item, "ID")
                if identity not in batch or identity in details:
                    raise ValueError
                restart_count = item.get("RestartCount")
                if type(restart_count) is not int or restart_count < 0:
                    raise ValueError
                details[identity] = {
                    "created_at": text_field(item, "CreatedAt"),
                    "started_at": text_field(item, "StartedAt"),
                    "image": text_field(item, "Image", 1024),
                    "image_id": text_field(item, "ImageID"),
                    "state": text_field(item, "State"),
                    "health": text_field(item, "Health"),
                    "restart_count": restart_count,
                }
        if set(details) != set(ids):
            raise ValueError
        for row in selected:
            row.update(details.get(row["id"], {}))
        return sorted(selected, key=lambda row: (row["service"], row["container"], row["id"]))
    except (ValueError, UnicodeError, RecursionError):
        raise ManagementError("Compose 状态输出格式不受支持，未显示原始内容。", 5) from None
