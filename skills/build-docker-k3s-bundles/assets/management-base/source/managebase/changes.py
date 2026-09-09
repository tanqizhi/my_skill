"""Service-scoped Compose changes, validation, configuration backups, and recovery."""

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import time

from . import compose, config_io, images
from .layout import Installation
from .lifecycle import instance_lock
from .model import ManagementError, Result
from .runner import run_command, run_readonly

COMMANDS = {"image-switch": "服务切换镜像", "service-add": "增加服务"}


def service_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", value):
        raise ManagementError("服务名只能包含字母、数字、点、下划线和短横线，不能以符号开头。", 2)
    return value


def local_image(installation, reference):
    if not isinstance(reference, str) or not reference or reference.startswith("-"):
        raise ManagementError("请选择有效的本地镜像。", 2)
    identity = run_readonly(compose.docker_command(installation) +
                            ["image", "inspect", "--format", "{{.Id}}", reference],
                            installation.root).decode("utf-8").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
        raise ManagementError("无法确认本地镜像 ID，未执行变更。", 5)
    return identity


def verify_image_volumes(installation, identity, effective):
    try:
        declared = json.loads(run_readonly(
            compose.docker_command(installation) + ["image", "inspect", "--format",
                                                    "{{json .Config.Volumes}}", identity],
            installation.root)) or {}
        if not isinstance(declared, dict):
            raise ValueError
        destinations = {mount["target"] for mount in effective.get("volumes", [])}
        destinations.update(value.split(":", 1)[0] for value in effective.get("tmpfs", []))
        if not set(declared) <= destinations:
            raise ManagementError("镜像声明了未映射的 VOLUME，请显式绑定固定目录，避免生成匿名卷。", 3)
    except (ValueError, TypeError, UnicodeError):
        raise ManagementError("无法核对镜像持久化目录。", 5) from None


def candidate_config(installation, raw):
    with config_io.candidate_file(installation, raw) as path:
        return compose.configuration(installation, override=path)


def select_rows(installation, service):
    return [row for row in compose.services(installation) if row["service"] == service]


def identities(rows):
    return sorted((r["id"], r["image_id"], r["state"]) for r in rows)


def verify_unchanged_services(before, after, selected, *, adding=False):
    expected = set(before["services"]) | ({selected} if adding else set())
    if set(after["services"]) != expected:
        raise ManagementError("变更涉及未选择的服务，已拒绝。", 4)
    for name, value in before["services"].items():
        if name != selected and after["services"][name] != value:
            raise ManagementError("变更影响了其他服务，已拒绝。", 4)
    for group, value in before.items():
        if group == "services":
            continue
        if group in ("volumes", "networks", "configs", "secrets"):
            if any(after.get(group, {}).get(name) != definition for name, definition in value.items()):
                raise ManagementError("变更会修改现有共享资源，已拒绝。", 4)
        elif after.get(group) != value:
            raise ManagementError("变更会修改项目级配置，已拒绝。", 4)


@dataclass(frozen=True)
class Plan:
    installation: Installation
    action: str
    service: str
    inputs: dict
    candidate: bytes
    image_id: str
    image_label: str
    previous_rows: list
    old_reference: str = ""
    no_change: bool = False
    target_count: int = 1
    before_effective: dict | None = None
    effective: dict | None = None

    def summary(self):
        return {"action": self.action, "service": self.service,
                "image": self.image_label, "image_id": self.image_id,
                "compose": str(self.installation.root / config_io.OVERRIDE),
                "effect": "创建未启动容器" if self.action == "service-add" else "仅重建并启动所选服务",
                "no_change": self.no_change}


def prepare_switch(installation, service, image_reference):
    service_name(service)
    inputs = config_io.snapshot(installation)
    before = compose.configuration(installation)
    if service not in before["services"]:
        raise ManagementError("所选服务不在当前 Compose 配置中。", 2)
    rows = select_rows(installation, service)
    if not rows or len({r["image_id"] for r in rows}) != 1:
        raise ManagementError("服务尚无容器或包含不同镜像的副本，无法建立可靠回退计划。", 4)
    if any(r["state"] not in ("running", "exited", "created") for r in rows):
        raise ManagementError("容器处于过渡状态，请稳定后再切换镜像。", 4)
    if len({r["state"] == "running" for r in rows}) != 1:
        raise ManagementError("服务副本启停状态不一致，请统一状态后再切换镜像。", 4)
    image_id = local_image(installation, image_reference)
    old_reference = before["services"][service].get("image", "")
    if local_image(installation, old_reference) != rows[0]["image_id"]:
        raise ManagementError("当前配置镜像与实际容器不一致，不能将未确认的配置作为回退基线。", 4)
    if image_id == rows[0]["image_id"]:
        return Plan(installation, "image-switch", service, inputs, inputs[config_io.OVERRIDE],
                    image_id, image_reference, rows, old_reference, True)
    verify_image_volumes(installation, image_id, before["services"][service])
    # Compare Compose's own service hash, not a hand-written subset of config fields.
    expected_hash = run_readonly(compose.command(installation, "config-hash") + [service],
                                 installation.root).decode().split()
    if len(expected_hash) != 2 or expected_hash[0] != service:
        raise ManagementError("当前 Compose 不支持可靠的服务配置指纹检查。", 4)
    for row in rows:
        actual_hash = run_readonly(compose.docker_command(installation) +
                                   ["inspect", "--format",
                                    '{{index .Config.Labels "com.docker.compose.config-hash"}}', row["id"]],
                                   installation.root).decode().strip()
        if actual_hash != expected_hash[1]:
            raise ManagementError("服务存在尚未应用的 Compose 修改，请先处理配置差异，再切换镜像。", 4)
    override = config_io.decode(inputs[config_io.OVERRIDE])
    services = override.setdefault("services", {})
    if not isinstance(services, dict) or not isinstance(services.get(service, {}), dict):
        raise ManagementError("override 的 services 结构无效。", 3)
    services[service] = copy.deepcopy(services.get(service, {}))
    services[service]["image"] = image_id
    candidate = config_io.encode(override)
    after = candidate_config(installation, candidate)
    verify_unchanged_services(before, after, service)
    old_service = copy.deepcopy(before["services"][service])
    old_service["image"] = image_id
    if old_service != after["services"][service]:
        raise ManagementError("候选配置不止修改了镜像，已拒绝。", 4)
    config_io.unchanged(installation, inputs)
    return Plan(installation, "image-switch", service, inputs, candidate, image_id,
                image_reference, rows, old_reference, before_effective=before, effective=after)


def referenced_resources(service):
    result = {"networks": set(), "volumes": set(), "configs": set(), "secrets": set()}
    for group in ("networks", "configs", "secrets"):
        values = service.get(group, {})
        if not isinstance(values, (dict, list)):
            raise ManagementError(f"服务的 {group} 结构无效。", 3)
        for item in values:
            name = item.get("source") if isinstance(item, dict) else item
            if not isinstance(name, str):
                raise ManagementError(f"服务的 {group} 引用无效。", 3)
            result[group].add(name)
    if not service.get("networks") and not service.get("network_mode"):
        result["networks"].add("default")
    mounts = service.get("volumes") or []
    if not isinstance(mounts, list):
        raise ManagementError("服务 volumes 必须是列表。", 3)
    for mount in mounts:
        if isinstance(mount, dict):
            if mount.get("type", "volume") == "volume" and mount.get("source"):
                result["volumes"].add(mount["source"])
        elif isinstance(mount, str) and ":" in mount:
            source = mount.split(":")[0]
            if "/" not in source and not source.startswith("."):
                result["volumes"].add(source)
        else:
            raise ManagementError("新增服务必须显式声明持久化来源，不能使用匿名卷。", 3)
    return result


def validate_storage(installation, service, effective):
    allowed = [installation.root / path / service for path in
               ("data", "config/services", "secrets", "logs/services")]
    for mount in effective.get("volumes", []):
        if mount.get("type") == "tmpfs":
            continue
        if mount.get("type") != "bind":
            raise ManagementError("新增服务持久化请使用固定目录的 bind mount，不自动创建命名卷或匿名卷。", 3)
        path = Path(mount["source"]).resolve()
        if not any(path.is_relative_to(root) for root in allowed):
            raise ManagementError("新增服务挂载必须位于其 data/config/services/secrets/logs/services 固定目录内。", 3)


def prepare_add(installation, service, source):
    service_name(service)
    inputs = config_io.snapshot(installation)
    before = compose.configuration(installation)
    if service in before["services"] or select_rows(installation, service):
        raise ManagementError("服务名已存在，不能覆盖现有服务。", 2)
    document = config_io.decode(config_io.external_file(source))
    if "include" in document or not isinstance(document.get("services"), dict):
        raise ManagementError("源文件需要 services 对象，不能通过 include 引入其他文件。", 3)
    definition = document["services"].get(service)
    if not isinstance(definition, dict) or "extends" in definition:
        raise ManagementError("源文件未定义该服务，或使用了暂不支持的 extends。", 3)
    profiles = definition.get("profiles", [])
    if not isinstance(profiles, list) or any(p not in installation.profiles for p in profiles):
        raise ManagementError("新增服务只能使用安装记录中已启用的 profiles，或省略 profiles。", 3)
    env_files = definition.get("env_file") or []
    if isinstance(env_files, (str, dict)):
        env_files = [env_files]
    if not isinstance(env_files, list):
        raise ManagementError("env_file 必须是路径或列表。", 3)
    for entry in env_files:
        value = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(value, str) or "$" in value:
            raise ManagementError("env_file 必须显式指向固定配置目录内的文件。", 3)
        path = (installation.root / value).resolve()
        if not any(path.is_relative_to(installation.root / name) for name in ("config/services", "secrets")):
            raise ManagementError("env_file 不能读取固定配置/凭据目录之外的文件。", 3)
    override = config_io.decode(inputs[config_io.OVERRIDE])
    services = override.setdefault("services", {})
    if not isinstance(services, dict):
        raise ManagementError("override 的 services 结构无效。", 3)
    services[service] = copy.deepcopy(definition)
    for group, names in referenced_resources(definition).items():
        declared = document.get(group, {})
        if not isinstance(declared, dict):
            raise ManagementError("源文件的共享资源声明必须是对象。", 3)
        for name in names:
            if name in declared:
                resource = declared[name]
                if isinstance(resource, dict) and "file" in resource:
                    value = resource["file"]
                    if not isinstance(value, str) or "$" in value or not any(
                        (installation.root / value).resolve().is_relative_to(installation.root / base)
                        for base in ("config/services", "secrets")
                    ):
                        raise ManagementError("configs/secrets 文件必须位于固定配置/凭据目录内。", 3)
                if override.get(group) is None:
                    override[group] = {}
                if not isinstance(override[group], dict):
                    raise ManagementError("override 共享资源结构必须是对象。", 3)
                override[group][name] = copy.deepcopy(declared[name])
    candidate = config_io.encode(override)
    after = candidate_config(installation, candidate)
    verify_unchanged_services(before, after, service, adding=True)
    effective = after["services"][service]
    validate_storage(installation, service, effective)
    reference = effective.get("image")
    image_id = local_image(installation, reference)
    verify_image_volumes(installation, image_id, effective)
    count = effective.get("scale", effective.get("deploy", {}).get("replicas", 1))
    if type(count) is not int or not 1 <= count <= 256:
        raise ManagementError("新服务副本数必须在 1 到 256 之间。", 3)
    # Keep the accepted version immutable when the service is later started.
    services[service]["image"] = image_id
    candidate = config_io.encode(override)
    verified = candidate_config(installation, candidate)
    verify_unchanged_services(before, verified, service, adding=True)
    validate_storage(installation, service, verified["services"][service])
    config_io.unchanged(installation, inputs)
    return Plan(installation, "service-add", service, inputs, candidate, image_id, reference, [],
                target_count=count, before_effective=before, effective=verified)


def wait_service(installation, service, identity, count, *, running=True, progress=None, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        rows = select_rows(installation, service)
        good = (len(rows) == count and all(r["image_id"] == identity for r in rows)
                and all(r["state"] == "running" and r["health"] in ("", "healthy") for r in rows)
                if running else len(rows) == count and all(
                    r["image_id"] == identity and r["state"] in ("created", "exited") for r in rows))
        if good:
            return rows
        if time.monotonic() >= deadline:
            raise ManagementError("服务运行状态或健康检查未在等待时间内通过。", 5)
        if progress:
            progress("正在等待所选服务状态及健康检查…", True)
        time.sleep(1)


def apply(plan, *, confirmed=False, progress=None):
    if not confirmed:
        return Result("未确认，未修改 Compose 或容器。", 2)
    backup = None
    committed = False
    record = {"operation_id": config_io.operation_id(plan.action), **plan.summary(),
              "previous_containers": plan.previous_rows, "previous_image_reference": plan.old_reference}
    installed = plan.installation
    try:
        with instance_lock(installed.root):
            config_io.unchanged(installed, plan.inputs)
            if identities(select_rows(installed, plan.service)) != identities(plan.previous_rows):
                raise ManagementError("服务容器在确认期间已变化，请重新选择。", 4)
            if local_image(installed, plan.image_id) != plan.image_id:
                raise ManagementError("目标镜像已变化。", 4)
            if plan.no_change:
                return Result("所选服务已经使用该镜像，未重建容器。")
            if (compose.configuration(installed) != plan.before_effective
                    or candidate_config(installed, plan.candidate) != plan.effective):
                raise ManagementError("引用的配置或环境文件已变化，请重新预览并确认。", 4)
            backup = installed.root / "backups" / record["operation_id"]
            config_io.save_change_backup(installed, plan.inputs, record)
            config_io.write_private(backup / "candidate.yaml", plan.candidate)
            recovery = [
                "人工恢复说明：先核对差异；不要覆盖其他管理员在操作后做出的修改。",
                "本说明不恢复业务数据，不保证数据库迁移可回退。",
                shlex.join(["diff", "-u", "--", str(installed.root / config_io.OVERRIDE),
                            str(backup / config_io.OVERRIDE)]),
                "确认需要恢复原 override 后执行：",
                shlex.join(["cp", "--", str(backup / config_io.OVERRIDE),
                            str(installed.root / config_io.OVERRIDE)]),
                shlex.join(compose.command(installed, "config-check")),
            ]
            if plan.action == "image-switch":
                running = plan.previous_rows[0]["state"] == "running"
                recovery += [
                    "恢复运行时前，核对原标签对应的 ID 必须为：" + plan.previous_rows[0]["image_id"],
                    shlex.join(compose.docker_command(installed) +
                               ["image", "inspect", "--format", "{{.Id}}", plan.old_reference]),
                    "仅当上面的 ID 一致且配置校验通过，执行：",
                    shlex.join(compose.command(installed, "up" if running else "create") +
                               ["--scale", f"{plan.service}={len(plan.previous_rows)}", plan.service]),
                ]
            else:
                recovery += ["新增服务失败可能留下未启动容器；请先查询现场，不自动删除容器或数据。"]
            recovery += [shlex.join([str(installed.root / "manage.sh"), "status", "--json"])]
            config_io.write_private(backup / "recovery.txt", ("\n\n".join(recovery) + "\n").encode())
            record["manual_recovery"] = str(backup / "recovery.txt")
            if progress:
                progress("Compose 校验通过，原配置已备份；开始应用所选服务…", False)
            config_io.replace_override(installed, plan.inputs, plan.candidate)
            committed = True
            current_inputs = {**plan.inputs, config_io.OVERRIDE: plan.candidate}
            try:
                adding = plan.action == "service-add"
                args = compose.command(installed, "create" if adding else "up")
                if not adding:
                    args += ["--scale", f"{plan.service}={len(plan.previous_rows)}"]
                run_command(args + [plan.service], installed.root, timeout=180,
                            tick=(lambda: progress("正在应用所选服务…", True)) if progress else None)
                config_io.unchanged(installed, current_inputs)
                if compose.configuration(installed) != plan.effective:
                    raise ManagementError("应用期间引用的配置文件发生变化，需恢复并检查现场。", 4)
                wait_service(installed, plan.service, plan.image_id,
                             plan.target_count if adding else len(plan.previous_rows),
                             running=not adding, progress=progress)
                record["status"] = "complete"
                message = ("服务已添加并创建为未启动状态，可从启动容器入口启动。"
                           if adding else "服务镜像已切换，运行状态及健康检查通过。")
            except ManagementError as failure:
                record["status"] = "failed"
                try:
                    config_io.replace_override(installed, current_inputs, plan.inputs[config_io.OVERRIDE])
                    record["config_restored"] = True
                    if plan.action == "image-switch":
                        if compose.configuration(installed) != plan.before_effective:
                            raise ManagementError("引用文件已变化，无法安全恢复原服务配置。", 4)
                        if local_image(installed, plan.old_reference) != plan.previous_rows[0]["image_id"]:
                            raise ManagementError("原镜像标签已漂移，不能自动恢复运行时。", 4)
                        running = plan.previous_rows[0]["state"] == "running"
                        if progress:
                            progress("切换失败，正在恢复原镜像和启停状态…", False)
                        run_command(compose.command(installed, "up" if running else "create") +
                                    ["--scale", f"{plan.service}={len(plan.previous_rows)}", plan.service],
                                    installed.root, timeout=180,
                                    tick=(lambda: progress("恢复原服务中…", True)) if progress else None)
                        wait_service(installed, plan.service, plan.previous_rows[0]["image_id"],
                                     len(plan.previous_rows), running=running, progress=progress)
                        record["runtime_restored"] = True
                except (ManagementError, OSError):
                    record["recovery_incomplete"] = True
                message = (f"{failure} 原配置及镜像已恢复。"
                           if record.get("runtime_restored") else
                           f"{failure} 请核对现场；备份已保留，未删除容器、数据或共享资源。")
                record["message"] = message
                config_io.write_private(backup / "result.json", json.dumps(record, ensure_ascii=False).encode())
                return Result(message, failure.code, {"backup": str(backup), "recovery": record})
            record["message"] = message
            config_io.write_private(backup / "result.json", json.dumps(record, ensure_ascii=False).encode())
            return Result(message, data={"backup": str(backup), "service": plan.service,
                                         "image_id": plan.image_id})
    except (ManagementError, OSError) as failure:
        message = str(failure) if isinstance(failure, ManagementError) else "配置读写或备份失败。"
        return Result(message + (" 已有变更，请查看备份并核对现场。" if committed else " 未应用服务变更。"),
                      failure.code if isinstance(failure, ManagementError) else 5,
                      {"backup": str(backup) if backup else None, "config_changed": committed})
