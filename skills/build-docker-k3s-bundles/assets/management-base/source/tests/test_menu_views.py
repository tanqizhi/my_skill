import curses
from pathlib import Path
import unittest
from unittest.mock import patch

from managebase.tui import MENU_ENTRIES, menu, menu_geometry, move_menu, text_view
from test_status_table import Screen


class MenuScreen(Screen):
    def keypad(self, enabled):
        pass


class MenuViewTests(unittest.TestCase):
    def test_menu_uses_both_sides_and_group_separators(self):
        screen = MenuScreen(["\x1b"], height=24, width=100)
        with patch("managebase.tui.set_cursor"):
            self.assertEqual(menu(screen, Path("/opt/bundles/test")), 0)
        self.assertIn("── 查询", screen.frames[0])
        self.assertIn("── 操作", screen.frames[0])
        self.assertIn("容器相关位置", screen.frames[0])
        self.assertNotIn("请选择查询或操作项目", screen.frames[0])
        image = next(cell for cell in screen.cells if "容器镜像版本" in cell[2])
        self.assertGreaterEqual(image[1], 50)

    def test_all_entries_reachable_with_arrows_and_no_heading_selected(self):
        for width in (64, 100, 140, 200):
            _, positions, _ = menu_geometry(width)
            pending, seen = [0], {0}
            while pending:
                source = pending.pop()
                for key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
                    target = move_menu(source, key, positions)
                    if target not in seen:
                        seen.add(target)
                        pending.append(target)
            self.assertEqual(seen, set(range(len(MENU_ENTRIES))))

    def test_responsive_menu_does_not_overlap(self):
        for width in (64, 100, 140, 200):
            screen = MenuScreen([curses.KEY_DOWN] * 20 + ["\x1b"], height=16, width=width)
            with patch("managebase.tui.set_cursor"):
                menu(screen, Path("/opt/bundles/test"))

    def test_text_result_uses_arrows_and_returns_without_exiting_menu(self):
        screen = Screen([curses.KEY_DOWN, curses.KEY_UP, curses.KEY_RIGHT,
                         curses.KEY_LEFT, "\x1b"], width=64)
        text_view(screen, "工具环境", "\n".join(f"row-{i:02} " + "x" * 120 for i in range(20)))
        first, second, previous, horizontal, restored = screen.frames
        self.assertIn("row-00", first)
        self.assertIn("row-09", second)
        self.assertEqual(first, previous)
        self.assertNotIn("row-00", horizontal)
        self.assertEqual(first, restored)

    def test_service_form_is_fullscreen_and_esc_returns_to_main(self):
        screen = MenuScreen([curses.KEY_DOWN] * 7 + [curses.KEY_RIGHT, "\n", "\x1b", "\x1b"],
                            height=24, width=100)
        with patch("managebase.tui.set_cursor"):
            menu(screen, Path("/opt/bundles/test"))
        placeholder = next(frame for frame in screen.frames if "服务信息" in frame)
        self.assertNotIn("── 查询", placeholder)
        self.assertNotIn("── 操作", placeholder)
        self.assertIn("部署管理基座", screen.frames[-1])
