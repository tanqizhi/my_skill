# -*- coding: utf-8 -*-

from __future__ import print_function

import datetime
import os
import re


MORE_PROMPTS = [
    "---- More ----",
    "---- More ---- ",
    "--More--",
    "-- More --",
    "More:",
    "Press Q to quit",
]
COMMAND_TIMEOUT = 30

try:
    text_type = unicode
except NameError:
    text_type = str


def _clean_output(value):
    if value is None:
        return ""
    value = value.replace("\x08", "")
    value = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", value)
    return value.strip()


def _prompt_value(crt, field, cache):
    key = field[0]
    label = field[1]
    example = field[2] if len(field) > 2 else ""
    if key in cache:
        return cache[key]
    value = crt.Dialog.Prompt(label, "查询参数", example, False)
    if value is None or not value.strip():
        raise ValueError("未填写必需参数：{0}".format(label))
    cache[key] = value.strip()
    return cache[key]


def _render_commands(crt, operation, cache, base_prompt):
    values = {}
    for field in operation.get("fields", []):
        values[field[0]] = _prompt_value(crt, field, cache)
    values["base_prompt"] = base_prompt
    rendered = []
    for command in operation["commands"]:
        if isinstance(command, dict):
            rendered.append((
                command["text"].format(**values),
                command.get("expect", "{base_prompt}").format(**values),
            ))
        else:
            rendered.append((command.format(**values), base_prompt))
    return rendered


def _run_command(crt, command, expected_prompt):
    screen = crt.Screen
    screen.Send(command + "\r")
    chunks = []
    targets = [expected_prompt] + MORE_PROMPTS

    while True:
        chunk = screen.ReadString(targets, COMMAND_TIMEOUT)
        chunks.append(chunk)
        match_index = screen.MatchIndex
        if match_index == 1:
            return "成功", _clean_output("".join(chunks))
        if match_index > 1:
            screen.Send(" ")
            continue
        return "超时或未识别到提示符", _clean_output("".join(chunks))


def _choose_operations(crt, operations, allow_multiple):
    lines = []
    if allow_multiple:
        lines.append("0. 执行全部查询")
    for index, operation in enumerate(operations, 1):
        lines.append("{0}. {1}".format(index, operation["name"]))
    if allow_multiple:
        message = "请输入序号，多个序号用英文逗号分隔：\n\n" + "\n".join(lines)
        default_value = "0"
    else:
        message = "请输入一个查询序号：\n\n" + "\n".join(lines)
        default_value = "1"
    value = crt.Dialog.Prompt(message, "选择查询项目", default_value, False)
    if value is None:
        return []
    value = value.strip()
    if allow_multiple and value == "0":
        return operations
    if not allow_multiple and "," in value:
        raise ValueError("该设备脚本一次只允许执行一个查询项目。")

    selected = []
    seen = set()
    for item in value.split(","):
        item = item.strip()
        if not item.isdigit():
            raise ValueError("无效序号：{0}".format(item))
        index = int(item)
        if index < 1 or index > len(operations):
            raise ValueError("序号超出范围：{0}".format(index))
        if index not in seen:
            selected.append(operations[index - 1])
            seen.add(index)
    return selected


def _build_report(settings, ticket, prompt, parameter_cache, results):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "【采集信息】",
        "工单编号: {0}".format(ticket or "未填写"),
        "当前系统: {0}".format(settings["system"]),
        "厂家: {0}".format(settings["vendor"]),
        "设备类型: {0}".format(settings["device_type"]),
        "设备提示符: {0}".format(prompt),
        "采集时间: {0}".format(now),
        "",
        "【查询对象】",
    ]
    if parameter_cache:
        parameter_labels = {
            "username": "用户名",
            "user_ip": "用户IP地址",
            "mac": "用户MAC地址",
        }
        for key in sorted(parameter_cache):
            lines.append("{0}: {1}".format(parameter_labels.get(key, key), parameter_cache[key]))
    else:
        lines.append("无")

    failed = []
    for index, result in enumerate(results, 1):
        lines.extend([
            "",
            "【检查结果 {0}】".format(index),
            "查询用途: {0}".format(result["name"]),
            "执行状态: {0}".format(result["status"]),
            "执行命令: {0}".format(result["command"]),
            "设备回显:",
            result["output"] or "无回显",
        ])
        if result["status"] != "成功":
            failed.append("{0}: {1}".format(result["name"], result["command"]))

    lines.extend(["", "【执行失败项】"])
    lines.extend(failed or ["无"])
    lines.extend([
        "",
        "【脚本规则提示】",
        "脚本仅采集设备回显，不自动执行配置变更，也不把缺失回显视为正常。",
    ])
    return "\r\n".join(lines) + "\r\n"


def _write_utf8(path, content):
    if not isinstance(content, bytes):
        content = content.encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(content)


def _save_results(crt, settings, ticket, prompt, parameter_cache, results):
    report = _build_report(settings, ticket, prompt, parameter_cache, results)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "securecrt_{0}_{1}_{2}.txt".format(
        settings["vendor_id"], settings["device_id"], timestamp
    )
    default_path = os.path.join(os.path.expanduser("~/Desktop"), filename)
    save_path = crt.Dialog.Prompt("请输入查询结果保存路径：", "保存结果", default_path, False)
    if save_path is None or not save_path.strip():
        return
    save_path = os.path.expandvars(os.path.expanduser(save_path.strip()))
    _write_utf8(save_path, report)
    crt.Dialog.MessageBox("查询完成，结果已保存到：\n{0}".format(save_path), "完成", 0)


def _collect_mse_user_info(crt):
    fields = [
        ("username", "请输入用户名（没有可留空）："),
        ("user_ip", "请输入用户IP地址（没有可留空）："),
        ("mac", "请输入用户MAC地址（没有可留空）："),
    ]
    values = {}
    for key, message in fields:
        value = crt.Dialog.Prompt(message, "MSE用户信息", "", False)
        if value is None:
            return None
        value = value.strip()
        if value:
            values[key] = value
    if not values:
        crt.Dialog.MessageBox("用户名、用户IP地址、用户MAC地址至少需要填写一项。", "缺少用户信息", 0)
        return None
    return values


def run_mse_script(crt, settings, searches):
    if not crt.Session.Connected:
        crt.Dialog.MessageBox("当前 SecureCRT 会话尚未连接设备。", "无法执行", 0)
        return

    user_info = _collect_mse_user_info(crt)
    if user_info is None:
        return

    crt.Screen.Synchronous = True
    try:
        prompt = crt.Dialog.Prompt(
            "请输入设备命令行提示符，必须与设备回显完全一致。\n例如：<MSE-01>、ZXR10# 或 <H3C-MSE>",
            "设备提示符",
            "",
            False,
        )
        if prompt is None or not prompt.strip():
            return
        prompt = prompt.strip()
        ticket = crt.Dialog.Prompt("请输入工单编号（可留空）：", "工单信息", "", False)

        results = []
        for key in ("username", "user_ip", "mac"):
            if key not in user_info:
                continue
            for operation in searches.get(key, []):
                commands = _render_commands(crt, operation, user_info, prompt)
                for command, expected_prompt in commands:
                    status, output = _run_command(crt, command, expected_prompt)
                    results.append({
                        "name": operation["name"],
                        "command": command,
                        "status": status,
                        "output": output,
                    })

        _save_results(crt, settings, ticket, prompt, user_info, results)
    except Exception as error:
        crt.Dialog.MessageBox("脚本执行失败：\n{0}".format(error), "错误", 0)
    finally:
        crt.Screen.Synchronous = False


def run_script(crt, settings, operations):
    if not crt.Session.Connected:
        crt.Dialog.MessageBox("当前 SecureCRT 会话尚未连接设备。", "无法执行", 0)
        return

    crt.Screen.Synchronous = True
    try:
        if settings.get("mode_warning"):
            crt.Dialog.MessageBox(settings["mode_warning"], "执行前提示", 0)
        prompt = crt.Dialog.Prompt(
            "请输入设备命令行提示符，必须与设备回显完全一致。\n例如：<MSE-01>、<SR-01> 或 ZXR10#",
            "设备提示符",
            "",
            False,
        )
        if prompt is None or not prompt.strip():
            return
        prompt = prompt.strip()

        ticket = crt.Dialog.Prompt("请输入工单编号（可留空）：", "工单信息", "", False)
        selected = _choose_operations(crt, operations, settings.get("allow_multiple", True))
        if not selected:
            return

        parameter_cache = {}
        results = []
        for operation in selected:
            if operation.get("precondition"):
                crt.Dialog.MessageBox(operation["precondition"], "查询前提", 0)
            commands = _render_commands(crt, operation, parameter_cache, prompt)
            for command, expected_prompt in commands:
                status, output = _run_command(crt, command, expected_prompt)
                results.append({
                    "name": operation["name"],
                    "command": command,
                    "status": status,
                    "output": output,
                })

        _save_results(crt, settings, ticket, prompt, parameter_cache, results)
    except Exception as error:
        crt.Dialog.MessageBox("脚本执行失败：\n{0}".format(error), "错误", 0)
    finally:
        crt.Screen.Synchronous = False
