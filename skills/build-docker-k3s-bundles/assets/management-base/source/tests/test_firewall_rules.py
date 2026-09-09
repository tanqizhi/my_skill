import contextlib
import curses
import io
import json
from pathlib import Path
import shlex
import tempfile
from unittest.mock import patch

from managebase import cli, firewall_rules as rules, tui
from managebase.layout import Installation
from managebase.model import ManagementError, Result
from managebase.operations import execute
from test_foundation import Fixture
from test_image_import import FormScreen


def values(**overrides):
    return {"position": "-1", "protocol": "IP", "source": "", "source_port": "",
            "destination": "", "destination_port": "", "action": "REJECT", **overrides}


class RuleTests(Fixture):
    def test_protocols_cidr_normalization_and_ports(self):
        for protocol in ("IP", "tcp", "udp", "icmp"):
            rule = rules.Rule.parse(**values(protocol=protocol, source="192.0.2.15/24"))
            self.assertEqual(rule.source, "192.0.2.0/24")
            self.assertEqual(rule.destination, "0.0.0.0/0")
            specification = rule.specification("test")
            self.assertEqual("-p" in specification, protocol != "IP")
        rule = rules.Rule.parse(**values(protocol="tcp", source_port="0010:0020", destination_port="443"))
        self.assertEqual(rule.source_port, "10:20")
        self.assertIn("--sport", rule.specification("test"))
        self.assertIn("--dport", rule.specification("test"))

    def test_ipv6_family_and_icmp_translation(self):
        rule = rules.Rule.parse(**values(protocol="icmp", destination="2001:db8::1/64"))
        self.assertEqual((rule.family, rule.source, rule.destination),
                         (6, "::/0", "2001:db8::/64"))
        self.assertIn("ipv6-icmp", rule.specification("test"))

    def test_invalid_inputs_rejected(self):
        for change in (
            {"position": 0}, {"position": -2}, {"position": True}, {"position": "1;false"},
            {"position": 10**10}, {"protocol": "all"}, {"action": "DROP"},
            {"source": "example.com"}, {"source": "192.0.2.1;false"}, {"source": "fe80::1%eth0"},
            {"source": "192.0.2.1", "destination": "::1"}, {"destination": "192.0.2.0/33"},
            {"protocol": "tcp", "destination_port": "65536"},
            {"protocol": "udp", "source_port": "10:1"},
            {"protocol": "tcp", "source_port": "1,2"}, {"source_port": "80"},
            {"protocol": "icmp", "destination_port": "80"},
        ):
            with self.subTest(change=change), self.assertRaises(ManagementError):
                rules.Rule.parse(**values(**change))

    def test_cli_confirmation_and_argument_scope(self):
        with patch("managebase.firewall_rules.prepare") as prepare:
            self.assertEqual(execute("firewall-add", self.root).code, 2)
            self.assertEqual(execute("status", self.root, position=1).code, 2)
            self.assertEqual(execute("firewall-add", self.root, yes=True, service="api").code, 2)
            self.assertEqual(execute("firewall-add", self.root, yes=True).code, 2)
        prepare.assert_not_called()
        with patch("managebase.cli.execute", return_value=Result("ok")) as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["firewall-add", "--position", "-1", "--protocol", "tcp",
                                      "--source", "192.0.2.0/24", "--destination-port", "443",
                                      "--action", "REJECT", "--dry-run", "--json"]), 0)
        self.assertEqual(call.call_args.kwargs["position"], -1)
        self.assertEqual(call.call_args.kwargs["destination_port"], "443")


class Backend:
    def __init__(self):
        self.rules = [("-A", "DOCKER-USER", "-j", "RETURN")]
        self.version = b"iptables test (nf_tables)\n"
        self.mutations = []
        self.fail_after_write = False
        self.foreign_after_write = False

    def read(self, argv, root, **kwargs):
        if "--version" in argv:
            return self.version
        if "-S" in argv:
            return ("-N DOCKER-USER\n" + "\n".join(shlex.join(row) for row in self.rules) + "\n").encode()
        if "-C" in argv:
            spec = ("-A", *argv[argv.index("-C") + 1:])
            if spec not in self.rules:
                raise ManagementError("missing", 5)
            return b""
        raise AssertionError(argv)

    def write(self, argv, root, **kwargs):
        self.mutations.append(argv)
        if "-D" in argv:
            self.rules.remove(("-A", *argv[argv.index("-D") + 1:]))
            return b""
        action = "-I" if "-I" in argv else "-A"
        tail = argv[argv.index(action) + 1:]
        if action == "-I":
            chain, number, *spec = tail
            self.rules.insert(int(number) - 1, ("-A", chain, *spec))
        else:
            self.rules.append(("-A", *tail))
        if self.foreign_after_write:
            self.rules.append(("-A", "DOCKER-USER", "-s", "198.51.100.1/32", "-j", "ACCEPT"))
        if self.fail_after_write:
            raise ManagementError("Docker command timeout", 5)
        return b""


class MutationTests(Fixture):
    def setUp(self):
        with patch("test_foundation.WORK", Path(tempfile.gettempdir()) / "managebase-firewall-tests"):
            super().setUp()
        (self.root / "state/locks").mkdir()
        self.installed = Installation.load(self.root)
        self.backend = Backend()
        self.enterContext(patch.object(rules, "HOST_LOCK", self.root / "host.lock"))
        self.enterContext(patch.object(rules, "binary_for", return_value="/usr/sbin/iptables"))
        self.enterContext(patch.object(rules, "run_readonly", side_effect=self.backend.read))
        self.enterContext(patch.object(rules, "run_command", side_effect=self.backend.write))

    def plan(self, **overrides):
        return rules.prepare(self.installed, rules.Rule.parse(**values(**overrides)))

    def test_preview_and_no_confirm_do_not_write(self):
        plan = self.plan()
        self.assertEqual(rules.apply(plan).code, 2)
        self.assertEqual(execute("firewall-add", self.root, dry_run=True, **values()).code, 0)
        self.assertFalse((self.root / "backups").exists())
        self.assertFalse((self.root / "host.lock").exists())
        self.assertEqual(self.backend.mutations, [])

    def test_append_is_after_return_and_insertion_shifts_rules(self):
        for position, expected in ((-1, 1), (1, 0)):
            with self.subTest(position=position):
                self.backend.rules = [("-A", "DOCKER-USER", "-j", "RETURN")]
                plan = self.plan(position=position)
                result = rules.apply(plan, confirmed=True)
                self.assertEqual(result.code, 0, result)
                self.assertEqual(rules.owned(tuple(self.backend.rules), plan.marker), [expected])
                backup = Path(result.data["backup"])
                self.assertEqual(json.loads((backup / "before.json").read_text()),
                                 [["-A", "DOCKER-USER", "-j", "RETURN"]])
                recovery = (backup / "recovery.txt").read_text()
                self.assertIn("-D DOCKER-USER", recovery)
                self.assertIn(plan.marker, recovery)
                self.assertNotIn("iptables-restore", recovery)
                self.assertEqual((backup / "plan.json").stat().st_mode & 0o777, 0o600)

    def test_line_bounds(self):
        self.plan(position=2)
        with self.assertRaises(ManagementError):
            self.plan(position=3)

    def test_rule_drift_and_backend_change_refuse_without_mutation(self):
        plan = self.plan()
        self.backend.rules.append(("-A", "DOCKER-USER", "-j", "DROP"))
        self.assertEqual(rules.apply(plan, confirmed=True).code, 4)
        self.backend.rules.pop()
        self.backend.version = b"iptables (legacy)"
        self.assertEqual(rules.apply(plan, confirmed=True).code, 4)
        self.assertEqual(self.backend.mutations, [])

    def test_post_write_failure_removes_only_own_rule(self):
        plan = self.plan(position=1)
        self.backend.fail_after_write = True
        result = rules.apply(plan, confirmed=True)
        self.assertEqual(result.code, 5)
        self.assertTrue(result.data["recovery"]["own_rule_absent"])
        self.assertEqual(self.backend.rules, list(plan.before))
        self.assertEqual(len(self.backend.mutations), 2)

    def test_external_rule_is_never_rolled_back(self):
        plan = self.plan()
        self.backend.foreign_after_write = True
        result = rules.apply(plan, confirmed=True)
        self.assertEqual(result.code, 5)
        self.assertTrue(result.data["recovery"]["own_rule_absent"])
        self.assertEqual(len(self.backend.rules), 2)
        self.assertIn("198.51.100.1/32", self.backend.rules[-1])

    def test_backup_failure_prevents_rule_write(self):
        plan = self.plan()
        with patch.object(rules.config_io, "write_private", side_effect=OSError):
            self.assertEqual(rules.apply(plan, confirmed=True).code, 5)
        self.assertEqual(self.backend.mutations, [])

    def test_command_failure_before_write_confirms_no_own_rule(self):
        plan = self.plan()
        def failure(*args, **kwargs):
            raise ManagementError("unavailable", 5)
        with patch.object(rules, "run_command", side_effect=failure):
            result = rules.apply(plan, confirmed=True)
        self.assertEqual(result.code, 5)
        self.assertTrue(result.data["recovery"]["own_rule_absent"])

    def test_unrecoverable_failure_reports_uncertain_state(self):
        plan = self.plan()
        self.backend.fail_after_write = True
        original_read = self.backend.read
        def inaccessible_after_write(*args, **kwargs):
            if self.backend.mutations:
                raise ManagementError("unavailable", 5)
            return original_read(*args, **kwargs)
        with patch.object(rules, "run_readonly", side_effect=inaccessible_after_write):
            result = rules.apply(plan, confirmed=True)
        self.assertEqual(result.code, 5)
        self.assertTrue(result.data["recovery"]["recovery_incomplete"])
        self.assertIn("状态不确定", result.summary)
        self.assertEqual(len(self.backend.mutations), 1)

    def test_interrupt_after_write_rolls_back_exact_rule(self):
        plan = self.plan()
        def interrupt(argv, root, **kwargs):
            self.backend.write(argv, root, **kwargs)
            if "-D" not in argv:
                raise KeyboardInterrupt
        with patch.object(rules, "run_command", side_effect=interrupt):
            result = rules.apply(plan, confirmed=True)
        self.assertEqual(result.code, 130)
        self.assertTrue(result.data["recovery"]["own_rule_absent"])
        self.assertEqual(self.backend.rules, list(plan.before))

    def test_missing_chain_is_refused(self):
        for raw in (b"", b"-N OTHER\n", b"-P FORWARD ACCEPT\n"):
            with patch.object(rules, "run_readonly", return_value=raw), self.assertRaises(ManagementError):
                rules.snapshot("/usr/sbin/iptables", self.root)

    def test_host_lock_blocks_other_instances_and_symlinks(self):
        with rules.host_lock(), self.assertRaises(ManagementError):
            with rules.host_lock():
                pass
        (self.root / "host.lock").unlink()
        (self.root / "host.lock").symlink_to(self.root / "bundle.yaml")
        with self.assertRaises(ManagementError):
            with rules.host_lock():
                pass


class FormTests(Fixture):
    def test_six_rows_and_escape_no_mutation(self):
        screen = FormScreen(["\x1b"], width=64)
        self.assertIsNone(tui.firewall_form(screen, values()))
        for label in ("添加到第 X 行", "协议类型", "源地址", "目标地址", "动作", "确认添加"):
            self.assertIn(label, screen.frames[0])
        self.assertNotIn("源端口", screen.frames[0])
        self.assertNotIn("目标端口", screen.frames[0])

    def test_protocol_arrows_show_and_clear_ports(self):
        data = values()
        keys = [curses.KEY_DOWN, curses.KEY_RIGHT, curses.KEY_DOWN, curses.KEY_RIGHT,
                "\n", "8", "0", "\n", curses.KEY_UP,
                curses.KEY_RIGHT, curses.KEY_RIGHT, "\x1b"]
        screen = FormScreen(keys, width=64)
        self.assertIsNone(tui.firewall_form(screen, data))
        self.assertEqual(data["protocol"], "icmp")
        self.assertEqual(data["source_port"], "")
        self.assertTrue(any("源端口" in frame for frame in screen.frames))
        self.assertNotIn("源端口", screen.frames[-1])

    def test_full_form_edit_confirm_and_validation(self):
        keys = ["\n", "\x15", "1", "\n", curses.KEY_DOWN, curses.KEY_RIGHT,
                curses.KEY_DOWN, "\n", *"192.0.2.1/24", "\n", curses.KEY_RIGHT,
                "\n", *"1024:65535", "\n", curses.KEY_DOWN, "\n", *"172.18.0.2", "\n",
                curses.KEY_RIGHT, "\n", *"443", "\n", curses.KEY_DOWN, curses.KEY_LEFT,
                curses.KEY_DOWN, "\n"]
        screen = FormScreen(keys, width=64)
        rule = tui.firewall_form(screen, values())
        self.assertEqual((rule.position, rule.protocol, rule.action), (1, "tcp", "ACCEPT"))
        self.assertEqual(rule.source, "192.0.2.0/24")
        self.assertEqual(rule.source_port, "1024:65535")
        self.assertEqual(rule.destination_port, "443")

    def test_edit_cancel_and_resize(self):
        data = values(source="2001:db8::/32")
        screen = FormScreen([curses.KEY_DOWN, curses.KEY_DOWN, "\n", "\x15", "x",
                             (16, 64), "\x1b", (8, 30), (16, 80), "\x1b"])
        self.assertIsNone(tui.firewall_form(screen, data))
        self.assertEqual(data["source"], "2001:db8::/32")

    def test_invalid_row_stays_in_form(self):
        screen = FormScreen([curses.KEY_DOWN] * 5 + ["\n", "\x1b"])
        self.assertIsNone(tui.firewall_form(screen, values(position="0")))
        self.assertIn("行号必须", screen.frames[-1])

    def test_final_confirmation_defaults_return(self):
        rule = rules.Rule.parse(**values())
        plan = rules.Plan(Installation.load(self.root), rule, "/usr/sbin/iptables", b"v", (), "test")
        with patch.object(tui, "firewall_form", side_effect=[rule, None]), \
                patch.object(rules, "prepare", return_value=plan), \
                patch.object(tui, "choose", return_value=1) as choose, \
                patch.object(rules, "apply") as apply:
            self.assertEqual(tui.firewall_add_view(None, self.root), "主菜单")
        self.assertEqual(choose.call_args.kwargs["selected"], 1)
        apply.assert_not_called()

    def test_confirm_executes_prepared_plan(self):
        rule = rules.Rule.parse(**values())
        plan = rules.Plan(Installation.load(self.root), rule, "/usr/sbin/iptables", b"v", (), "test")
        with patch.object(tui, "firewall_form", return_value=rule), \
                patch.object(rules, "prepare", return_value=plan), \
                patch.object(tui, "choose", return_value=0), \
                patch.object(tui, "execution_progress", return_value=lambda *_: None), \
                patch.object(tui, "flush_input"), patch.object(tui, "text_view"), \
                patch.object(rules, "apply", return_value=Result("ok")) as apply:
            self.assertEqual(tui.firewall_add_view(None, self.root), "ok")
        self.assertEqual(apply.call_args.args, (plan,))
        self.assertTrue(apply.call_args.kwargs["confirmed"])
