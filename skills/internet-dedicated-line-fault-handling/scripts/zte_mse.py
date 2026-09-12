#$language = "Python"
#$interface = "1.0"

import os
import sys

import datetime
import re

MORE_PROMPTS = ["---- More ----", "---- More ---- ", "--More--", "-- More --", "More:", "Press Q to quit"]

try:
    text_type = unicode
except NameError:
    text_type = str


def to_unicode(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    try:
        return text_type(value)
    except Exception:
        return repr(value).decode("utf-8", "replace")


def clean_output(value):
    value = (value or "").replace("\x08", "")
    return re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", value).strip()


def collect_user_info(crt):
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


def run_command(crt, command, prompt):
    crt.Screen.Send(command + "\r")
    chunks = []
    targets = [prompt] + MORE_PROMPTS
    while True:
        chunks.append(crt.Screen.ReadString(targets, 30))
        if crt.Screen.MatchIndex == 1:
            return "成功", clean_output("".join(chunks))
        if crt.Screen.MatchIndex > 1:
            crt.Screen.Send(" ")
            continue
        return "超时或未识别到提示符", clean_output("".join(chunks))


def save_report(crt, settings, ticket, prompt, user_info, results):
    labels = {"username": "用户名", "user_ip": "用户IP地址", "mac": "用户MAC地址"}
    lines = [
        "【采集信息】",
        "工单编号: {0}".format(ticket or "未填写"),
        "当前系统: MSE",
        "厂家: {0}".format(settings["vendor"]),
        "设备提示符: {0}".format(prompt),
        "采集时间: {0}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "",
        "【查询对象】",
    ]
    for key in ("username", "user_ip", "mac"):
        if key in user_info:
            lines.append("{0}: {1}".format(labels[key], user_info[key]))
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
    lines.extend(["", "【脚本规则提示】", "脚本仅采集设备回显，不自动执行配置变更，也不把缺失回显视为正常。"])
    report = u"\r\n".join([to_unicode(line) for line in lines]) + u"\r\n"
    filename = "securecrt_{0}_mse_{1}.txt".format(
        settings["vendor_id"], datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    path = crt.Dialog.Prompt(
        "请输入查询结果保存路径：",
        "保存结果",
        os.path.join(os.path.expanduser("~/Desktop"), filename),
        False,
    )
    if path is None or not path.strip():
        return
    path = os.path.expandvars(os.path.expanduser(path.strip()))
    data = report.encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(data)
    crt.Dialog.MessageBox(
        to_unicode("查询完成，结果已保存到：\n{0}").format(to_unicode(path)),
        to_unicode("完成"),
        0,
    )


def main(crt, settings, searches):
    if not crt.Session.Connected:
        crt.Dialog.MessageBox("当前 SecureCRT 会话尚未连接设备。", "无法执行", 0)
        return
    user_info = collect_user_info(crt)
    if user_info is None:
        return
    prompt = crt.Dialog.Prompt(
        "请输入设备命令行提示符，必须与设备回显完全一致：",
        "设备提示符",
        "",
        False,
    )
    if prompt is None or not prompt.strip():
        return
    prompt = prompt.strip()
    ticket = crt.Dialog.Prompt("请输入工单编号（可留空）：", "工单信息", "", False)
    crt.Screen.Synchronous = True
    try:
        results = []
        for key in ("username", "user_ip", "mac"):
            if key not in user_info:
                continue
            for item in searches.get(key, []):
                for template in item["commands"]:
                    command = template.format(**user_info)
                    status, output = run_command(crt, command, prompt)
                    results.append({
                        "name": item["name"],
                        "command": command,
                        "status": status,
                        "output": output,
                    })
        save_report(crt, settings, ticket, prompt, user_info, results)
    except Exception as error:
        crt.Dialog.MessageBox(
            to_unicode("脚本执行失败：\n{0}").format(to_unicode(error)),
            to_unicode("错误"),
            0,
        )
    finally:
        crt.Screen.Synchronous = False


SETTINGS = {"system": "MSE", "vendor": "中兴", "device_type": "MSE", "vendor_id": "zte", "device_id": "mse"}

SEARCHES = {
    "username": [
        {"name": "基于username查看用户是否在线", "fields": [("username", "用户名", "")], "commands": ["show subscriber user-name {username}"]},
        {"name": "基于username查看用户上线失败记录", "fields": [("username", "用户名", "")], "commands": ["show online-fail-record user-name {username}"]},
        {"name": "基于username查看用户下线记录", "fields": [("username", "用户名", "")], "commands": ["show offline-exception-record user-name {username}"]},
    ],
    "user_ip": [
        {"name": "基于用户IP地址查看用户是否在线", "fields": [("user_ip", "用户IP地址", "")], "commands": ["show subscriber ipv4-address {user_ip}"]},
    ],
    "mac": [
        {"name": "基于用户MAC地址查看用户是否在线", "fields": [("mac", "用户MAC地址", "")], "commands": ["show subscriber user-mac {mac}"]},
        {"name": "基于用户MAC地址查看用户上线失败记录", "fields": [("mac", "用户MAC地址", "")], "commands": ["show online-fail-record user-mac {mac}"]},
        {"name": "基于用户MAC地址查看用户下线记录", "fields": [("mac", "用户MAC地址", "")], "commands": ["show offline-exception-record user-mac {mac}"]},
    ],
}

main(crt, SETTINGS, SEARCHES)
