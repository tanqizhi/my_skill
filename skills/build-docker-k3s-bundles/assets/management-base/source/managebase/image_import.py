"""Preview Docker-save archives and load only the explicitly selected image/tag."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
import time

from . import compose, images
from .layout import Installation, read_registered, unique_object
from .lifecycle import instance_lock
from .model import ManagementError, Result
from .runner import run_command, run_readonly

MAX_METADATA = 4 * 1024 * 1024
COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
HOST_PART = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?"
DOMAIN = rf"(?:{HOST_PART}(?:\.{HOST_PART})*|\[[a-fA-F0-9:]+\])(?::[0-9]+)?"


def reference(repository, tag):
    if (not isinstance(repository, str) or len(repository) > 255
            or not re.fullmatch(rf"(?:{DOMAIN}/)?{COMPONENT}(?:/{COMPONENT})*", repository)
            or re.fullmatch(r"[a-f0-9]{64}", repository)):
        raise ManagementError("镜像名称无效：使用小写仓库路径，不含 tag、空格或协议前缀。", 2)
    if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ManagementError("tag 无效：1 到 128 个字母、数字、下划线、点或短横线，不能以点或短横线开头。", 2)
    return f"{repository}:{tag}"


def split_reference(value):
    if not isinstance(value, str) or "@" in value:
        raise ManagementError("归档中的镜像标签格式无效。", 3)
    head, separator, tail = value.rpartition(":")
    repository, tag = (head, tail) if separator and "/" not in tail else (value, "latest")
    reference(repository, tag)
    return repository, tag


def canonical(value):
    repository, tag = split_reference(value)
    first, slash, rest = repository.partition("/")
    if not slash or ("." not in first and ":" not in first and first != "localhost"
                     and first == first.lower()):
        repository = "docker.io/" + repository
    if repository.startswith("index.docker.io/"):
        repository = "docker.io/" + repository[len("index.docker.io/"):]
    if repository.startswith("docker.io/") and repository.count("/") == 1:
        repository = "docker.io/library/" + repository[len("docker.io/"):]
    return f"{repository}:{tag}"


def human_size(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024


@dataclass(frozen=True)
class ArchiveImage:
    config: str
    layers: tuple[str, ...]
    identity: str
    repository: str
    tag: str
    size: int
    platform: str


@dataclass(frozen=True)
class Archive:
    path: Path
    fingerprint: tuple
    images: tuple[ArchiveImage, ...]
    content_sha256: str


def fingerprint(stream):
    value = os.fstat(stream.fileno())
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def content_hash(stream, progress=None):
    """Timestamps may collide on fast rewrites or coarse-resolution filesystems."""
    position = stream.tell()
    stream.seek(0)
    digest = hashlib.sha256()
    done = 0
    last_update = 0.0
    try:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            now = time.monotonic()
            if progress and now - last_update >= 0.15:
                progress(f"校验归档内容：{human_size(done)}", False)
                last_update = now
        return digest.hexdigest()
    finally:
        stream.seek(position)


@contextmanager
def archive_file(path):
    if not path.is_absolute():
        raise ManagementError("请输入镜像归档文件的完整绝对路径。", 2)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ManagementError("镜像归档必须是普通文件，不能是目录、管道或设备。", 2)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            yield stream
    except (OSError, ValueError):
        raise ManagementError("无法读取镜像归档，请检查完整路径、权限及文件是否变化。", 3) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def member_name(value):
    if not isinstance(value, str) or len(value) > 4096 or "\\" in value:
        raise ManagementError("镜像归档包含非法成员路径。", 3)
    while value.startswith("./"):
        value = value[2:]
    if (not value or value.startswith("/") or ".." in PurePosixPath(value).parts
            or any(not c.isprintable() for c in value)):
        raise ManagementError("镜像归档包含不安全成员路径。", 3)
    return str(PurePosixPath(value))


def index_members(archive, progress=None):
    members = {}
    for index, item in enumerate(archive):
        if index >= 100000:
            raise ManagementError("归档成员过多，超过读取上限。", 3)
        if progress and index % 128 == 0:
            progress("正在读取归档目录…", True)
        if item.isdir():
            continue
        name = member_name(item.name)
        if not item.isfile() or item.issparse() or name in members or item.size < 0:
            raise ManagementError("归档含链接、特殊文件、稀疏文件或重复成员，拒绝导入。", 3)
        members[name] = item
    return members


def metadata(archive, members, name):
    name = member_name(name)
    item = members.get(name)
    if item is None or item.size > MAX_METADATA:
        raise ManagementError("镜像元数据缺失或超过读取上限。", 3)
    with archive.extractfile(item) as stream:
        raw = stream.read(MAX_METADATA + 1)
    return raw, json.loads(raw, object_pairs_hook=unique_object)


def inspect(path, progress=None):
    path = Path(path)
    try:
        with archive_file(path) as source:
            before = fingerprint(source)
            before_hash = content_hash(source, progress)
            reader = CopyProgress(source, before[2], progress) if progress else source
            with tarfile.open(fileobj=reader, mode="r:*") as archive:
                members = index_members(archive, progress)
                if "manifest.json" not in members:
                    raise ManagementError("需要 docker save 镜像归档；不支持 docker export 根文件系统或纯 OCI 归档。", 3)
                _, manifest = metadata(archive, members, "manifest.json")
                if not isinstance(manifest, list) or not 1 <= len(manifest) <= 1024:
                    raise ValueError
                result = []
                seen = set()
                for item in manifest:
                    if not isinstance(item, dict) or not isinstance(item.get("Layers"), list):
                        raise ValueError
                    config_path = member_name(item.get("Config"))
                    raw, config = metadata(archive, members, config_path)
                    identity = "sha256:" + hashlib.sha256(raw).hexdigest()
                    layers = tuple(member_name(layer) for layer in item["Layers"])
                    if len(layers) > 1024 or any(layer not in members for layer in layers):
                        raise ValueError
                    if not isinstance(config, dict) or not isinstance(config.get("rootfs"), dict):
                        raise ValueError
                    diffs = config["rootfs"].get("diff_ids")
                    if (config["rootfs"].get("type") != "layers" or not isinstance(diffs, list)
                            or len(diffs) != len(layers)
                            or any(not isinstance(d, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", d)
                                   for d in diffs)):
                        raise ValueError
                    platform = "/".join(str(config.get(k, "")) for k in ("os", "architecture", "variant")).rstrip("/")
                    if len(platform) > 128 or any(not c.isprintable() for c in platform):
                        raise ValueError
                    tags = item.get("RepoTags") or [None]
                    if not isinstance(tags, list) or len(tags) > 1024:
                        raise ValueError
                    size = sum(members[layer].size for layer in layers)
                    for tag in tags:
                        repository, tag = split_reference(tag) if tag else ("", "")
                        key = (identity, repository, tag)
                        if key not in seen:
                            if len(result) >= 4096:
                                raise ManagementError("归档镜像及标签数量超过 4096，请拆分归档。", 3)
                            result.append(ArchiveImage(config_path, layers, identity,
                                                       repository, tag, size, platform))
                            seen.add(key)
                if fingerprint(source) != before or content_hash(source, progress) != before_hash:
                    raise ManagementError("归档在读取期间发生变化，请重新输入路径。", 3)
                return Archive(path, before, tuple(result), before_hash)
    except (tarfile.TarError, ValueError, TypeError, UnicodeError, RecursionError, EOFError):
        raise ManagementError("镜像归档损坏或格式不受支持；支持 docker save 的 tar/gzip/bzip2/xz 归档。", 3) from None


def check_destination(installation, target, identity):
    try:
        rows = compose.records_from_json(run_readonly(images.command(installation), installation.root))
        for row in rows:
            repository, tag = compose.text_field(row, "Repository", 1024), compose.text_field(row, "Tag")
            if repository in ("", "<none>") or tag in ("", "<none>"):
                continue
            if canonical(f"{repository}:{tag}") == canonical(target) and row.get("ID") != identity:
                raise ManagementError("目标名称和 tag 已指向另一个本地镜像，请修改后重试；未覆盖原标签。", 4)
    except (ValueError, UnicodeError, RecursionError):
        raise ManagementError("无法可靠核对本地镜像标签，未执行导入。", 5) from None


def work_directory(root):
    parent = root / "state/image-import"
    parent.mkdir(mode=0o700, exist_ok=True)
    if not stat.S_ISDIR(parent.lstat().st_mode):
        raise ManagementError("state/image-import 必须是实际目录。", 3)
    return parent


class CopyProgress:
    def __init__(self, source, size, progress):
        self.source, self.size, self.progress = source, size, progress
        self.done, self.last = 0, time.monotonic()

    def __getattr__(self, name):
        return getattr(self.source, name)

    def read(self, size=-1):
        data = self.source.read(size)
        self.done += len(data)
        now = time.monotonic()
        if self.progress and now - self.last >= 0.5:
            self.progress(f"当前镜像文件：{human_size(self.done)} / {human_size(self.size)}", False)
            self.last = now
        return data


def stage(preview, image, target, destination, progress):
    with archive_file(preview.path) as source:
        if (fingerprint(source) != preview.fingerprint
                or content_hash(source, progress) != preview.content_sha256):
            raise ManagementError("归档已变化，请重新读取并确认。", 3)
        reader = CopyProgress(source, preview.fingerprint[2], progress) if progress else source
        with tarfile.open(fileobj=reader, mode="r:*") as archive:
            members = index_members(archive, progress)
            required = [image.config, *image.layers]
            names = ["config.json", *(f"layer-{index}.tar" for index in range(len(image.layers)))]
            size = sum(members[path].size for path in required)
            if shutil.disk_usage(destination.parent).free < size + 2 * 1024 * 1024:
                raise ManagementError("安装目录磁盘空间不足，无法准备临时导入归档。", 4)
            with tarfile.open(destination, "w") as output:
                for index, (path, name) in enumerate(zip(required, names)):
                    if progress:
                        progress(f"准备镜像文件 {index + 1}/{len(required)}", False)
                    item = tarfile.TarInfo(name)
                    item.size = members[path].size
                    item.mode = 0o600
                    with archive.extractfile(members[path]) as content:
                        output.addfile(item, CopyProgress(content, item.size, progress))
                manifest = json.dumps([{"Config": "config.json", "RepoTags": [target],
                                        "Layers": names[1:]}]).encode()
                item = tarfile.TarInfo("manifest.json")
                item.size = len(manifest)
                item.mode = 0o600
                output.addfile(item, io.BytesIO(manifest))
        if (fingerprint(source) != preview.fingerprint
                or content_hash(source, progress) != preview.content_sha256):
            raise ManagementError("准备期间原归档已变化，未执行导入。", 3)


def imported_at(installation, identity):
    try:
        raw = read_registered(installation.root, f"state/image-import/{identity.removeprefix('sha256:')}.json")
        record = json.loads(raw, object_pairs_hook=unique_object)
        if record["image_id"] == identity:
            value = record["imported_at"]
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).isoformat()
    except (ManagementError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        pass
    return None


def apply(installation, preview, image, repository, tag, *, confirmed=False, progress=None):
    if not confirmed:
        return Result("未确认，未执行导入。", 2)
    load_started = False
    loaded = False
    try:
        target = reference(repository, tag)
        if image not in preview.images:
            raise ManagementError("所选镜像不属于已确认的归档。", 2)
        with instance_lock(installation.root):
            if Installation.load(installation.root) != installation:
                raise ManagementError("安装记录已变化，请重新确认。", 4)
            check_destination(installation, target, image.identity)
            parent = work_directory(installation.root)
            with tempfile.TemporaryDirectory(prefix="load-", dir=parent) as temporary:
                archive = Path(temporary) / "selected.tar"
                stage(preview, image, target, archive, progress)
                check_destination(installation, target, image.identity)
                if progress:
                    progress(f"正在导入 {target}", False)
                load_started = True
                run_command(compose.docker_command(installation) + ["image", "load", "--input", str(archive)],
                            installation.root, timeout=3600,
                            tick=(lambda: progress(f"正在导入 {target}", True)) if progress else None)
                observed = run_readonly(
                    compose.docker_command(installation) + ["image", "inspect", "--format", "{{.Id}}", target],
                    installation.root).decode("utf-8").strip()
                if observed != image.identity:
                    raise ManagementError("导入后镜像 ID 核对失败，请查询实际镜像状态。", 5)
                loaded = True
                record = {"image_id": observed, "reference": target,
                          "imported_at": datetime.now(timezone.utc).isoformat()}
                pending = Path(temporary) / "record.json"
                pending.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
                os.replace(pending, parent / f"{observed.removeprefix('sha256:')}.json")
                if progress:
                    progress(f"导入完成：{target}", False)
            return Result(f"镜像导入完成：{target}；未切换或重启任何容器。",
                          data={"image_id": image.identity, "reference": target,
                                "imported_at": record["imported_at"]})
    except (ManagementError, OSError, tarfile.TarError, ValueError, KeyError, EOFError) as error:
        message = str(error) if isinstance(error, ManagementError) else "读取、准备或记录镜像失败，请检查归档及磁盘空间。"
        status = ("镜像已导入，但导入时间未成功记录。" if loaded else
                  "导入可能部分完成，未自动清理镜像，请查询实际状态。" if load_started else "未执行 Docker 导入。")
        return Result(f"{message} {status}", error.code if isinstance(error, ManagementError) else 5,
                      {"load_started": load_started, "loaded": loaded})
