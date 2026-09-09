"""Image inventory presentation for both management interfaces."""

from .status_table import render_table, text_width, timestamp


def table_data(images: list[dict]) -> tuple[list[str], list[list[str]], list[int]]:
    headings = ["镜像名称", "镜像标签", "导入时间 (UTC)", "容器使用", "容器数",
                "大小", "镜像 ID", "完整镜像名称", "使用容器（含已停止）"]
    rows = []
    for image in images:
        repository = image["repository"] or "<none>"
        values = [
            repository.rsplit("/", 1)[-1], image["tag"] or "<none>",
            timestamp(image["imported_at"]) if image["imported_at"] else "未知（无记录）",
            "是" if image["in_use"] else "否", str(image["container_count"]),
            image["size"] or "--", image["id"], repository,
            ", ".join(f'{item["name"]} ({item["state"]})' for item in image["containers"]) or "--",
        ]
        rows.append(["".join(char for char in value if char.isprintable()) for value in values])
    widths = [max([text_width(heading), *(text_width(row[i]) for row in rows)])
              for i, heading in enumerate(headings)]
    return headings, rows, widths


def format_table(images: list[dict]) -> str:
    return render_table(*table_data(images), empty="没有本地镜像")
