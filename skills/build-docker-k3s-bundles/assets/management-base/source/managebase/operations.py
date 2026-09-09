"""One command registry shared by the CLI and terminal menu."""

import importlib.util
from pathlib import Path
import platform
import sys

from . import __version__
from . import backups, changes, compose, firewall, firewall_rules, image_import, images, lifecycle, locations, ports
from .layout import Installation, REQUIRED_FILES
from .model import ManagementError, Result
from .runner import run_readonly

COMMANDS = {
    **lifecycle.ACTIONS,
    **changes.COMMANDS,
    **backups.COMMANDS,
    "doctor": "工具环境",
    "layout": "安装目录检查",
    "status": "服务状态",
    "image-versions": "本机镜像查询",
    "image-import": "导入镜像",
    "locations": "容器相关位置",
    "exposed-ports": "对外暴露端口",
    "docker-firewall": "DOCKER-USER 防火墙",
    "firewall-add": "添加 DOCKER-USER 规则",
    "config-check": "Compose 配置校验",
}


def execute(name: str, root: Path, *, dry_run: bool = False, container=None,
            all_containers=False, yes=False, archive=None, image_index=None,
            image_name=None, image_tag=None, service=None, image=None,
            compose_file=None, output=None, position=None, protocol=None, source=None,
            source_port=None, destination=None, destination_port=None, action=None) -> Result:
    if name not in COMMANDS:
        return Result("未知命令，未执行任何操作。", 2)
    try:
        if name in lifecycle.ACTIONS and not dry_run and not yes:
            return Result("非交互操作必须提供 --yes，并指定 --container 或 --all。", 2)
        if name != "image-import" and any(value is not None for value in
                                         (archive, image_index, image_name, image_tag)):
            return Result("镜像导入参数仅用于 image-import。", 2)
        if name not in lifecycle.ACTIONS and (container or (all_containers and name not in backups.COMMANDS)):
            return Result("容器选择及确认参数仅用于 start / stop / restart。", 2)
        firewall_values = (position, protocol, source, source_port, destination, destination_port, action)
        if name != "firewall-add" and any(value is not None for value in firewall_values):
            return Result("防火墙参数仅用于 firewall-add。", 2)
        if name == "firewall-add" and not dry_run and not yes:
            return Result("防火墙变更需要 --yes；预览使用 --dry-run。", 2)
        if name not in (*lifecycle.ACTIONS, "image-import", *changes.COMMANDS, *backups.COMMANDS, "firewall-add") and yes:
            return Result("--yes 仅用于变更操作。", 2)
        if ((service is not None and name not in (*changes.COMMANDS, *backups.COMMANDS))
                or (image is not None and name != "image-switch")
                or (compose_file is not None and name != "service-add")
                or (output is not None and name not in backups.COMMANDS)):
            return Result("服务、镜像、Compose 源文件或输出路径参数与命令不匹配。", 2)
        if name in (*changes.COMMANDS, *backups.COMMANDS):
            if not dry_run and not yes:
                return Result("变更操作必须提供 --yes；预览使用 --dry-run。", 2)
            if name == "image-switch" and (not service or not image):
                return Result("切换镜像必须指定 --service 和 --image。", 2)
            if name == "service-add" and (not service or compose_file is None):
                return Result("增加服务必须指定 --service 和 --compose-file。", 2)
        if name == "image-import":
            if archive is None:
                return Result("镜像导入必须提供 --archive 完整路径。", 2)
            if not dry_run and not yes:
                return Result("镜像导入必须明确提供 --yes；预览请使用 --dry-run。", 2)
        if name == "doctor":
            return Result("管理工具环境信息", data={
                "version": __version__,
                "python": platform.python_version(),
                "architecture": platform.machine(),
                "system": platform.system(),
                "python_supported": sys.version_info >= (3, 10),
                "curses_available": importlib.util.find_spec("_curses") is not None,
                "capabilities": list(COMMANDS),
                "scope": "management-only; docker-compose; local socket",
            })
        installation = Installation.load(root)
        if name == "firewall-add":
            rule = firewall_rules.Rule.parse(
                position=position, protocol=protocol, source=source, source_port=source_port,
                destination=destination, destination_port=destination_port, action=action)
            plan = firewall_rules.prepare(installation, rule)
            if dry_run:
                return Result("防火墙规则预览；仅查询，未写入规则或备份文件。", data=plan.summary())
            return firewall_rules.apply(plan, confirmed=yes)
        if name in changes.COMMANDS:
            plan = (changes.prepare_switch(installation, service, image) if name == "image-switch" else
                    changes.prepare_add(installation, service, compose_file))
            if dry_run:
                return Result("变更预览通过；未写入固定配置、未修改容器。", data=plan.summary())
            return changes.apply(plan, confirmed=yes)
        if name in backups.COMMANDS:
            plan = backups.prepare(installation, name, service=service, all_services=all_containers)
            target = backups.destination(plan, output)
            if dry_run:
                return Result("备份预览；未创建备份文件。", data={**plan.summary(), "path": str(target)})
            return backups.apply(plan, target, confirmed=yes)
        if name == "image-import":
            preview = image_import.inspect(archive)
            if image_index is None and len(preview.images) != 1:
                return Result("归档包含多个镜像或标签，请用 --image-index 指定序号（从 1 开始）。",
                              0 if dry_run else 2, {
                                  "archive_images": [
                                      {"index": i, "name": entry.repository, "tag": entry.tag,
                                       "size": entry.size, "platform": entry.platform}
                                      for i, entry in enumerate(preview.images, 1)]})
            selected = 1 if image_index is None else image_index
            if type(selected) is not int or not 1 <= selected <= len(preview.images):
                return Result("镜像序号超出归档范围。", 2)
            image = preview.images[selected - 1]
            repository = image.repository if image_name is None else image_name
            tag = image.tag if image_tag is None else image_tag
            target = image_import.reference(repository, tag)
            if dry_run:
                return Result("镜像导入预览；未调用 Docker、未创建临时文件。", data={
                    "archive": str(preview.path), "image_id": image.identity,
                    "reference": target, "size": image.size, "size_source": "archive-layer-bytes",
                    "platform": image.platform, "mutates_workloads": False})
            return image_import.apply(installation, preview, image, repository, tag, confirmed=yes)
        if name in lifecycle.ACTIONS:
            if bool(container) == bool(all_containers):
                return Result("必须指定 --container 或 --all，且不能同时指定。", 2)
            plan = lifecycle.prepare(installation, name, compose.services(installation),
                                     container=container, all_containers=all_containers)
            if dry_run:
                return Result("仅查询并预览目标；未启停或重启容器。", data={
                    "action": name, "targets": list(plan.targets), "mutates_workloads": False})
            return lifecycle.apply(plan, confirmed=yes)
        if name == "layout":
            return Result("管理入口所需的固定路径及实例记录检查通过。", data={
                "root": str(installation.root),
                "bundle": installation.bundle_name,
                "instance": installation.instance_id,
                "compose_project": installation.project,
                "checked_files": list(REQUIRED_FILES),
                "not_checked": ["完整安装包规范", "Compose 内容", "运行时健康"],
            })
        if dry_run:
            if name == "docker-firewall":
                return Result("只读查询计划；未读取或修改防火墙。", data={
                    "commands": firewall.commands(), "cwd": str(installation.root),
                    "mutates_workloads": False, "resets_counters": False,
                })
            return Result("执行计划；未启动 Docker 命令。", data={
                "argv": images.command(installation) if name == "image-versions"
                        else compose.command(installation, "status" if name == "exposed-ports" else name),
                "cwd": str(installation.root),
                "mutates_workloads": False,
                **({"follow_up": "只读查询本机全部容器，并按容器 ID 分批 inspect 核对镜像引用。"}
                   if name == "image-versions" else {}),
            })
        if name == "status":
            return Result("服务状态查询完成；不代表应用健康检查通过。",
                          data={"services": compose.services(installation)})
        if name == "image-versions":
            return Result("本机镜像查询完成；使用统计包含已停止容器，导入时间无记录时显示未知。",
                          data={"images": images.inventory(installation), "scope": "local-docker"})
        if name == "locations":
            return Result("容器相关位置查询完成；Compose 文件按实际加载顺序列出。",
                          data={"locations": locations.locations(installation)})
        if name == "exposed-ports":
            return Result("实际 Docker 端口映射查询完成；不代表外部连通性或应用监听检测。",
                          data={"ports": ports.published(installation)})
        if name == "docker-firewall":
            snapshot = firewall.inspect_chain(installation)
            return Result("本机 DOCKER-USER / filter 规则快照；五元组按规则原样显示，保留附加匹配条件。"
                          if snapshot["complete"] else "防火墙查询不完整；读取失败不代表没有规则。",
                          code=0 if snapshot["complete"] else 5, data={"firewall": snapshot})
        run_readonly(compose.command(installation, name), installation.root)
        return Result("Compose 配置校验通过；未应用配置、未重建容器。")
    except ManagementError as error:
        return Result(str(error), error.code)
