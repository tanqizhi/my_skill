"""Fixed-path contract. Never execute or source installation metadata."""

import json
import os
from pathlib import Path
import re
import stat
from dataclasses import dataclass
from typing import Any

from .model import ManagementError

COMPOSE_FILES = ("deploy/docker/compose.yaml", "config/compose.override.yaml")
ENV_FILES = ("config/compose.env",)
REQUIRED_FILES = ("bundle.yaml", *COMPOSE_FILES, *ENV_FILES)
ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
PROJECT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}\Z")
PROFILE_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}\Z")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def read_registered(root: Path, relative: str, *, limit: int = 65536) -> bytes:
    """Use directory descriptors so symlinked components are never followed."""
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ManagementError("非法的配置相对路径。")
    fd = -1
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ManagementError(f"配置必须是普通文件：{relative}")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ManagementError(f"配置文件超过读取上限：{relative}")
        return data
    except OSError:
        raise ManagementError(f"文件缺失、不可读或包含符号链接：{relative}") from None
    finally:
        if fd >= 0:
            os.close(fd)


@dataclass(frozen=True)
class Installation:
    root: Path
    bundle_name: str
    instance_id: str
    project: str
    docker_binary: Path
    profiles: tuple[str, ...]
    docker_config: Path | None = None

    @classmethod
    def load(cls, requested_root: Path) -> "Installation":
        if not requested_root.is_absolute():
            raise ManagementError("安装根目录必须是绝对路径。")
        try:
            root = requested_root.resolve(strict=True)
        except (OSError, RuntimeError):
            raise ManagementError("安装根目录不存在或无法解析。") from None
        if root == Path("/") or not root.is_dir():
            raise ManagementError("不能将系统根目录或普通文件作为安装根目录。")
        try:
            raw = read_registered(root, "state/installation.json")
            state = json.loads(raw, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError):
            raise ManagementError("安装记录 JSON 无效或包含重复字段；未输出配置内容。") from None
        if not isinstance(state, dict):
            raise ManagementError("安装记录必须是 JSON 对象。")
        if type(state.get("layout_version")) is not int or state["layout_version"] != 1:
            raise ManagementError("仅支持目录规范版本 1，旧包需要独立迁移方案。")
        if state.get("install_root") != str(root):
            raise ManagementError("安装记录中的根目录与实际目录不一致，拒绝猜测或自动迁移。")
        for field in ("bundle_name", "instance_id"):
            if not isinstance(state.get(field), str) or not ID_PATTERN.fullmatch(state[field]):
                raise ManagementError(f"安装记录字段不合法：{field}")
        if not isinstance(state.get("bundle_version"), str) or not state["bundle_version"]:
            raise ManagementError("安装记录缺少 bundle_version。")
        if state.get("deploy_targets") != ["docker"]:
            raise ManagementError("第一版仅支持 Docker Compose，尚未实现 K3s 适配器。")
        compose = state.get("compose")
        if not isinstance(compose, dict):
            raise ManagementError("安装记录缺少 compose 对象。")
        if compose.get("files") != list(COMPOSE_FILES) or compose.get("env_files") != list(ENV_FILES):
            raise ManagementError("Compose 文件和环境文件必须使用固定路径及固定加载顺序。")
        project = compose.get("project_name")
        if not isinstance(project, str) or not PROJECT_PATTERN.fullmatch(project):
            raise ManagementError("Compose 项目名无效。")
        binary = compose.get("docker_binary")
        if not isinstance(binary, str) or not binary.startswith("/") or "\0" in binary:
            raise ManagementError("docker_binary 必须是经过安装器验证的绝对路径。")
        profiles = compose.get("profiles")
        if (not isinstance(profiles, list) or len(profiles) > 16
                or any(not isinstance(p, str) or not PROFILE_PATTERN.fullmatch(p) for p in profiles)
                or len(set(profiles)) != len(profiles)):
            raise ManagementError("Compose profiles 必须是不重复的有效名称列表。")
        for relative in REQUIRED_FILES:
            read_registered(root, relative, limit=4 * 1024 * 1024)
        config = compose.get("docker_config")
        if config is not None:
            if config != "config/services/installer/docker-cli":
                raise ManagementError("Docker CLI 配置目录不符合安装约定。")
            read_registered(root, config + "/config.json")
        return cls(root, state["bundle_name"], state["instance_id"],
                   project, Path(binary), tuple(profiles), root / config if config else None)
