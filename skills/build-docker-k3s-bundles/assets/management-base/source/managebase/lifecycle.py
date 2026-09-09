"""Manage exact existing containers; never create or recreate workloads."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
import re
import stat

from . import compose
from .layout import Installation
from .model import ManagementError, Result
from .runner import run_command

ACTIONS = {"start": "启动容器", "stop": "停止容器", "restart": "重启容器"}


@dataclass(frozen=True)
class Plan:
    installation: Installation
    action: str
    targets: tuple[tuple[str, str], ...]


def prepare(installation, action, rows, *, container=None, all_containers=False):
    if action not in ACTIONS or bool(container) == bool(all_containers):
        raise ManagementError("必须选择一个容器，或明确选择全部容器。", 2)
    selected = rows if all_containers else [
        row for row in rows if container in (row["id"], row["container"])]
    if not selected or (not all_containers and len(selected) != 1):
        raise ManagementError("目标容器不存在或名称不唯一，请重新选择。", 2)
    ids = [row["id"] for row in selected]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[0-9a-f]{64}", i) for i in ids):
        raise ManagementError("容器标识无效，请重新查询。", 5)
    return Plan(installation, action, tuple((r["id"], r["container"]) for r in selected))


@contextmanager
def instance_lock(root):
    descriptors = []
    try:
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(parent)
        for part in ("state", "locks"):
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(parent)
        lock = os.open("management.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                       0o600, dir_fd=parent)
        descriptors.append(lock)
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise ManagementError("管理锁必须是普通文件。", 4)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ManagementError("当前实例已有管理操作正在执行。", 4) from None
        yield
    except OSError:
        raise ManagementError("无法获取 state/locks 下的管理锁，请检查安装目录及权限。", 4) from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def apply(plan, *, confirmed=False, progress=None):
    if not confirmed:
        return Result("未确认，未执行任何操作。", 2)
    completed = []
    current = None
    try:
        with instance_lock(plan.installation.root):
            installation = Installation.load(plan.installation.root)
            if installation != plan.installation:
                raise ManagementError("安装记录已变化，请重新选择并确认。", 4)
            members = {r["id"] for r in compose.services(installation)}
            if not {identity for identity, _ in plan.targets} <= members:
                raise ManagementError("目标容器已变化，请重新选择并确认。", 4)
            for index, (identity, name) in enumerate(plan.targets, 1):
                current = name
                message = f"[{index}/{len(plan.targets)}] {ACTIONS[plan.action]}：{name}"
                if progress:
                    progress(message, False)
                run_command(compose.docker_command(installation) + [plan.action, identity],
                            installation.root, timeout=120,
                            tick=(lambda: progress(message, True)) if progress else None)
                completed.append(name)
                current = None
                if progress:
                    progress(f"[{index}/{len(plan.targets)}] 完成：{name}", False)
        return Result(f"{ACTIONS[plan.action]}完成，共 {len(completed)} 个。",
                      data={"completed": completed})
    except ManagementError as error:
        return Result(f"{error} 已完成 {len(completed)} 个；未自动回滚，请查询容器状态。",
                      error.code, {"completed": completed, "uncertain": current})
