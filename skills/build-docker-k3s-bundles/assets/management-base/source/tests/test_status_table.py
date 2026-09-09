import curses
import unittest

from managebase.status_table import cell_slice, format_table, text_width, timestamp
from managebase.tui import status_view


def services(count):
    return [
        {"service": f"service-{index:03}", "state": "running", "health": "healthy",
         "created_at": "2026-09-09T01:00:00Z", "started_at": "2026-09-09T02:00:00Z",
         "image": "registry.example.com/project/service:v2", "restart_count": 0,
         "container": f"project-service-{index:03}", "image_id": "sha256:" + "a" * 64}
        for index in range(count)
    ]


class Screen:
    def __init__(self, keys, height=16, width=100):
        self.keys = iter(keys)
        self.height, self.width = height, width
        self.frames = []
        self.cells = []

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.cells = []

    def addstr(self, y, x, text, style):
        assert 0 <= y < self.height
        assert x + text_width(text) < self.width
        for old_y, old_x, old_text in self.cells:
            if y == old_y:
                assert x >= old_x + text_width(old_text) or old_x >= x + text_width(text)
        self.cells.append((y, x, text))

    def refresh(self):
        self.frames.append("\n".join(text for _, _, text in self.cells))

    def get_wch(self):
        key = next(self.keys)
        if isinstance(key, tuple):
            self.height, self.width = key
            return curses.KEY_RESIZE
        return key


class StatusTableTests(unittest.TestCase):
    def test_table_has_required_columns_and_exact_values(self):
        table = format_table(services(1))
        for text in ("服务名", "健康状态", "创建时间", "启动时间", "镜像版本",
                     "重启次数", "service-000", "2026-09-09 02:00:00", "service:v2"):
            self.assertIn(text, table)

    def test_missing_health_and_never_started(self):
        table = format_table([{"service": "stopped", "state": "created",
                               "started_at": "0001-01-01T00:00:00Z"}])
        self.assertIn("未配置", table)
        self.assertIn("未启动", table)
        self.assertEqual(timestamp("2026-09-09T10:00:00+08:00"), "2026-09-09 02:00:00")
        self.assertEqual(timestamp("invalid"), "--")

    def test_empty_table(self):
        screen = Screen(["\x1b"])
        status_view(screen, [])
        self.assertIn("没有容器", screen.frames[0])
        self.assertIn("第 1/1 页", screen.frames[0])

    def test_page_keys_bounds_and_last_partial_page(self):
        screen = Screen([curses.KEY_UP, curses.KEY_DOWN, curses.KEY_DOWN,
                         curses.KEY_DOWN, curses.KEY_UP, "\x1b"])
        status_view(screen, services(16))
        first, bounded_first, second, last, bounded_last, previous = screen.frames
        self.assertEqual(first, bounded_first)
        self.assertIn("service-006", first)
        self.assertNotIn("service-007", first)
        self.assertIn("service-007", second)
        self.assertIn("service-015", last)
        self.assertNotIn("service-013", last)
        self.assertEqual(last, bounded_last)
        self.assertEqual(previous, second)
        for frame in screen.frames:
            self.assertIn("↑ 上一页", frame)
            self.assertIn("↓ 下一页", frame)
            self.assertIn("服务名", frame)

    def test_horizontal_scroll_pins_service_name(self):
        screen = Screen([curses.KEY_RIGHT] * 8 + [curses.KEY_LEFT, "\x1b"], width=64)
        status_view(screen, services(16))
        for frame in screen.frames:
            self.assertIn("service-000", frame)
            self.assertIn("第 1/3 页", frame)
            self.assertIn("← / → 横向移动", frame)
        roundtrip = Screen([curses.KEY_RIGHT, curses.KEY_LEFT, "\x1b"], width=64)
        status_view(roundtrip, services(16))
        self.assertEqual(roundtrip.frames[0], roundtrip.frames[2])
        self.assertTrue(any("service:v2" in frame for frame in screen.frames))

    def test_resize_clamps_page_and_horizontal_position(self):
        screen = Screen([curses.KEY_DOWN, curses.KEY_DOWN, curses.KEY_RIGHT,
                         (40, 250), (8, 30), (16, 64), "\x1b"])
        status_view(screen, services(16))
        self.assertIn("第 1/1 页", screen.frames[4])
        self.assertIn("至少需要", screen.frames[5])
        self.assertIn("↓ 下一页", screen.frames[6])

    def test_chinese_long_fields_do_not_overlap(self):
        rows = services(1)
        rows[0]["service"] = "中文服务" * 30
        rows[0]["image"] = "镜像仓库/" * 30 + ":latest"
        screen = Screen([curses.KEY_RIGHT] * 10 + ["\x1b"], width=64)
        status_view(screen, rows)
        self.assertIn("…", screen.frames[0])
        self.assertEqual(cell_slice("中文abc", 1, 4), " 文a")


if __name__ == "__main__":
    unittest.main()
