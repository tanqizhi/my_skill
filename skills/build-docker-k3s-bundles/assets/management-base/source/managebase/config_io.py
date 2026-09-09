"""Round-trip YAML, fixed-input snapshots, and atomic configuration updates."""

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timezone

from .layout import COMPOSE_FILES, ENV_FILES, read_registered
from .model import ManagementError

# Source checkouts use the same pinned pure-Python dependency as the zipapp.
vendor = Path(__file__).resolve().parents[1] / "vendor"
if vendor.is_dir() and str(vendor) not in sys.path:
    sys.path.insert(0, str(vendor))
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

LIMIT = 4 * 1024 * 1024
OVERRIDE = COMPOSE_FILES[1]


def yaml_codec():
    codec = YAML(typ="rt", pure=True)
    codec.preserve_quotes = True
    codec.allow_duplicate_keys = False
    return codec


def decode(raw):
    try:
        result = yaml_codec().load(raw.decode("utf-8"))
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (YAMLError, ValueError, UnicodeError, RecursionError):
        raise ManagementError("Compose YAML 无效、重复键或根节点不是对象；未输出原文。", 3) from None


def encode(document):
    try:
        output = io.StringIO()
        yaml_codec().dump(document, output)
        return output.getvalue().encode("utf-8")
    except (YAMLError, ValueError, RecursionError):
        raise ManagementError("无法安全保存 Compose YAML。", 3) from None


def external_file(path):
    path = Path(path)
    if not path.is_absolute():
        raise ManagementError("Compose 源文件必须使用完整绝对路径。", 2)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ManagementError("Compose 源文件必须是普通文件。", 3)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ManagementError("Compose 源文件超过 4 MiB 上限。", 3)
        return raw
    except (OSError, ValueError):
        raise ManagementError("Compose 源文件不可读或包含非法路径。", 3) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def snapshot(installation):
    return {path: read_registered(installation.root, path, limit=LIMIT)
            for path in (*COMPOSE_FILES, *ENV_FILES, "state/installation.json")}


def unchanged(installation, expected):
    if snapshot(installation) != expected:
        raise ManagementError("安装记录或 Compose 输入已变化，请重新预览并确认。", 4)


def operation_id(prefix):
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def private_directory(root, relative):
    current = root
    for part in relative.split("/"):
        if part in ("", ".", ".."):
            raise ManagementError("非法操作目录。", 3)
        current = current / part
        current.mkdir(mode=0o700, exist_ok=True)
        if not stat.S_ISDIR(current.lstat().st_mode):
            raise ManagementError("操作目录不能包含符号链接。", 3)
    return current


def write_private(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != 0o600:
            raise ManagementError("文件系统不支持私有文件权限，请选择支持 Linux 权限的目录。", 4)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def replace_override(installation, expected, raw):
    unchanged(installation, expected)
    destination = installation.root / OVERRIDE
    metadata = destination.stat()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".manage-", suffix=".yaml",
                                         dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        unchanged(installation, expected)
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def candidate_file(installation, raw):
    with tempfile.NamedTemporaryFile(prefix=".manage-preview-", suffix=".yaml",
                                     dir=installation.root / "config") as stream:
        stream.write(raw)
        stream.flush()
        yield Path(stream.name)


def save_change_backup(installation, inputs, record):
    relative = f"backups/{record['operation_id']}"
    parent = private_directory(installation.root, relative)
    for path, raw in inputs.items():
        destination = parent / path
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_private(destination, raw)
    record["input_hashes"] = {path: hashlib.sha256(raw).hexdigest() for path, raw in inputs.items()}
    write_private(parent / "plan.json", json.dumps(record, ensure_ascii=False, indent=2).encode())
    return parent
