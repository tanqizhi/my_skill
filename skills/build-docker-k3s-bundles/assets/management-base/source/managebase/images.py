"""Read local image inventory and container references without changing Docker."""

import re

from .compose import docker_command, records_from_json, text_field
from .layout import Installation
from .model import ManagementError
from .runner import run_readonly


CONTAINER_FORMAT = (
    '{"ID":{{json .Id}},"ImageID":{{json .Image}},'
    '"Name":{{json .Name}},"State":{{json .State.Status}}}'
)


def command(installation: Installation) -> list[str]:
    return docker_command(installation) + ["image", "ls", "--all", "--no-trunc",
                                            "--format", "{{json .}}"]


def inventory(installation: Installation) -> list[dict]:
    from .image_import import imported_at

    output = run_readonly(command(installation), installation.root)
    try:
        rows, seen = [], set()
        for item in records_from_json(output):
            identity = text_field(item, "ID")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
                raise ValueError
            repository = text_field(item, "Repository", 1024)
            tag = text_field(item, "Tag")
            key = (repository, tag, identity)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "repository": repository, "tag": tag, "id": identity,
                "size": text_field(item, "Size"),
                # Image creation/tag timestamps do not establish a local import time.
                "imported_at": None, "import_time_source": "unrecorded",
                "in_use": False, "container_count": 0, "containers": [],
            })
        if not rows:
            return []
        ids_output = run_readonly(
            docker_command(installation) + ["ps", "--all", "--quiet", "--no-trunc"],
            installation.root)
        ids = list(dict.fromkeys(ids_output.decode("utf-8").split()))
        if not all(re.fullmatch(r"[0-9a-f]{64}", identity) for identity in ids):
            raise ValueError
        inspected, usage = set(), {}
        for start in range(0, len(ids), 64):
            batch = ids[start:start + 64]
            output = run_readonly(
                docker_command(installation) + ["inspect", "--type", "container",
                                                "--format", CONTAINER_FORMAT, *batch],
                installation.root)
            for item in records_from_json(output):
                identity = text_field(item, "ID")
                image_id = text_field(item, "ImageID")
                if identity not in batch or identity in inspected:
                    raise ValueError
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                    raise ValueError
                inspected.add(identity)
                usage.setdefault(image_id, []).append({
                    "id": identity,
                    "name": text_field(item, "Name").removeprefix("/"),
                    "state": text_field(item, "State"),
                })
        if inspected != set(ids):
            raise ValueError
        for row in rows:
            containers = sorted(usage.get(row["id"], []), key=lambda item: (item["name"], item["id"]))
            row.update(in_use=bool(containers), container_count=len(containers), containers=containers)
            timestamp = imported_at(installation, row["id"])
            if timestamp:
                row.update(imported_at=timestamp, import_time_source="management-import")
        return sorted(rows, key=lambda row: (row["repository"], row["tag"], row["id"]))
    except (ValueError, UnicodeError, RecursionError):
        raise ManagementError("镜像查询输出格式不受支持，未显示原始内容。", 5) from None
