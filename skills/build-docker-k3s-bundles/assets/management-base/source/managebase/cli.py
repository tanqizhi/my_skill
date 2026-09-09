import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .model import Result
from .operations import COMMANDS, execute


def format_result(result: Result) -> str:
    text = result.summary
    if result.data:
        if "services" in result.data:
            from .status_table import format_table
            text += "\n" + format_table(result.data["services"])
        elif "images" in result.data:
            from .image_table import format_table
            text += "\n" + format_table(result.data["images"])
        elif "locations" in result.data:
            from .location_table import format_table
            text += "\n" + format_table(result.data["locations"])
        elif "ports" in result.data:
            from .network_tables import format_ports
            text += "\n" + format_ports(result.data["ports"])
        elif "firewall" in result.data:
            from .network_tables import format_firewall
            text += "\n" + format_firewall(result.data["firewall"])
        else:
            text += "\n" + json.dumps(result.data, ensure_ascii=False, indent=2)
    return text


def entrypoint() -> None:
    raise SystemExit(main())


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(sys.argv[0]).resolve().parent
    if not args:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("交互模式需要终端。请使用 --help 或携带命令参数。", file=sys.stderr)
            return 2
        # A missing curses extension must never prevent command-mode use.
        try:
            from .tui import run
        except ImportError:
            print("缺少 curses 交互依赖，命令模式仍可使用。", file=sys.stderr)
            return 4
        return run(root)
    parser = argparse.ArgumentParser(
        description="管理基座：无参数交互；携带参数非交互。仅管理已安装实例。",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--root", type=Path, default=root, help="已安装实例的绝对根目录")
    parser.add_argument("--dry-run", action="store_true", help="只预览；启停类命令会只读查询目标")
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--container", help="当前实例的容器名称或完整 ID")
    targets.add_argument("--all", dest="all_containers", action="store_true", help="当前实例的全部容器/备份服务")
    parser.add_argument("--yes", action="store_true", help="明确确认变更操作")
    parser.add_argument("--archive", type=Path, help="镜像归档完整路径")
    parser.add_argument("--image-index", type=int, help="归档内的镜像序号，从 1 开始")
    parser.add_argument("--image-name", help="导入后的镜像名称，不含 tag")
    parser.add_argument("--image-tag", help="导入后的 tag")
    parser.add_argument("--service", help="所选服务名")
    parser.add_argument("--image", help="切换到已有镜像的标签、摘要或 ID")
    parser.add_argument("--compose-file", type=Path, help="定义新增服务的 Compose 文件完整路径")
    parser.add_argument("--output", type=Path, help="备份文件完整路径，自动补充 .tar.gz")
    parser.add_argument("--position", type=int, help="规则插入行号，从 1 开始；-1 追加末尾")
    parser.add_argument("--protocol", choices=("IP", "tcp", "udp", "icmp"), help="IP 表示所有协议")
    parser.add_argument("--source", help="源 IP/CIDR；省略表示任意")
    parser.add_argument("--source-port", help="源端口或起始:结束；省略表示任意，仅 tcp/udp")
    parser.add_argument("--destination", help="目标 IP/CIDR；匹配 DNAT 后地址")
    parser.add_argument("--destination-port", help="目标端口或起始:结束；匹配 DNAT 后端口，仅 tcp/udp")
    parser.add_argument("--action", choices=("ACCEPT", "REJECT"), help="通过或拒绝")
    parser.add_argument("--json", action="store_true", help="输出结构化结果")
    try:
        options = parser.parse_args(args)
    except SystemExit as error:
        return int(error.code)
    try:
        result = execute(options.command, options.root, dry_run=options.dry_run,
                         container=options.container, all_containers=options.all_containers,
                         yes=options.yes, archive=options.archive, image_index=options.image_index,
                         image_name=options.image_name, image_tag=options.image_tag,
                         service=options.service, image=options.image,
                         compose_file=options.compose_file, output=options.output,
                         position=options.position, protocol=options.protocol,
                         source=options.source, source_port=options.source_port,
                         destination=options.destination, destination_port=options.destination_port,
                         action=options.action)
    except KeyboardInterrupt:
        return 130
    if options.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False))
    else:
        print(format_result(result), file=sys.stderr if result.code else sys.stdout)
    return result.code
