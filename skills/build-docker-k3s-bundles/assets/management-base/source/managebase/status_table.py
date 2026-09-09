"""Plain-text container table shared by CLI and terminal rendering."""

from datetime import datetime, timezone
import unicodedata


COLUMNS = (
    ("service", "服务名"),
    ("state", "运行状态"),
    ("health", "健康状态"),
    ("created_at", "创建时间 (UTC)"),
    ("started_at", "启动时间 (UTC)"),
    ("image", "镜像版本"),
    ("restart_count", "重启次数"),
    ("container", "容器名"),
    ("image_id", "镜像 ID"),
)


def cell_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def text_width(text: str) -> int:
    return sum(cell_width(char) for char in text)


def cell_slice(text: str, start: int, width: int) -> str:
    result, position = "", 0
    end = start + width
    for char in text:
        if not char.isprintable():
            continue
        size = cell_width(char)
        if position >= end:
            break
        if position >= start:
            result += char if position + size <= end else " " * (end - position)
        elif position + size > start:
            result += " " * (position + size - start)
        position += size
    return result


def padded(text: str, width: int) -> str:
    value = cell_slice(text, 0, width)
    return value + " " * (width - text_width(value))


def timestamp(value: str, *, started: bool = False) -> str:
    if not value:
        return "--"
    if value.startswith("0001-01-01"):
        return "未启动" if started else "--"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return "--"
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "--"


def table_data(services: list[dict]) -> tuple[list[str], list[list[str]], list[int]]:
    headings = [label for _, label in COLUMNS]
    rows = []
    for service in services:
        values = []
        for key, _ in COLUMNS:
            value = service.get(key)
            if key in ("created_at", "started_at"):
                text = timestamp(value or "", started=key == "started_at")
            elif key == "health":
                text = value or "未配置"
            else:
                text = "--" if value is None or value == "" else str(value)
            values.append("".join(char for char in text if char.isprintable()))
        rows.append(values)
    widths = [max([text_width(heading), *(text_width(row[i]) for row in rows)])
              for i, heading in enumerate(headings)]
    return headings, rows, widths


def format_table(services: list[dict]) -> str:
    return render_table(*table_data(services), empty="没有容器")


def render_table(headings: list[str], rows: list[list[str]], widths: list[int], *, empty: str) -> str:
    def line(values):
        return " | ".join(padded(value, width) for value, width in zip(values, widths))
    lines = [line(headings), "-+-".join("-" * width for width in widths)]
    lines.extend(line(row) for row in rows)
    if not rows:
        lines.append(empty)
    return "\n".join(lines)
