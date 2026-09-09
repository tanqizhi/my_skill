"""Service-selected tar.gz backups. Never stop services or follow data symlinks."""

from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import time

from . import compose, config_io, locations
from .layout import COMPOSE_FILES, ENV_FILES
from .lifecycle import instance_lock
from .model import ManagementError, Result

COMMANDS = {"backup-compose": "备份 Compose 文件", "backup-data": "备份数据文件"}


@dataclass(frozen=True)
class Plan:
    installation: object
    kind: str
    services: tuple
    sources: tuple
    inputs: dict
    operation_id: str

    def default_path(self):
        scope = self.services[0] if len(self.services) == 1 else "all"
        return self.installation.root / "backups" / self.operation_id / f"{self.kind}-{scope}.tar.gz"

    def summary(self):
        return {"kind": self.kind, "selected_services": list(self.services),
                "sources": [str(p) for p in self.sources],
                "path": str(self.default_path()), "format": "tar.gz",
                "consistency": "完整共享 Compose 原文件" if self.kind == "backup-compose"
                               else "在线文件快照，不保证数据库事务一致性；需要一致性时请先停止服务"}


def service_list(installation):
    return sorted(compose.configuration(installation)["services"])


def prepare(installation, kind, *, service=None, all_services=False):
    if kind not in COMMANDS or bool(service) == bool(all_services):
        raise ManagementError("请选择一个服务或明确选择我全都要。", 2)
    inputs = config_io.snapshot(installation)
    known = service_list(installation)
    selected = known if all_services else [service]
    if not selected or any(name not in known for name in selected):
        raise ManagementError("当前实例中没有所选服务。", 2)
    sources = set()
    if kind == "backup-compose":
        sources.update(installation.root / path for path in (*COMPOSE_FILES, *ENV_FILES))
    else:
        data_root = installation.root / "data"
        if data_root.resolve() != data_root:
            raise ManagementError("固定 data 目录不能通过符号链接指向其他位置。", 4)
        other_roots = [installation.root / path for path in ("config", "secrets", "logs")]
        for name in selected:
            path = data_root / name
            if path.exists() or path.is_symlink():
                sources.add(path)
        for row in locations.locations(installation):
            if row["service"] not in selected:
                continue
            for value in row["persistent_directories"] + row["file_mounts"]:
                path = Path(value)
                if not path.is_absolute():
                    raise ManagementError("存在未解析的持久化卷，不能宣称已完整备份该服务。", 4)
                if path.is_relative_to(data_root) and path != data_root:
                    sources.add(path)
                elif not any(path.is_relative_to(parent) for parent in other_roots):
                    raise ManagementError("发现固定 data 目录之外的持久化挂载，请单独确认其备份策略。", 4)
        for path in sources:
            if path.is_symlink() or not path.resolve().is_relative_to(data_root.resolve()):
                raise ManagementError("数据来源包含符号链接逃逸或不属于固定 data 目录。", 4)
            if not path.exists():
                raise ManagementError("数据来源不存在，未跳过该路径或生成不完整备份。", 4)
        sources = {path for path in sources if not any(
            path != parent and path.is_relative_to(parent) for parent in sources)}
    config_io.unchanged(installation, inputs)
    return Plan(installation, kind, tuple(selected), tuple(sorted(sources)), inputs,
                config_io.operation_id(kind))


def destination(plan, requested):
    path = Path(requested) if requested is not None else plan.default_path()
    if not path.is_absolute():
        raise ManagementError("备份路径必须为完整绝对路径。", 2)
    if path.is_dir():
        path = path / plan.default_path().name
    if not str(path).endswith(".tar.gz"):
        path = Path(str(path) + ".tar.gz")
    if path.exists() or path.is_symlink():
        raise ManagementError("备份文件已存在，不能覆盖，请更换路径。", 4)
    parent = path.parent.resolve()
    for protected in (Path("/proc"), Path("/sys"), Path("/dev"),
                      *(plan.installation.root / name for name in
                        ("data", "config", "deploy", "secrets", "state", "runtime", "logs"))):
        if parent.is_relative_to(protected.resolve()):
            raise ManagementError("备份文件不能写入运行数据、配置、运行时或系统虚拟文件目录。", 4)
    for source in plan.sources:
        if parent.is_relative_to(source.resolve()):
            raise ManagementError("备份文件不能位于正在备份的数据目录中。", 4)
    return parent / path.name


def file_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


class CopyProgress:
    def __init__(self, stream, progress, label):
        self.stream, self.progress, self.label = stream, progress, label
        self.total, self.last = 0, time.monotonic()

    def read(self, size=-1):
        data = self.stream.read(size)
        self.total += len(data)
        if self.progress and time.monotonic() - self.last >= 0.5:
            self.progress(f"{self.label}：已读取 {self.total // (1024 * 1024)} MiB", False)
            self.last = time.monotonic()
        return data


def add_data(archive, root, path, tracked, progress):
    before = path.lstat()
    tracked[path] = file_identity(before)
    relative = path.relative_to(root).as_posix()
    info = archive.gettarinfo(str(path), arcname=relative)
    if progress:
        progress(f"打包：{relative}", False)
    if stat.S_ISDIR(before.st_mode):
        archive.addfile(info)
        for child in sorted(path.iterdir()):
            add_data(archive, root, child, tracked, progress)
    elif stat.S_ISLNK(before.st_mode) or info.islnk():
        archive.addfile(info)
    elif stat.S_ISREG(before.st_mode):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if file_identity(os.fstat(stream.fileno())) != tracked[path]:
                raise ManagementError("备份期间文件发生变化，请停止写入后重试。", 5)
            archive.addfile(info, CopyProgress(stream, progress, relative))
            if file_identity(os.fstat(stream.fileno())) != tracked[path]:
                raise ManagementError("备份期间文件发生变化，请停止写入后重试。", 5)
    else:
        raise ManagementError("数据目录含设备、管道或套接字，未生成不完整备份；请先处理该特殊文件。", 5)


def add_bytes(archive, name, content):
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(content), 0o600
    archive.addfile(info, io.BytesIO(content))


def apply(plan, requested=None, *, confirmed=False, progress=None):
    if not confirmed:
        return Result("未确认，未生成备份。", 2)
    temporary = None
    try:
        with instance_lock(plan.installation.root):
            config_io.unchanged(plan.installation, plan.inputs)
            current = prepare(plan.installation, plan.kind,
                              service=plan.services[0] if len(plan.services) == 1 else None,
                              all_services=len(plan.services) != 1)
            if current.services != plan.services or current.sources != plan.sources:
                raise ManagementError("备份服务或数据来源已变化，请重新选择。", 4)
            if not plan.sources:
                return Result("所选服务不涉及持久化数据文件，无需生成备份。")
            target = destination(plan, requested)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=".backup-", suffix=".partial", dir=target.parent)
            temporary = Path(name)
            tracked = {}
            with os.fdopen(descriptor, "wb") as output:
                if stat.S_IMODE(os.fstat(output.fileno()).st_mode) != 0o600:
                    raise ManagementError("备份输出文件系统不支持私有权限，请选择 Linux 文件系统目录。", 4)
                with tarfile.open(fileobj=output, mode="w:gz", dereference=False) as archive:
                    if plan.kind == "backup-compose":
                        for relative in (*COMPOSE_FILES, *ENV_FILES):
                            add_bytes(archive, relative, plan.inputs[relative])
                        add_bytes(archive, "state/installation.json", plan.inputs["state/installation.json"])
                    else:
                        for path in plan.sources:
                            add_data(archive, plan.installation.root, path, tracked, progress)
                    metadata = {**plan.summary(), "operation_id": plan.operation_id,
                                "output": str(target), "symlinks_followed": False,
                                "database_consistent": False if plan.kind == "backup-data" else None}
                    add_bytes(archive, "backup-manifest.json",
                              json.dumps(metadata, ensure_ascii=False, indent=2).encode())
                output.flush()
                os.fsync(output.fileno())
            for path, identity in tracked.items():
                if file_identity(path.lstat()) != identity:
                    raise ManagementError("备份期间数据或目录发生变化，未发布备份，请停止写入后重试。", 5)
            config_io.unchanged(plan.installation, plan.inputs)
            # Publish without replacing any file another process may have created.
            os.link(temporary, target)
            size = target.stat().st_size
            if progress:
                progress(f"备份完成：{target}", False)
            return Result("备份完成，已自动打包为 tar.gz。" +
                          (" 在线文件快照不保证数据库事务一致性。" if plan.kind == "backup-data" else
                           " Compose 为共享文件，已原样保留完整文件。"),
                          data={"path": str(target), "bytes": size, "selected_services": list(plan.services)})
    except (ManagementError, OSError, tarfile.TarError, ValueError, RecursionError) as error:
        message = str(error) if isinstance(error, ManagementError) else "备份读写失败，请检查权限、空间和文件是否变化。"
        return Result(message, error.code if isinstance(error, ManagementError) else 5)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
