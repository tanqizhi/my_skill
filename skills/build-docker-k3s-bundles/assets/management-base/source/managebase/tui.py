"""Small curses front end. All business operations live in operations.py."""

import curses
import locale
from pathlib import Path
import signal
import time
from dataclasses import replace

from .cli import format_result
from .operations import COMMANDS, execute
from . import backups, changes, compose, firewall_rules, image_import, image_table, images, lifecycle, location_table, network_tables
from .layout import Installation
from .model import ManagementError
from .status_table import cell_slice, cell_width, padded, table_data, text_width


MENU_GROUPS = (
    ("查询", (
        ("status", "容器状态"),
        ("image-versions", "容器镜像版本"),
        ("locations", "容器相关位置"),
        ("exposed-ports", "对外暴露端口"),
        ("docker-firewall", "Docker 转发防火墙"),
        ("doctor", "工具环境"),
        ("layout", "安装目录检查"),
    )),
    ("操作", (
        ("start", "启动容器"),
        ("stop", "停止容器"),
        ("restart", "重启容器"),
        ("image-import", "导入镜像"),
        ("image-switch", "服务切换镜像"),
        ("service-add", "增加服务"),
        ("config-check", "校验 Compose"),
        ("backup-compose", "备份现有 Compose 文件"),
        ("backup-data", "备份现有数据文件"),
        ("firewall-add", "防火墙管理"),
    )),
)
MENU_ENTRIES = (
    ("root", "安装根目录"),
    *(entry for _, entries in MENU_GROUPS for entry in entries),
    ("exit", "退出"),
)


def entry_detail(command: str, label: str, root: Path) -> str:
    if command in COMMANDS:
        return format_result(execute(command, root))
    return f"{label}\n\n待实现\n\n未执行任何操作。"


def clipped(text: str, width: int) -> str:
    result = ""
    used = 0
    for char in text:
        if not char.isprintable():
            continue
        size = cell_width(char)
        if used + size > width:
            break
        result += char
        used += size
    return result


def wrap_lines(text: str, width: int) -> list[str]:
    lines = []
    for line in text.splitlines() or [""]:
        current = ""
        used = 0
        for char in line:
            if not char.isprintable():
                continue
            size = cell_width(char)
            if used + size > width and current:
                lines.append(current)
                current, used = "", 0
            current += char
            used += size
        lines.append(current)
    return lines


def put(screen, y: int, x: int, text: str, style: int = 0) -> None:
    height, width = screen.getmaxyx()
    if not (0 <= y < height and 0 <= x < width - 1):
        return
    try:
        screen.addstr(y, x, clipped(text, width - x - 1), style)
    except curses.error:
        pass


def set_cursor(visible: bool) -> None:
    try:
        curses.curs_set(int(visible))
    except curses.error:
        pass


def edit_root(screen, initial: str) -> str | None:
    return edit_text(screen, initial, "安装根目录")


def edit_text(screen, initial: str, title: str) -> str | None:
    value, cursor = initial, len(initial)
    set_cursor(True)
    try:
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            if height < 8 or width < 32:
                put(screen, 0, 0, "终端尺寸不足")
                screen.refresh()
                key = screen.get_wch()
                if key == "\x1b":
                    return None
                continue
            put(screen, 1, 2, title, curses.A_BOLD)
            available = width - 6
            start = cursor
            cells = 0
            while start > 0 and cells + cell_width(value[start - 1]) < available:
                start -= 1
                cells += cell_width(value[start])
            put(screen, 3, 2, value[start:], curses.A_UNDERLINE)
            put(screen, 5, 2, "Enter 确定 | Esc 取消")
            screen.move(3, 2 + cells)
            screen.refresh()
            key = screen.get_wch()
            if key in ("\n", "\r", curses.KEY_ENTER):
                if value.startswith("/"):
                    return value
            elif key == "\x1b":
                return None
            else:
                value, cursor = edit_key(value, cursor, key)
    finally:
        set_cursor(False)


def edit_key(value, cursor, key):
    if key == curses.KEY_LEFT:
        cursor = max(0, cursor - 1)
    elif key == curses.KEY_RIGHT:
        cursor = min(len(value), cursor + 1)
    elif key in (curses.KEY_HOME, "\x01"):
        cursor = 0
    elif key in (curses.KEY_END, "\x05"):
        cursor = len(value)
    elif key in ("\b", "\x7f", curses.KEY_BACKSPACE):
        if cursor:
            value = value[:cursor - 1] + value[cursor:]
            cursor -= 1
    elif key == curses.KEY_DC:
        value = value[:cursor] + value[cursor + 1:]
    elif key == "\x15":
        value, cursor = "", 0
    elif isinstance(key, str) and key.isprintable() and len(value) < 4096:
        value = value[:cursor] + key + value[cursor:]
        cursor += 1
    return value, cursor


def status_view(screen, services: list[dict]) -> None:
    table_view(screen, "容器状态", table_data(services), "没有容器")


def images_view(screen, images: list[dict]) -> None:
    table_view(screen, "本机镜像", image_table.table_data(images), "没有本地镜像")


def table_view(screen, title: str, data: tuple, empty: str, *, footer: str = "时间 UTC") -> None:
    headings, rows, widths = data
    page, horizontal = 0, 0
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 12 or width < 64:
            put(screen, 0, 0, "表格至少需要 64 列、12 行；Esc 返回")
            screen.refresh()
            if screen.get_wch() == "\x1b":
                return
            continue
        page_size = height - 9
        pages = max(1, (len(rows) + page_size - 1) // page_size)
        page = min(page, pages - 1)
        pinned = min(widths[0], max(12, width // 3))
        available = width - pinned - 7
        content_width = sum(widths[1:]) + 3 * (len(widths) - 2)
        horizontal = min(horizontal, max(0, content_width - available))
        put(screen, 1, 2, f"{title} | 共 {len(rows)} 条 | 第 {page + 1}/{pages} 页",
            curses.A_BOLD)

        def draw(y, values, style=0):
            name = values[0]
            if sum(cell_width(char) for char in name) > pinned:
                name = clipped(name, pinned - 1) + "…"
            put(screen, y, 2, padded(name, pinned) + " │ ", style)
            tail = " | ".join(padded(value, size)
                              for value, size in zip(values[1:], widths[1:]))
            put(screen, y, pinned + 5, cell_slice(tail, horizontal, available), style)

        draw(3, headings, curses.A_BOLD)
        put(screen, 4, 2, "─" * (width - 4))
        for index, row in enumerate(rows[page * page_size:(page + 1) * page_size]):
            draw(5 + index, row)
        if not rows:
            put(screen, 5, 2, empty)
        put(screen, height - 3, 2, "↑ 上一页 | ↓ 下一页 | Esc 返回上级", curses.A_BOLD)
        put(screen, height - 2, 2, f"← / → 横向移动 | {footer}")
        screen.refresh()
        key = screen.get_wch()
        if key == "\x1b":
            return
        if key == curses.KEY_DOWN:
            page = min(pages - 1, page + 1)
        elif key == curses.KEY_UP:
            page = max(0, page - 1)
        elif key == curses.KEY_RIGHT:
            horizontal += max(1, available // 2)
        elif key == curses.KEY_LEFT:
            horizontal = max(0, horizontal - max(1, available // 2))


def text_view(screen, title: str, detail: str) -> None:
    lines = detail.splitlines() or [""]
    content_width = max(sum(cell_width(char) for char in line) for line in lines)
    page, horizontal = 0, 0
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 12 or width < 64:
            put(screen, 0, 0, "结果页至少需要 64 列、12 行；Esc 返回")
            screen.refresh()
            if screen.get_wch() == "\x1b":
                return
            continue
        page_size = height - 7
        pages = max(1, (len(lines) + page_size - 1) // page_size)
        page = min(page, pages - 1)
        available = width - 4
        horizontal = min(horizontal, max(0, content_width - available))
        put(screen, 1, 2, f"{title} | 第 {page + 1}/{pages} 页", curses.A_BOLD)
        for index, line in enumerate(lines[page * page_size:(page + 1) * page_size]):
            put(screen, 3 + index, 2, cell_slice(line, horizontal, available))
        put(screen, height - 3, 2, "↑ 上一页 | ↓ 下一页 | Esc 返回上级", curses.A_BOLD)
        put(screen, height - 2, 2, "← / → 横向移动")
        screen.refresh()
        key = screen.get_wch()
        if key == "\x1b":
            return
        if key == curses.KEY_DOWN:
            page = min(pages - 1, page + 1)
        elif key == curses.KEY_UP:
            page = max(0, page - 1)
        elif key == curses.KEY_RIGHT:
            horizontal += max(1, available // 2)
        elif key == curses.KEY_LEFT:
            horizontal = max(0, horizontal - max(1, available // 2))


def menu_geometry(width: int) -> tuple[list, dict[int, tuple[int, int]], int]:
    columns = min(3, max(2, (width - 4) // 38))
    rows = [[0]]
    index = 1
    for title, entries in MENU_GROUPS:
        rows.append(title)
        for start in range(0, len(entries), columns):
            rows.append(list(range(index + start, index + min(start + columns, len(entries)))))
        index += len(entries)
    rows.append([len(MENU_ENTRIES) - 1])
    positions = {entry: (row, column) for row, items in enumerate(rows) if isinstance(items, list)
                 for column, entry in enumerate(items)}
    return rows, positions, columns


def choose(screen, title, details, options, *, selected=0, searchable=False):
    horizontal = 0
    query = ""
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 16 or width < 64:
            put(screen, 0, 0, "终端至少需要 64 列、16 行；Esc 返回")
            screen.refresh()
            if screen.get_wch() == "\x1b":
                return None
            continue
        put(screen, 1, 2, title, curses.A_BOLD)
        shown_details = [*details[:2], "搜索：" + query] if searchable else details[:3]
        for index, line in enumerate(shown_details):
            put(screen, 3 + index, 2, cell_slice(line, horizontal, width - 4))
        visible = [index for index, option in enumerate(options) if query.casefold() in option.casefold()]
        selected = min(selected, max(0, len(visible) - 1))
        page_size = height - 10
        offset = selected // page_size * page_size
        put(screen, 6, 2, "─" * (width - 4))
        for index, original in enumerate(visible[offset:offset + page_size]):
            label = options[original]
            option_offset = min(horizontal, max(0, text_width(label) - (width - 6)))
            put(screen, 7 + index, 2, padded(cell_slice(label, option_offset, width - 6), width - 4),
                curses.A_REVERSE if offset + index == selected else 0)
        put(screen, height - 2, 2,
            f"↑ ↓ 选择 {selected + 1 if visible else 0}/{len(visible)} | ← → 横移 | Enter 进入 | Esc 返回",
            curses.A_BOLD)
        if not visible:
            put(screen, 7, 2, "没有匹配项")
        screen.refresh()
        key = screen.get_wch()
        if key == "\x1b":
            return None
        if key in ("\n", "\r", curses.KEY_ENTER):
            if visible:
                return visible[selected]
            continue
        if key == curses.KEY_DOWN:
            selected = min(max(0, len(visible) - 1), selected + 1)
        elif key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_LEFT:
            horizontal = max(0, horizontal - 16)
        elif key == curses.KEY_RIGHT:
            maximum = max([0, *(text_width(line) for line in [*shown_details, *options])])
            horizontal = min(max(0, maximum - (width - 6)), horizontal + 16)
        elif searchable:
            if key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                query, selected = query[:-1], 0
            elif key == "\x15":
                query, selected = "", 0
            elif isinstance(key, str) and key.isprintable() and len(query) < 256:
                query, selected = query + key, 0


def execution_progress(screen, label, *, footer="执行完毕自动返回主菜单"):
    history = []
    started = time.monotonic()

    def progress(message, tick):
        if not tick or not history or history[-1] != message:
            history.append(message)
            del history[:-200]
        screen.erase()
        height, width = screen.getmaxyx()
        put(screen, 1, 2, f"{label} / 执行中 | {int(time.monotonic() - started)} 秒",
            curses.A_BOLD)
        for index, line in enumerate(history[-max(1, height - 6):]):
            put(screen, 3 + index, 2, line)
        put(screen, height - 2, 2, footer)
        screen.refresh()

    return progress


def flush_input():
    try:
        curses.flushinp()
    except curses.error:
        pass


def input_form(screen, title, fields, *, notes=(), confirm="确认", validators=()):
    values = [value for _, value in fields]
    selected, editing, cursor, horizontal = len(fields) + 1, False, 0, 0
    error, saved = "", ""
    try:
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            if height < 16 or width < 64:
                set_cursor(False)
                put(screen, 0, 0, "终端至少需要 64 列、16 行；Esc 返回")
                screen.refresh()
                if screen.get_wch() == "\x1b":
                    return None
                continue
            put(screen, 1, 2, title, curses.A_BOLD)
            for index, (label, _) in enumerate(fields):
                prefix = label + "："
                available = max(1, width - 6 - text_width(prefix))
                value = values[index]
                start, cells = 0, 0
                if editing and selected == index:
                    start = cursor
                    while start > 0 and cells + cell_width(value[start - 1]) < available:
                        start -= 1
                        cells += cell_width(value[start])
                    cursor_x = 2 + text_width(prefix) + cells
                    visible = value[start:]
                else:
                    offset = min(horizontal, max(0, text_width(value) - available))
                    visible = cell_slice(value, offset, available)
                put(screen, 3 + 2 * index, 2,
                    padded(prefix + clipped(visible, available), width - 4),
                    curses.A_REVERSE if selected == index else 0)
            for index, note in enumerate(notes[:3]):
                offset = min(horizontal, max(0, text_width(note) - (width - 4)))
                put(screen, 7 + index, 2, cell_slice(note, offset, width - 4))
            for index, label in enumerate((confirm, "返回"), len(fields)):
                put(screen, 10 + index - len(fields), 2, padded(label, width - 4),
                    curses.A_REVERSE if selected == index else 0)
            put(screen, 12, 2, error)
            put(screen, height - 2, 2, "输入内容 | ← → 光标 | Enter 保存 | Esc 取消编辑" if editing else
                "↑↓ 选择 | ←→ 横移 | Enter 编辑/确认 | Esc 返回", curses.A_BOLD)
            set_cursor(editing)
            if editing:
                screen.move(3 + 2 * selected, cursor_x)
            screen.refresh()
            key = screen.get_wch()
            if editing:
                if key == "\x1b":
                    values[selected], editing = saved, False
                elif key in ("\n", "\r", curses.KEY_ENTER):
                    editing = False
                else:
                    values[selected], cursor = edit_key(values[selected], cursor, key)
                continue
            if key == "\x1b":
                return None
            if key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(len(fields) + 1, selected + 1)
            elif key == curses.KEY_LEFT:
                horizontal = max(0, horizontal - 16)
            elif key == curses.KEY_RIGHT:
                horizontal = min(max([0, *(text_width(v) for v in [*values, *notes])]), horizontal + 16)
            elif key in ("\n", "\r", curses.KEY_ENTER):
                if selected == len(fields) + 1:
                    return None
                if selected < len(fields):
                    editing, saved, cursor = True, values[selected], len(values[selected])
                else:
                    try:
                        for validate, value in zip(validators, values):
                            validate(value)
                        return tuple(values)
                    except ManagementError as failure:
                        error = str(failure)
    finally:
        set_cursor(False)


def absolute_input(value):
    if not value.startswith("/"):
        raise ManagementError("请输入完整绝对路径。", 2)


def firewall_form(screen, values):
    row, column, editing, cursor, saved, error = 0, 0, False, 0, "", ""
    protocols, actions = ("IP", "tcp", "udp", "icmp"), ("ACCEPT", "REJECT")
    try:
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            if height < 16 or width < 64:
                set_cursor(False)
                put(screen, 0, 0, "终端至少需要 64 列、16 行；Esc 返回")
                screen.refresh()
                if screen.get_wch() == "\x1b":
                    return None
                continue
            has_ports = values["protocol"] in ("tcp", "udp")
            if not has_ports:
                column = 0
            put(screen, 1, 2, "防火墙管理 / 添加 DOCKER-USER 规则", curses.A_BOLD)
            fields = {0: [("position", "添加到第 X 行")],
                      2: [("source", "源地址")] + ([("source_port", "源端口")] if has_ports else []),
                      3: [("destination", "目标地址")] + ([("destination_port", "目标端口")] if has_ports else [])}
            for index, entries in fields.items():
                span = (width - 4) // len(entries)
                for col, (name, label) in enumerate(entries):
                    x, y = 2 + col * span, 3 + index
                    prefix = label + "："
                    available = max(1, span - text_width(prefix) - 2)
                    value = values[name]
                    active = row == index and column == col
                    if active and editing:
                        start, cells = cursor, 0
                        while start > 0 and cells + cell_width(value[start - 1]) < available:
                            start -= 1
                            cells += cell_width(value[start])
                        visible = value[start:]
                        cursor_position = (y, x + text_width(prefix) + cells)
                    else:
                        visible = value or "任意"
                    put(screen, y, x, padded(prefix + clipped(visible, available), span - 1),
                        curses.A_REVERSE if active else 0)
            for index, key, choices, labels in (
                (1, "protocol", protocols, protocols),
                (4, "action", actions, ("通过", "拒绝")),
            ):
                put(screen, 3 + index, 2, "协议类型：" if index == 1 else "动作：")
                x = 14
                for choice, label in zip(choices, labels):
                    text = ("[x] " if values[key] == choice else "[ ] ") + label
                    put(screen, 3 + index, x, text,
                        curses.A_REVERSE if row == index and values[key] == choice else 0)
                    x += text_width(text) + 3
            put(screen, 8, 2, "确认添加", curses.A_REVERSE if row == 5 else 0)
            put(screen, 10, 2, "主机级 filter / DOCKER-USER；匹配 DNAT 后地址和端口")
            put(screen, 11, 2, "-1=链尾；前置终止规则可能阻断；不自动持久化")
            put(screen, 12, 2, "IP=所有协议；地址支持 CIDR；端口留空=任意")
            put(screen, height - 3, 2, error)
            put(screen, height - 2, 2, "输入文字 | ←→ 光标 | Enter 保存 | Esc 取消编辑" if editing else
                "↑↓ 选择行 | ←→ 选择项 | Enter 编辑/确认 | Esc 返回", curses.A_BOLD)
            set_cursor(editing)
            if editing:
                screen.move(*cursor_position)
            screen.refresh()
            key = screen.get_wch()
            if editing:
                field = fields[row][column][0]
                if key == "\x1b":
                    values[field], editing = saved, False
                elif key in ("\n", "\r", curses.KEY_ENTER):
                    editing = False
                else:
                    values[field], cursor = edit_key(values[field], cursor, key)
                continue
            if key == "\x1b":
                return None
            if key in (curses.KEY_UP, curses.KEY_DOWN):
                row = max(0, min(5, row + (1 if key == curses.KEY_DOWN else -1)))
                column = 0
            elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                step = 1 if key == curses.KEY_RIGHT else -1
                if row in (1, 4):
                    field, choices = ("protocol", protocols) if row == 1 else ("action", actions)
                    values[field] = choices[max(0, min(len(choices) - 1, choices.index(values[field]) + step))]
                    if values["protocol"] in ("IP", "icmp"):
                        values["source_port"] = values["destination_port"] = ""
                elif row in (2, 3):
                    column = max(0, min(1 if has_ports else 0, column + step))
            elif key in ("\n", "\r", curses.KEY_ENTER):
                if row in fields:
                    field = fields[row][column][0]
                    editing, saved, cursor = True, values[field], len(values[field])
                elif row in (1, 4):
                    row += 1
                elif row == 5:
                    try:
                        return firewall_rules.Rule.parse(**values)
                    except ManagementError as failure:
                        error = str(failure)
    finally:
        set_cursor(False)


def firewall_add_view(screen, root):
    values = {"position": "-1", "protocol": "IP", "source": "", "source_port": "",
              "destination": "", "destination_port": "", "action": "REJECT"}
    while True:
        rule = firewall_form(screen, values)
        if rule is None:
            return "主菜单"
        try:
            installation = Installation.load(root)
            plan = firewall_rules.prepare(installation, rule)
            summary = plan.summary()
            selected = choose(
                screen, "DOCKER-USER / 最终确认",
                [f"IPv{rule.family} 第 {summary['effective_position']} 行 | {rule.protocol} | {rule.action}",
                 f"{rule.source} 端口 {rule.source_port or '任意'} -> "
                 f"{rule.destination} 端口 {rule.destination_port or '任意'}",
                 "影响主机 Docker 转发（包括其他项目）；仅运行时生效"],
                ["确认添加", "返回"], selected=1)
            if selected != 0:
                continue
            progress = execution_progress(screen, "添加防火墙规则")
            result = firewall_rules.apply(plan, confirmed=True, progress=progress)
            flush_input()
            text_view(screen, "防火墙添加结果", format_result(result))
            return result.summary
        except ManagementError as error:
            text_view(screen, "防火墙预检查", str(error))


def image_switch_view(screen, root):
    try:
        installation = Installation.load(root)
        configured = compose.configuration(installation)["services"]
        names = sorted({r["service"] for r in compose.services(installation)} & set(configured))
        if not names:
            text_view(screen, "服务切换镜像", "没有已创建容器的服务。")
            return "没有可切换的服务。"
        service_index = 0
        while True:
            service_index = choose(screen, "服务切换镜像 / 选择服务", [str(root)],
                                   names, selected=service_index)
            if service_index is None:
                return "主菜单"
            service = names[service_index]
            inventory = images.inventory(installation)
            options = [f"{i['repository']}:{i['tag']} | {i['size']} | {i['id']}" for i in inventory]
            if not options:
                text_view(screen, "选择镜像", "本机没有镜像。")
                continue
            selected = 0
            while True:
                selected = choose(screen, "服务切换镜像 / 选择镜像", [f"服务：{service}", str(root)],
                                  options, selected=selected, searchable=True)
                if selected is None:
                    break
                image = inventory[selected]
                label = (f"{image['repository']}:{image['tag']}"
                         if image["repository"] != "<none>" else image["id"])
                try:
                    plan = changes.prepare_switch(installation, service, image["id"])
                    plan = replace(plan, image_label=label)
                except ManagementError as error:
                    text_view(screen, "切换预检查", str(error))
                    continue
                confirmation = choose(screen, "服务切换镜像 / 最终确认",
                                      [f"服务：{service}", f"目标镜像：{label}",
                                       "将仅重建并启动所选服务；原配置先备份"],
                                      ["确认切换", "返回"], selected=1)
                if confirmation != 0:
                    continue
                progress = execution_progress(screen, "切换镜像")
                progress("正在重新核对所选服务和镜像…", False)
                result = changes.apply(plan, confirmed=True, progress=progress)
                flush_input()
                if result.code:
                    text_view(screen, "切换镜像结果", format_result(result))
                return result.summary
    except ManagementError as error:
        text_view(screen, "服务切换镜像", str(error))
        return str(error)


def service_add_view(screen, root):
    values = ("", "")
    while True:
        fields = [("服务名", values[0]), ("Compose 文件路径", values[1])]
        entered = input_form(screen, "增加服务 / 服务信息", fields,
                             notes=("从源文件读取同名服务；写入固定 override", "创建容器但不启动，不拉取或构建镜像"),
                             confirm="校验并继续", validators=(changes.service_name, absolute_input))
        if entered is None:
            return "主菜单"
        values = entered
        try:
            installation = Installation.load(root)
            progress = execution_progress(screen, "新增服务校验", footer="校验完成后进入确认页")
            progress("正在校验源 Compose 和固定目录…", False)
            plan = changes.prepare_add(installation, values[0], Path(values[1]))
            selected = choose(screen, "增加服务 / 最终确认",
                              [f"服务：{plan.service}", f"镜像：{plan.image_label}",
                               "保存到固定 override，并创建未启动容器"],
                              ["确认添加", "返回"], selected=1)
            if selected != 0:
                continue
            progress = execution_progress(screen, "增加服务")
            progress("正在创建所选服务（不启动）…", False)
            result = changes.apply(plan, confirmed=True, progress=progress)
            flush_input()
            if result.code:
                text_view(screen, "增加服务结果", format_result(result))
            return result.summary
        except ManagementError as error:
            text_view(screen, "增加服务校验失败", str(error))


def backup_view(screen, root, command):
    try:
        installation = Installation.load(root)
        names = backups.service_list(installation)
        if not names:
            text_view(screen, "备份", "没有可备份的服务。")
            return "没有可备份的服务。"
        selected = 0
        while True:
            selected = choose(screen, f"{backups.COMMANDS[command]} / 选择服务", [str(root)],
                              names + ["我全都要"], selected=selected)
            if selected is None:
                return "主菜单"
            try:
                plan = backups.prepare(installation, command,
                                       service=names[selected] if selected < len(names) else None,
                                       all_services=selected == len(names))
                if not plan.sources:
                    text_view(screen, "备份数据文件", "所选服务不涉及持久化数据文件，无需备份。")
                    continue
                entered = input_form(
                    screen, f"{backups.COMMANDS[command]} / 备份路径",
                    [("备份路径", str(plan.default_path()))],
                    notes=("服务：" + "、".join(plan.services), "自动打包成 tar.gz；不会覆盖已有文件",
                           "在线快照，不保证数据库事务一致性" if command == "backup-data"
                           else "Compose 为共享文件，原样备份完整文件"),
                    confirm="确认备份", validators=(absolute_input,))
                if entered is None:
                    continue
                progress = execution_progress(screen, "备份", footer="完成后显示备份路径")
                progress("正在检查备份来源及输出路径…", False)
                result = backups.apply(plan, entered[0], confirmed=True, progress=progress)
                flush_input()
                text_view(screen, "备份结果", format_result(result))
                return result.summary
            except ManagementError as error:
                text_view(screen, "备份检查失败", str(error))
    except ManagementError as error:
        text_view(screen, "备份", str(error))
        return str(error)


def image_confirmation(screen, image):
    values = [image.repository, image.tag]
    selected, editing, cursor, horizontal = 3, False, 0, 0
    saved, error = "", ""
    try:
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            if height < 16 or width < 64:
                set_cursor(False)
                put(screen, 0, 0, "终端至少需要 64 列、16 行；Esc 返回")
                screen.refresh()
                if screen.get_wch() == "\x1b":
                    return None
                continue
            put(screen, 1, 2, "导入镜像 / 操作确认", curses.A_BOLD)
            for index, label in enumerate(("镜像名称：", "tag：")):
                available = width - 6 - text_width(label)
                value = values[index]
                if editing and selected == index:
                    start = cursor
                    cells = 0
                    while start > 0 and cells + cell_width(value[start - 1]) < available:
                        start -= 1
                        cells += cell_width(value[start])
                    visible = value[start:]
                    cursor_x = 2 + text_width(label) + cells
                else:
                    offset = min(horizontal, max(0, text_width(value) - available))
                    visible = cell_slice(value, offset, available)
                put(screen, 3 + index * 2, 2, padded(label + clipped(visible, available), width - 4),
                    curses.A_REVERSE if selected == index else 0)
            put(screen, 7, 2, f"镜像大小：{image_import.human_size(image.size)}（归档内层文件合计）")
            for index, label in enumerate(("确认导入", "返回"), 2):
                put(screen, 9 + index - 2, 2, padded(label, width - 4),
                    curses.A_REVERSE if selected == index else 0)
            put(screen, 11, 2, f"平台：{image.platform or '未知'}")
            put(screen, 12, 2, error)
            put(screen, height - 2, 2,
                "输入内容 | ← → 光标 | Enter 保存 | Esc 取消编辑" if editing else
                "↑ ↓ 选择 | ← → 横移 | Enter 编辑/确定 | Esc 返回",
                curses.A_BOLD)
            set_cursor(editing)
            if editing:
                screen.move(3 + selected * 2, cursor_x)
            screen.refresh()
            key = screen.get_wch()
            if editing:
                if key == "\x1b":
                    values[selected], editing, error = saved, False, ""
                elif key in ("\n", "\r", curses.KEY_ENTER):
                    try:
                        image_import.reference(values[0] if selected == 0 else "validation",
                                               values[1] if selected == 1 else "latest")
                        editing, error = False, ""
                    except ManagementError as failure:
                        error = str(failure)
                else:
                    values[selected], cursor = edit_key(values[selected], cursor, key)
                continue
            if key == "\x1b":
                return None
            if key == curses.KEY_DOWN:
                selected = min(3, selected + 1)
            elif key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_LEFT:
                horizontal = max(0, horizontal - 16)
            elif key == curses.KEY_RIGHT:
                horizontal = min(max(text_width(v) for v in values), horizontal + 16)
            elif key in ("\n", "\r", curses.KEY_ENTER):
                if selected == 3:
                    return None
                if selected < 2:
                    editing, saved, cursor = True, values[selected], len(values[selected])
                else:
                    try:
                        image_import.reference(*values)
                        return tuple(values)
                    except ManagementError as failure:
                        error = str(failure)
    finally:
        set_cursor(False)


def image_import_view(screen, root):
    path = ""
    while True:
        path = edit_text(screen, path, "导入镜像 / 镜像归档完整路径")
        if path is None:
            return "主菜单"
        try:
            installation = Installation.load(root)
            progress = execution_progress(screen, "读取镜像归档")
            progress("正在读取镜像名称、tag 和大小…", False)
            preview = image_import.inspect(Path(path), progress)
            selected = 0
            if len(preview.images) > 1:
                selected = choose(screen, "导入镜像 / 选择归档镜像", [path],
                                  [f"{i.repository or '<无名称>'}:{i.tag or '<无tag>'} | "
                                   f"{i.platform} | {image_import.human_size(i.size)}"
                                   for i in preview.images])
                if selected is None:
                    continue
            image = preview.images[selected]
            target = image_confirmation(screen, image)
            if target is None:
                continue
            progress = execution_progress(screen, "导入镜像")
            progress("正在核对目标标签及归档…", False)
            result = image_import.apply(installation, preview, image, *target,
                                        confirmed=True, progress=progress)
            flush_input()
            if result.code:
                text_view(screen, "镜像导入结果", format_result(result))
            return result.summary
        except ManagementError as error:
            text_view(screen, "镜像归档检查失败", str(error))


def lifecycle_view(screen, action, root):
    label = lifecycle.ACTIONS[action]
    try:
        screen.erase()
        put(screen, 1, 2, label, curses.A_BOLD)
        put(screen, 3, 2, "查询当前实例容器…")
        screen.refresh()
        installation = Installation.load(root)
        rows = compose.services(installation)
        if not rows:
            text_view(screen, label, "当前实例没有现有容器，未执行任何操作。")
            return "当前实例没有现有容器。"
        options = [f"{r['service']} | {r['container']} | {r['state']} | {r['id'][:12]}"
                   for r in rows] + ["我全都要"]
        selected = 0
        while True:
            selected = choose(screen, f"{label} / 选择容器",
                              [str(root), f"项目：{installation.project}"], options, selected=selected)
            if selected is None:
                return "主菜单"
            plan = lifecycle.prepare(installation, action, rows,
                                     all_containers=selected == len(rows),
                                     container=rows[selected]["id"] if selected < len(rows) else None)
            target = "、".join(name for _, name in plan.targets)
            confirmed = choose(screen, f"{label} / 操作确认",
                               [str(root), f"项目：{installation.project} | 共 {len(plan.targets)} 个",
                                f"目标：{target}"], ["确认", "返回"], selected=1)
            if confirmed != 0:
                continue
            progress = execution_progress(screen, label)
            progress("正在核对安装记录及目标容器…", False)
            result = lifecycle.apply(plan, confirmed=True, progress=progress)
            flush_input()
            return result.summary + " 已返回主菜单。"
    except ManagementError as error:
        text_view(screen, label, str(error))
        return str(error)


def move_menu(selected: int, key, positions: dict[int, tuple[int, int]]) -> int:
    row, column = positions[selected]
    if key in (curses.KEY_LEFT, curses.KEY_RIGHT):
        destination = column + (1 if key == curses.KEY_RIGHT else -1)
        return next((entry for entry, position in positions.items() if position == (row, destination)),
                    selected)
    if key in (curses.KEY_UP, curses.KEY_DOWN):
        selectable_rows = sorted({position[0] for position in positions.values()})
        step = 1 if key == curses.KEY_DOWN else -1
        destination = selectable_rows[(selectable_rows.index(row) + step) % len(selectable_rows)]
        candidates = [entry for entry, position in positions.items() if position[0] == destination]
        return min(candidates, key=lambda entry: abs(positions[entry][1] - column))
    return selected


def menu(screen, initial_root: Path) -> int:
    screen.keypad(True)
    set_cursor(False)
    root = initial_root
    selected = 0
    notice = "主菜单"
    menu_offset = 0
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 16 or width < 64:
            put(screen, 0, 0, "终端至少需要 64 列、16 行")
            screen.refresh()
            if screen.get_wch() in ("\x1b", "q"):
                return 0
            continue
        put(screen, 1, 2, "部署管理基座", curses.A_BOLD)
        put(screen, 1, width - 12, "管理基座")
        put(screen, 2, 2, notice)
        put(screen, 3, 2, str(root))
        rows, positions, columns = menu_geometry(width)
        visible_rows = height - 7
        active_row = positions[selected][0]
        menu_offset = min(menu_offset, max(0, len(rows) - visible_rows))
        if active_row < menu_offset:
            menu_offset = active_row
        elif active_row >= menu_offset + visible_rows:
            menu_offset = active_row - visible_rows + 1
        cell_size = (width - 4) // columns
        for index, items in enumerate(rows[menu_offset:menu_offset + visible_rows]):
            y = 5 + index
            if isinstance(items, str):
                put(screen, y, 2, clipped(f"── {items} " + "─" * width, width - 4), curses.A_BOLD)
                continue
            for column, entry in enumerate(items):
                span = width - 4 if entry in (0, len(MENU_ENTRIES) - 1) else cell_size - 2
                put(screen, y, 2 + column * cell_size, padded("  " + MENU_ENTRIES[entry][1], span),
                    curses.A_REVERSE if entry == selected else 0)
        put(screen, height - 2, 2, "↑ ↓ ← → 选择 | Enter 打开 | Esc 退出", curses.A_BOLD)
        screen.refresh()
        key = screen.get_wch()
        if key == curses.KEY_RESIZE:
            continue
        if key == "\x1b":
            return 0
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN):
            selected = move_menu(selected, key, positions)
        elif key in ("\n", "\r", curses.KEY_ENTER):
            command, label = MENU_ENTRIES[selected]
            if command == "exit":
                return 0
            if command == "root":
                edited = edit_root(screen, str(root))
                if edited is not None:
                    root = Path(edited)
                    notice = "已切换检查目录，未修改任何安装记录。"
            else:
                notice = "主菜单"
                if command in lifecycle.ACTIONS:
                    notice = lifecycle_view(screen, command, root)
                elif command == "image-import":
                    notice = image_import_view(screen, root)
                elif command == "image-switch":
                    notice = image_switch_view(screen, root)
                elif command == "service-add":
                    notice = service_add_view(screen, root)
                elif command == "firewall-add":
                    notice = firewall_add_view(screen, root)
                elif command in backups.COMMANDS:
                    notice = backup_view(screen, root, command)
                elif command in COMMANDS:
                    screen.erase()
                    put(screen, 1, 2, label, curses.A_BOLD)
                    put(screen, 3, 2, "检查中…")
                    screen.refresh()
                    result = execute(command, root)
                    if result.code == 0 and command == "status":
                        status_view(screen, result.data["services"])
                    elif result.code == 0 and command == "image-versions":
                        images_view(screen, result.data["images"])
                    elif result.code == 0 and command == "locations":
                        table_view(screen, label, location_table.table_data(result.data["locations"]),
                                   "没有服务")
                    elif result.code == 0 and command == "exposed-ports":
                        table_view(screen, label, network_tables.ports_data(result.data["ports"]),
                                   "没有容器端口映射", footer="实际映射，非连通性检测")
                    elif command == "docker-firewall" and "firewall" in result.data:
                        table_view(screen, "DOCKER-USER" + ("（查询不完整）" if result.code else ""),
                                   network_tables.firewall_data(result.data["firewall"]),
                                   "没有防火墙查询结果", footer="filter / DNAT 后匹配")
                    else:
                        text_view(screen, label, format_result(result))
                else:
                    text_view(screen, label, entry_detail(command, label, root))


def run(root: Path) -> int:
    def interrupt(signum, _frame):
        raise KeyboardInterrupt

    old_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    for sig in old_handlers:
        signal.signal(sig, interrupt)
    try:
        locale.setlocale(locale.LC_ALL, "")
        if hasattr(curses, "set_escdelay"):
            curses.set_escdelay(80)
        return curses.wrapper(menu, root)
    except KeyboardInterrupt:
        return 130
    except (curses.error, locale.Error):
        import sys
        print("终端初始化或显示失败；请检查 TERM/UTF-8 设置，或改用命令模式。", file=sys.stderr)
        return 4
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
