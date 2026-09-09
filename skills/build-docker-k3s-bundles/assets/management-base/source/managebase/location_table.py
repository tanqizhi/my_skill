from .status_table import render_table, text_width, timestamp


def table_data(locations: list[dict]) -> tuple[list[str], list[list[str]], list[int]]:
    headings = ["服务名", "Compose 文件位置", "修改日期 (UTC)", "创建日期 (UTC)",
                "持久化目录位置", "挂载依据", "文件型挂载"]
    rows = []
    for service in locations:
        for metadata in service["compose_files"] or [{}]:
            rows.append([
                service["service"], metadata.get("path", "未在当前 Compose 中定义"),
                timestamp(metadata.get("modified_at", "")),
                timestamp(metadata["created_at"]) if metadata.get("created_at") else "未知（不支持）",
                "; ".join(service["persistent_directories"]) or "不涉及",
                "容器实际挂载" if service["mount_source"] == "actual-containers" else "Compose 配置",
                "; ".join(service["file_mounts"]) or "不涉及",
            ])
    rows = [["".join(char for char in value if char.isprintable()) for value in row] for row in rows]
    widths = [max([text_width(heading), *(text_width(row[i]) for row in rows)])
              for i, heading in enumerate(headings)]
    return headings, rows, widths


def format_table(locations: list[dict]) -> str:
    return render_table(*table_data(locations), empty="没有服务")
