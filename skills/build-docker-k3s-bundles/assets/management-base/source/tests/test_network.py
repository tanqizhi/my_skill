import curses
import json
from unittest.mock import patch

from managebase import cli, firewall, network_tables
from managebase.model import ManagementError
from managebase.operations import execute
from managebase.tui import table_view
from test_foundation import Fixture
from test_status_table import Screen


IDENTITY = "a" * 64


def snapshot(*rules, declared=True):
    declaration = ":DOCKER-USER - [0:0]\n" if declared else ":FORWARD ACCEPT [0:0]\n"
    return ("*filter\n" + declaration + "\n".join(rules) + "\nCOMMIT\n").encode()


class PortTests(Fixture):
    def query(self, bindings, *, mode="bridge", running=True):
        record = {"ID": IDENTITY, "Service": "api"}
        inspected = {"ID": IDENTITY, "Name": "/project-api", "Running": running,
                     "State": "running" if running else "exited", "Mode": mode,
                     "Ports": bindings, "Env": "SECRET"}
        with patch("managebase.ports.run_readonly", side_effect=[
            json.dumps([record]).encode(), json.dumps([inspected]).encode(),
        ]):
            return execute("exposed-ports", self.root)

    def test_ipv4_ipv6_and_udp_actual_mapping(self):
        result = self.query({
            "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"},
                         {"HostIp": "::", "HostPort": "28080"}],
            "53/udp": [{"HostIp": "0.0.0.0", "HostPort": "5353"}],
            "9000/tcp": None,
        })
        self.assertEqual(result.code, 0)
        rows = result.data["ports"]
        self.assertEqual({(row["listen_ip"], row["host_port"], row["container_port"], row["protocol"])
                          for row in rows},
                         {("127.0.0.1", 18080, 8080, "tcp"), ("::", 28080, 8080, "tcp"),
                          ("0.0.0.0", 5353, 53, "udp")})
        self.assertNotIn("SECRET", cli.format_result(result))

    def test_unpublished_stopped_and_host_network_are_not_listeners(self):
        for options, status in (
            ({"bindings": {"80/tcp": None}}, "未发布端口"),
            ({"bindings": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "80"}]},
              "running": False}, "容器未运行"),
            ({"bindings": {}, "mode": "host"}, "host 网络"),
        ):
            with self.subTest(status=status):
                result = self.query(**options)
                self.assertEqual(result.code, 0)
                row = result.data["ports"][0]
                self.assertIsNone(row["host_port"])
                self.assertIn(status, row["publishing_status"])

    def test_binding_without_host_port_does_not_claim_listener(self):
        result = self.query({"80/tcp": [{"HostIp": "::", "HostPort": ""}]})
        self.assertIsNone(result.data["ports"][0]["host_port"])
        self.assertEqual(result.data["ports"][0]["publishing_status"], "无宿主机端口映射")

    def test_invalid_bindings_and_missing_inspection_fail(self):
        for bindings in ([], {"bad/tcp": []},
                         {"80/tcp": [{"HostIp": "invalid", "HostPort": "80"}]},
                         {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "65536"}]}):
            self.assertEqual(self.query(bindings).code, 5)
        with patch("managebase.ports.run_readonly", side_effect=[
            json.dumps([{"ID": IDENTITY, "Service": "api"}]).encode(), b"[]",
        ]):
            self.assertEqual(execute("exposed-ports", self.root).code, 5)

    def test_empty_ports_and_dry_run(self):
        with patch("managebase.ports.run_readonly", return_value=b"[]") as run:
            result = execute("exposed-ports", self.root)
        self.assertEqual(result.data["ports"], [])
        self.assertEqual(run.call_count, 1)
        with patch("managebase.ports.run_readonly") as run:
            self.assertEqual(execute("exposed-ports", self.root, dry_run=True).code, 0)
        run.assert_not_called()

    def test_port_table_uses_all_arrow_keys(self):
        result = self.query({"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]})
        rows = [{**result.data["ports"][0], "service": f"api-{index:02}"} for index in range(10)]
        screen = Screen([curses.KEY_DOWN, curses.KEY_UP, curses.KEY_RIGHT, curses.KEY_LEFT, "\x1b"],
                        width=64)
        table_view(screen, "对外暴露端口", network_tables.ports_data(rows), "没有映射",
                   footer="实际映射，非连通性检测")
        self.assertIn("api-07", screen.frames[1])
        self.assertEqual(screen.frames[0], screen.frames[2])
        self.assertEqual(screen.frames[0], screen.frames[4])
        self.assertNotEqual(screen.frames[0], screen.frames[3])


class FirewallTests(Fixture):
    def test_five_tuple_counters_negation_and_rule_numbers(self):
        data = snapshot(
            "[12345678901:98765432100] -A DOCKER-USER ! -s 10.0.0.0/8 -d 172.18.0.2/32 "
            "-p tcp -m multiport --sports 1024:65535 --dports 80,443 -i eth0 -o docker0 -j ACCEPT",
            "[7:420] -A DOCKER-USER -p udp --dport 53 -j DROP",
            "[8:800] -A DOCKER-USER -j RETURN",
        )
        rules = firewall.parse_snapshot(data, "IPv4")["rules"]
        self.assertEqual([rule["number"] for rule in rules], [1, 2, 3])
        first = rules[0]
        self.assertEqual(first["source_ip"], "! 10.0.0.0/8")
        self.assertEqual(first["destination_ip"], "172.18.0.2/32")
        self.assertEqual(first["source_port"], "1024:65535")
        self.assertEqual(first["destination_port"], "80,443")
        self.assertEqual(first["packets"], 12345678901)
        self.assertEqual(first["bytes"], 98765432100)
        self.assertEqual(first["input_interface"], "eth0")
        self.assertEqual(first["action"], "ACCEPT")
        self.assertEqual(rules[1]["protocol"], "udp")
        self.assertEqual(rules[2]["protocol"], "all")

    def test_conntrack_original_tuple_and_comment_are_preserved(self):
        line = ('[1:60] -A DOCKER-USER -p tcp --dport 80 -m conntrack '
                '--ctorigdst 192.0.2.5 --ctorigdstport 8080 --ctstate NEW '
                '-m comment --comment "-j DROP --dport 22" -j ACCEPT')
        rule = firewall.parse_rule(line, "IPv4", 1)
        self.assertEqual(rule["destination_port"], "80")
        self.assertEqual(rule["action"], "ACCEPT")
        self.assertIn("--ctorigdstport 8080", rule["extra_matches"])
        self.assertIn("-j DROP --dport 22", rule["extra_matches"])
        self.assertEqual(rule["raw_rule"], line)

    def test_ipv6_ranges_goto_and_missing_counters(self):
        rule = firewall.parse_rule(
            '-A DOCKER-USER -s 2001:db8::/32 -p tcp --dport ! 443 -m comment --comment "!" '
            '-g USER-FILTER', "IPv6", 2)
        self.assertEqual(rule["family"], "IPv6")
        self.assertEqual(rule["destination_port"], "! 443")
        self.assertEqual(rule["action"], "GOTO USER-FILTER")
        self.assertIsNone(rule["packets"])
        self.assertIn("'!'", rule["extra_matches"])

    def test_only_docker_user_is_included(self):
        data = snapshot(
            "[999:9999] -A FORWARD -j DOCKER-USER",
            "[2:120] -A DOCKER-USER -j RETURN",
        )
        rules = firewall.parse_snapshot(data, "IPv4")["rules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["packets"], 2)

    def test_empty_missing_and_malformed_are_distinct(self):
        self.assertEqual(firewall.parse_snapshot(snapshot(), "IPv4")["status"], "present")
        self.assertEqual(firewall.parse_snapshot(snapshot(declared=False), "IPv6")["status"], "missing")
        self.assertEqual(firewall.parse_snapshot(b"", "IPv4")["status"], "missing")
        for data in (b"SECRET-invalid", b"*filter\n:DOCKER-USER - [0:0]\n",
                     snapshot('[oops] -A DOCKER-USER -j DROP'),
                     snapshot('[0:0] -A DOCKER-USER --dport'),
                     snapshot('[0:0] -A DOCKER-USER -j DROP', declared=False)):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    firewall.parse_snapshot(data, "IPv4")

    def test_permission_error_is_partial_failure_not_empty_success(self):
        commands = {"IPv4": ["/usr/sbin/iptables-save", "-c", "-t", "filter"],
                    "IPv6": ["/usr/sbin/ip6tables-save", "-c", "-t", "filter"]}
        with patch("managebase.firewall.commands", return_value=commands):
            with patch("managebase.firewall.run_readonly", side_effect=[
                snapshot("[1:60] -A DOCKER-USER -j DROP"), ManagementError("SECRET permission error"),
            ]):
                result = execute("docker-firewall", self.root)
        self.assertEqual(result.code, 5)
        self.assertFalse(result.data["firewall"]["complete"])
        text = cli.format_result(result)
        self.assertIn("读取失败", text)
        self.assertIn("DROP", text)
        self.assertNotIn("SECRET", text)

    def test_missing_tools_and_dry_run_never_modify_firewall(self):
        with patch("managebase.firewall.commands", return_value={"IPv4": None, "IPv6": None}):
            with patch("managebase.firewall.run_readonly") as run:
                result = execute("docker-firewall", self.root)
                plan = execute("docker-firewall", self.root, dry_run=True)
        run.assert_not_called()
        self.assertEqual(result.code, 5)
        self.assertEqual(plan.code, 0)
        self.assertFalse(plan.data["resets_counters"])
        with patch("managebase.firewall.shutil.which", side_effect=["/usr/sbin/iptables-save",
                                                                  "/usr/sbin/ip6tables-save"]):
            for argv in firewall.commands().values():
                self.assertEqual(argv[1:], ["-c", "-t", "filter"])

    def test_firewall_table_paging_and_empty_chain_status(self):
        chain = firewall.parse_snapshot(snapshot(
            *[f"[{index}:60] -A DOCKER-USER -p tcp --dport {80 + index} -j ACCEPT"
              for index in range(10)]), "IPv4")
        data = {"chains": [chain], "complete": True}
        screen = Screen([curses.KEY_DOWN, curses.KEY_UP, curses.KEY_RIGHT, curses.KEY_LEFT, "\x1b"],
                        width=64)
        table_view(screen, "DOCKER-USER", network_tables.firewall_data(data), "无规则")
        self.assertIn("IPv4/8", screen.frames[1])
        self.assertEqual(screen.frames[0], screen.frames[4])
        text = network_tables.format_firewall(
            {"chains": [firewall.parse_snapshot(snapshot(), "IPv4")], "complete": True})
        self.assertIn("链为空", text)
        self.assertIn("命中包数", text)
