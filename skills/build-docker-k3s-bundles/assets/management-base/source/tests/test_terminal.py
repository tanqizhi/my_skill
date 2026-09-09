import fcntl
from collections import deque
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest
from unittest.mock import patch

from managebase.tui import MENU_ENTRIES, MENU_GROUPS, cell_width, clipped, entry_detail, wrap_lines, menu_geometry, move_menu

PROJECT = Path(__file__).resolve().parents[1]


class TextTests(unittest.TestCase):
    def test_chinese_width(self):
        self.assertEqual(cell_width("中"), 2)
        self.assertEqual(clipped("中文abc", 5), "中文a")

    def test_wrap(self):
        self.assertEqual(wrap_lines("中文abc", 4), ["中文", "abc"])

    def test_control_characters_filtered(self):
        self.assertNotIn("\x1b", clipped("\x1bhello", 20))

    def test_groups_and_placeholder_entries_do_not_execute(self):
        self.assertEqual([title for title, _ in MENU_GROUPS], ["查询", "操作"])
        self.assertIn(("backup-compose", "备份现有 Compose 文件"), MENU_ENTRIES)
        self.assertIn(("backup-data", "备份现有数据文件"), MENU_ENTRIES)
        with patch("managebase.tui.execute") as execute:
            for command, label in MENU_ENTRIES:
                if command not in {"root", "exit", "doctor", "layout", "status",
                                   "image-versions", "locations", "exposed-ports",
                                   "docker-firewall", "config-check", "start", "stop", "restart",
                                   "image-import", "image-switch", "service-add",
                                   "backup-compose", "backup-data", "firewall-add"}:
                    self.assertIn("待实现", entry_detail(command, label, Path("/missing")))
            execute.assert_not_called()


class TerminalTests(unittest.TestCase):
    def start(self, rows=24, columns=100):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        before = termios.tcgetattr(slave)
        proc = subprocess.Popen(
            [sys.executable, str(PROJECT / "manage.py")],
            stdin=slave, stdout=slave, stderr=slave,
            env={**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8"},
        )
        self.addCleanup(self.cleanup, proc, master, slave)
        return proc, master, slave, before

    @staticmethod
    def cleanup(proc, master, slave):
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)
        os.close(slave)

    def wait_for(self, master, expected, timeout=5):
        data = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                data += os.read(master, 65536)
                if expected in data:
                    return data
        self.fail(f"terminal did not show {expected!r}; output={data[-500:]!r}")

    def test_menu_navigation_and_restoration(self):
        proc, master, slave, before = self.start()
        self.wait_for(master, "部署管理基座".encode())
        os.write(master, b"\x1bOB\x1bOC\x1bOB\x1bOB\n")
        self.wait_for(master, b"python_supported")
        os.write(master, b"\x1b")
        self.wait_for(master, "部署管理基座".encode())
        os.write(master, b"\x1b")
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertEqual(termios.tcgetattr(slave), before)

    def test_service_form_and_backup_navigation(self):
        import curses
        proc, master, slave, before = self.start()
        self.wait_for(master, "Docker 转发防火墙".encode())
        selected = 0
        _, positions, _ = menu_geometry(100)

        def enter(command):
            nonlocal selected
            target = next(i for i, row in enumerate(MENU_ENTRIES) if row[0] == command)
            queue, seen = deque([(selected, b"")]), {selected}
            while queue:
                current, route = queue.popleft()
                if current == target:
                    selected = target
                    os.write(master, route + b"\n")
                    return
                for key, encoded in ((curses.KEY_UP, b"\x1bOA"), (curses.KEY_DOWN, b"\x1bOB"),
                                     (curses.KEY_LEFT, b"\x1bOD"), (curses.KEY_RIGHT, b"\x1bOC")):
                    other = move_menu(current, key, positions)
                    if other not in seen:
                        seen.add(other)
                        queue.append((other, route + encoded))
            self.fail(command)

        enter("service-add")
        self.wait_for(master, "服务信息".encode())
        os.write(master, b"\x1b")
        self.wait_for(master, "部署管理基座".encode())
        for command in ("backup-compose", "backup-data"):
            enter(command)
            self.wait_for(master, "文件缺失".encode())
            os.write(master, b"\x1b")
            self.wait_for(master, "部署管理基座".encode())
        enter("firewall-add")
        self.wait_for(master, "确认添加".encode())
        os.write(master, b"\x1b")
        self.wait_for(master, "部署管理基座".encode())
        os.write(master, b"\x1b")
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertEqual(termios.tcgetattr(slave), before)

    def test_minimum_terminal_scroll_and_wrap(self):
        proc, master, slave, before = self.start(16, 64)
        self.wait_for(master, "部署管理基座".encode())
        os.write(master, b"\x1bOA")
        self.wait_for(master, "退出".encode())
        os.write(master, b"\n")
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertEqual(termios.tcgetattr(slave), before)

    def test_edit_root_chinese_and_cancel(self):
        proc, master, slave, before = self.start()
        self.wait_for(master, "部署管理基座".encode())
        os.write(master, b"\n")
        self.wait_for(master, "取消".encode())
        os.write(master, b"\x15" + "/tmp/中文目录".encode() + b"\n")
        self.wait_for(master, "已切换检查目录".encode())
        os.write(master, b"\x1b")
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertEqual(termios.tcgetattr(slave), before)

    def test_sigterm_restores_terminal(self):
        proc, master, slave, before = self.start()
        self.wait_for(master, "部署管理基座".encode())
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=5), 130)
        self.assertEqual(termios.tcgetattr(slave), before)

    def test_small_terminal_can_exit(self):
        proc, master, slave, before = self.start(8, 30)
        self.wait_for(master, "终端至少需要".encode())
        os.write(master, b"\x1b")
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertEqual(termios.tcgetattr(slave), before)
