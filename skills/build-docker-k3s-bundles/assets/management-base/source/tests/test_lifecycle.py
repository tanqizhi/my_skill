import contextlib
import curses
import io
import json
import sys
from unittest.mock import patch

from managebase import cli, lifecycle, tui
from managebase.layout import Installation
from managebase.model import ManagementError, Result
from managebase.operations import execute
from managebase.runner import run_command
from test_foundation import Fixture
from test_menu_views import MenuScreen
from test_status_table import Screen


class LifecycleTests(Fixture):
    def setUp(self):
        super().setUp()
        (self.root / "state/locks").mkdir()
        self.installation = Installation.load(self.root)
        self.rows = [{"id": c * 64, "container": f"project-{c}", "service": "replica",
                      "state": "running"} for c in "ab"]

    def plan(self, action="restart", **kwargs):
        return lifecycle.prepare(self.installation, action, self.rows,
                                 **(kwargs or {"container": "project-a"}))

    def test_explicit_selection_required(self):
        for kwargs in ({}, {"container": "project-a", "all_containers": True},
                       {"container": "foreign"}, {"container": "a" * 12}):
            with self.assertRaises(ManagementError):
                lifecycle.prepare(self.installation, "restart", self.rows, **kwargs)

    def test_no_confirmation_never_calls_docker_or_creates_lock(self):
        with patch("managebase.lifecycle.run_command") as run:
            self.assertEqual(lifecycle.apply(self.plan()).code, 2)
            run.assert_not_called()
        self.assertFalse((self.root / "state/locks/management.lock").exists())
        with patch("managebase.operations.compose.services") as query:
            self.assertEqual(execute("stop", self.root, all_containers=True).code, 2)
            query.assert_not_called()

    def test_exact_single_id_for_all_actions(self):
        for action in lifecycle.ACTIONS:
            updates = []
            with patch("managebase.lifecycle.compose.services", return_value=self.rows), \
                    patch("managebase.lifecycle.run_command", return_value=b"") as run:
                result = lifecycle.apply(self.plan(action), confirmed=True,
                                         progress=lambda message, tick: updates.append(message))
            self.assertEqual(result.code, 0)
            self.assertEqual(run.call_args.args[0][-2:], [action, "a" * 64])
            self.assertEqual(result.data["completed"], ["project-a"])
            self.assertTrue(any("完成" in u for u in updates))

    def test_all_is_snapshot_not_new_or_foreign_containers(self):
        with patch("managebase.lifecycle.compose.services",
                   return_value=self.rows + [{"id": "c" * 64}]), \
                patch("managebase.lifecycle.run_command", return_value=b"") as run:
            result = lifecycle.apply(self.plan(all_containers=True), confirmed=True)
        self.assertEqual(result.code, 0)
        self.assertEqual([c.args[0][-1] for c in run.call_args_list], ["a" * 64, "b" * 64])

    def test_changed_membership_or_installation_refuses_execution(self):
        plan = self.plan()
        with patch("managebase.lifecycle.compose.services", return_value=[]), \
                patch("managebase.lifecycle.run_command") as run:
            self.assertNotEqual(lifecycle.apply(plan, confirmed=True).code, 0)
            run.assert_not_called()
        self.state["compose"]["project_name"] = "another"
        self.save()
        with patch("managebase.lifecycle.run_command") as run:
            self.assertNotEqual(lifecycle.apply(plan, confirmed=True).code, 0)
            run.assert_not_called()

    def test_concurrent_operation_refused(self):
        with lifecycle.instance_lock(self.root), patch("managebase.lifecycle.run_command") as run:
            self.assertNotEqual(lifecycle.apply(self.plan(), confirmed=True).code, 0)
            run.assert_not_called()

    def test_symlink_lock_rejected(self):
        (self.root / "state/locks/management.lock").symlink_to(self.root / "bundle.yaml")
        with patch("managebase.lifecycle.run_command") as run:
            self.assertNotEqual(lifecycle.apply(self.plan(), confirmed=True).code, 0)
            run.assert_not_called()

    def test_failure_preserves_partial_result_and_stops(self):
        with patch("managebase.lifecycle.compose.services", return_value=self.rows), \
                patch("managebase.lifecycle.run_command",
                      side_effect=[b"", ManagementError("timeout", 5)]):
            result = lifecycle.apply(self.plan(all_containers=True), confirmed=True)
        self.assertEqual(result.code, 5)
        self.assertEqual(result.data, {"completed": ["project-a"], "uncertain": "project-b"})

    def test_cli_preview_and_execution_json_without_prompts(self):
        for args in (["--dry-run"], ["--yes"]):
            output = io.StringIO()
            with patch("managebase.lifecycle.compose.services", return_value=self.rows), \
                    patch("managebase.lifecycle.run_command", return_value=b"") as run, \
                    contextlib.redirect_stdout(output):
                code = cli.main(["restart", "--root", str(self.root),
                                 "--container", "project-a", "--json", *args])
            self.assertEqual(code, 0)
            self.assertIsInstance(json.loads(output.getvalue()), dict)
            self.assertEqual(run.call_count, 0 if "--dry-run" in args else 1)

    def test_runner_ticks_and_hides_errors(self):
        ticks = []
        run_command([sys.executable, "-c", "import time; time.sleep(.3)"], self.root,
                    tick=lambda: ticks.append(1))
        self.assertGreaterEqual(len(ticks), 2)
        with self.assertRaises(ManagementError) as error:
            run_command([sys.executable, "-c", "raise RuntimeError('SECRET')"], self.root)
        self.assertNotIn("SECRET", str(error.exception))

    def test_selection_scrolling_all_last_and_resize(self):
        options = [f"container-{i}" for i in range(30)] + ["我全都要"]
        screen = Screen([curses.KEY_DOWN] * 30 + [(8, 30), (16, 64), "\n"])
        self.assertEqual(tui.choose(screen, "选择容器", [], options), 30)
        self.assertIn("我全都要", screen.frames[-1])
        self.assertIn("31/31", screen.frames[-1])

    def test_confirmation_default_return_and_esc_back_one_level(self):
        for back in ("\n", "\x1b"):
            screen = Screen(["\n", back, "\x1b"])
            with patch("managebase.tui.compose.services", return_value=self.rows), \
                    patch("managebase.tui.lifecycle.apply") as apply:
                self.assertEqual(tui.lifecycle_view(screen, "restart", self.root), "主菜单")
                apply.assert_not_called()
            self.assertIn("操作确认", screen.frames[2])
            self.assertIn("选择容器", screen.frames[3])
            self.assertFalse((self.root / "state/locks/management.lock").exists())

    def test_horizontal_scroll_keeps_confirmation_choices_visible(self):
        screen = Screen([curses.KEY_RIGHT] * 10 + ["\n"], width=64)
        self.assertEqual(tui.choose(screen, "操作确认", ["目标：" + "x" * 500],
                                    ["确认", "返回"], selected=1), 1)
        for frame in screen.frames:
            self.assertIn("确认", frame)
            self.assertIn("返回", frame)

    def test_confirm_single_and_all_show_progress_then_return(self):
        for selection in (0, 2):
            screen = Screen([curses.KEY_DOWN] * selection + ["\n", curses.KEY_UP, "\n"])
            with patch("managebase.tui.compose.services", return_value=self.rows), \
                    patch("managebase.lifecycle.run_command", return_value=b""):
                notice = tui.lifecycle_view(screen, "restart", self.root)
            self.assertIn("已返回主菜单", notice)
            self.assertTrue(any("执行中" in frame for frame in screen.frames))
            self.assertTrue(any("完成：project-a" in frame for frame in screen.frames))
            self.assertEqual(any("完成：project-b" in frame for frame in screen.frames), selection == 2)

    def test_full_menu_returns_automatically_after_execution(self):
        screen = MenuScreen([curses.KEY_DOWN] * 6 + ["\n", "\n", curses.KEY_UP, "\n", "\x1b"],
                            height=24)
        with patch("managebase.tui.set_cursor"), \
                patch("managebase.tui.compose.services", return_value=self.rows), \
                patch("managebase.lifecycle.run_command", return_value=b""):
            self.assertEqual(tui.menu(screen, self.root), 0)
        self.assertIn("部署管理基座", screen.frames[-1])
        self.assertIn("已返回主菜单", screen.frames[-1])
