"""Project file metadata and persistent mount locations, without config disclosure."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from . import compose
from .layout import COMPOSE_FILES, Installation
from .model import ManagementError
from .runner import run_readonly


def iso_time(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def file_metadata(installation: Installation) -> list[dict]:
    files = []
    for relative in COMPOSE_FILES:
        path = installation.root / relative
        try:
            metadata = path.stat()
        except OSError:
            raise ManagementError(f"无法读取 Compose 文件信息：{relative}") from None
        created = getattr(metadata, "st_birthtime", None)
        if created is None:
            try:
                seconds = int(run_readonly(
                    ["stat", "--format=%W", "--", str(path)], installation.root,
                    timeout=5, max_output=1024).strip())
                created = seconds if seconds > 0 else None
            except (ManagementError, ValueError):
                created = None
        # ctime is metadata change time, not file creation time.
        files.append({"path": str(path), "modified_at": iso_time(metadata.st_mtime),
                      "created_at": iso_time(created) if created is not None else None})
    return files


def locations(installation: Installation) -> list[dict]:
    try:
        config = json.loads(run_readonly(compose.command(installation, "locations"),
                                        installation.root))
        if not isinstance(config, dict) or not isinstance(config.get("services", {}), dict):
            raise ValueError
        configured = config.get("services", {})
        volumes = config.get("volumes", {})
        if not isinstance(volumes, dict):
            raise ValueError
        for name, service in configured.items():
            if not isinstance(name, str) or not isinstance(service, dict):
                raise ValueError
        records = compose.records_from_json(run_readonly(
            compose.command(installation, "status"), installation.root))
        containers = {}
        for item in records:
            identity = compose.text_field(item, "ID")
            service = compose.text_field(item, "Service")
            if not re.fullmatch(r"[0-9a-f]{64}", identity) or not service:
                raise ValueError
            containers[identity] = service
        actual, inspected = {}, set()
        ids = list(containers)
        for start in range(0, len(ids), 64):
            batch = ids[start:start + 64]
            output = run_readonly(
                compose.docker_command(installation) + [
                    "inspect", "--type", "container", "--format",
                    '{"ID":{{json .Id}},"Mounts":{{json .Mounts}}}', *batch],
                installation.root)
            for item in compose.records_from_json(output):
                identity = compose.text_field(item, "ID")
                mounts = item.get("Mounts")
                if identity not in batch or identity in inspected or not isinstance(mounts, list):
                    raise ValueError
                inspected.add(identity)
                actual.setdefault(containers[identity], []).extend(mounts)
        if inspected != set(ids):
            raise ValueError
        files = file_metadata(installation)
        resolved_volumes = {}

        def volume_source(name):
            if name not in resolved_volumes:
                try:
                    output = run_readonly(
                        compose.docker_command(installation) + [
                            "volume", "inspect", "--format", "{{json .Mountpoint}}", name],
                        installation.root)
                    path = json.loads(output)
                    if not isinstance(path, str) or not path.startswith("/"):
                        raise ValueError
                    resolved_volumes[name] = path
                except (ManagementError, ValueError):
                    resolved_volumes[name] = f"Docker 卷 {name}（宿主机路径未解析）"
            return resolved_volumes[name]

        result = []
        for service in sorted(set(configured) | set(actual)):
            mounted = service in actual
            mounts = actual[service] if mounted else configured[service].get("volumes", [])
            if not isinstance(mounts, list):
                raise ValueError
            directories, mounted_files = set(), set()
            for mount in mounts:
                if not isinstance(mount, dict):
                    raise ValueError
                kind = compose.text_field(mount, "Type" if mounted else "type")
                source = compose.text_field(mount, "Source" if mounted else "source", 4096)
                if kind in ("tmpfs", "image"):
                    continue
                if kind not in ("bind", "volume"):
                    raise ValueError
                if kind == "volume" and not mounted:
                    if not source:
                        directories.add("匿名卷（容器创建后确定）")
                        continue
                    definition = volumes.get(source, {})
                    if not isinstance(definition, dict):
                        raise ValueError
                    name = compose.text_field(definition, "name") or f"{installation.project}_{source}"
                    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
                        raise ValueError
                    directories.add(volume_source(name))
                    continue
                if not source.startswith("/"):
                    raise ValueError
                if kind == "bind" and Path(source).is_file():
                    mounted_files.add(source)
                else:
                    directories.add(source)
            result.append({
                "service": service, "compose_files": files if service in configured else [],
                "persistent_directories": sorted(directories), "file_mounts": sorted(mounted_files),
                "mount_source": "actual-containers" if mounted else "compose-config",
            })
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise ManagementError("容器位置查询输出格式不受支持，未显示原始配置。", 5) from None
