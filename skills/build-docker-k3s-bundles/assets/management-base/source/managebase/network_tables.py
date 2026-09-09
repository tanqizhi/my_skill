from .status_table import render_table, text_width


def sized(headings: list[str], rows: list[list[str]]) -> tuple:
    rows = [["".join(char for char in value if char.isprintable()) for value in row] for row in rows]
    widths = [max([text_width(heading), *(text_width(row[i]) for row in rows)])
              for i, heading in enumerate(headings)]
    return headings, rows, widths


def ports_data(ports: list[dict]) -> tuple:
    headings = ["服务名", "监听/绑定 IP", "对外监听端口", "容器端口", "协议",
                "映射状态", "容器名", "容器状态"]
    rows = [[row["service"], row["listen_ip"] or "--",
             str(row["host_port"]) if row["host_port"] is not None else "--",
             str(row["container_port"]) if row["container_port"] is not None else "--",
             row["protocol"] or "--", row["publishing_status"], row["container"], row["state"]]
            for row in ports]
    return sized(headings, rows)


def firewall_data(firewall: dict) -> tuple:
    headings = ["序号", "协议", "源 IP", "源端口", "目的 IP", "目的端口",
                "命中包数", "动作", "字节数", "入接口", "出接口", "附加条件/动作参数", "完整规则"]
    rows = []
    for chain in firewall["chains"]:
        if not chain["rules"]:
            status = {"present": "链为空", "missing": "链不存在", "unavailable": "读取失败"}[chain["status"]]
            rows.append([f'{chain["family"]}/--', "--", "--", "--", "--", "--", "--", status,
                         "--", "--", "--", chain["message"] or "链存在，当前没有规则", "--"])
        for rule in chain["rules"]:
            rows.append([
                f'{rule["family"]}/{rule["number"]}', rule["protocol"],
                rule["source_ip"], rule["source_port"], rule["destination_ip"], rule["destination_port"],
                str(rule["packets"]) if rule["packets"] is not None else "未知",
                rule["action"], str(rule["bytes"]) if rule["bytes"] is not None else "未知",
                rule["input_interface"], rule["output_interface"], rule["extra_matches"] or "--",
                rule["raw_rule"],
            ])
    return sized(headings, rows)


def format_ports(ports: list[dict]) -> str:
    return render_table(*ports_data(ports), empty="没有容器端口映射")


def format_firewall(firewall: dict) -> str:
    return render_table(*firewall_data(firewall), empty="没有防火墙查询结果")
