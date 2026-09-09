import contextlib
import curses
import io
import json
import unittest
from unittest.mock import patch

from managebase import cli, image_table
from managebase.operations import execute
from managebase.tui import images_view
from test_foundation import Fixture
from test_status_table import Screen


IMAGE_ID = "sha256:" + "a" * 64
OTHER_ID = "sha256:" + "b" * 64
CONTAINER_ID = "c" * 64


def image(repository="registry:5000/team/api", tag="v1", identity=IMAGE_ID):
    return {"Repository": repository, "Tag": tag, "ID": identity, "Size": "120MB",
            "CreatedAt": "2020-01-01 00:00:00 +0000 UTC"}


def container(identity=CONTAINER_ID, image_id=IMAGE_ID, state="running"):
    return {"ID": identity, "ImageID": image_id, "Name": "/outside-project-api",
            "State": state, "Env": "SECRET"}


def encoded(records):
    return json.dumps(records).encode()


class ImageTests(Fixture):
    def query(self, records, containers=()):
        with patch("managebase.images.run_readonly", side_effect=[
            encoded(records), "\n".join(row["ID"] for row in containers).encode(),
            encoded(containers),
        ]) as run:
            result = execute("image-versions", self.root)
        return result, run

    def test_multiple_tags_and_usage_are_matched_by_image_id(self):
        result, run = self.query([
            image(tag="old"), image(tag="alias"), image(tag="latest", identity=OTHER_ID),
            image(tag="alias"),
        ], [container()])
        self.assertEqual(result.code, 0)
        rows = {row["tag"]: row for row in result.data["images"]}
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows["old"]["in_use"])
        self.assertTrue(rows["alias"]["in_use"])
        self.assertFalse(rows["latest"]["in_use"])
        self.assertEqual(rows["old"]["containers"][0]["name"], "outside-project-api")
        self.assertNotIn("SECRET", json.dumps(result.as_dict()))
        calls = [call.args[0] for call in run.call_args_list]
        self.assertTrue(all(args[:3] == ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
                            for args in calls))
        self.assertTrue(all("--filter" not in args for args in calls))
        self.assertIn("--all", calls[0])
        self.assertIn("--no-trunc", calls[0])
        self.assertNotIn(".Config.Env", calls[-1][-2])

    def test_stopped_container_counts_as_in_use(self):
        result, _ = self.query([image()], [container(state="exited")])
        row = result.data["images"][0]
        self.assertTrue(row["in_use"])
        self.assertEqual(row["container_count"], 1)
        self.assertEqual(row["containers"][0]["state"], "exited")

    def test_creation_time_is_not_import_time(self):
        result, _ = self.query([image()])
        row = result.data["images"][0]
        self.assertIsNone(row["imported_at"])
        self.assertEqual(row["import_time_source"], "unrecorded")
        text = cli.format_result(result)
        self.assertIn("未知（无记录）", text)
        self.assertNotIn("2020-01-01", text)
        for label in ("镜像名称", "镜像标签", "导入时间", "容器使用", "镜像 ID", "大小"):
            self.assertIn(label, text)
        self.assertIn("registry:5000/team/api", text)

    def test_dangling_image_is_preserved(self):
        result, _ = self.query([image(repository="<none>", tag="<none>")])
        row = result.data["images"][0]
        self.assertEqual(row["repository"], "<none>")
        self.assertFalse(row["in_use"])
        self.assertIn("<none>", cli.format_result(result))

    def test_empty_inventory_does_not_query_containers(self):
        with patch("managebase.images.run_readonly", return_value=b"[]") as run:
            result = execute("image-versions", self.root)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.data["images"], [])
        self.assertEqual(run.call_count, 1)
        self.assertIn("没有本地镜像", cli.format_result(result))

    def test_invalid_image_and_container_outputs_fail_closed(self):
        cases = (
            [b"SECRET-invalid"],
            [encoded([image(identity="--help")])],
            [encoded([image()]), b"--help"],
            [encoded([image()]), CONTAINER_ID.encode(), b"[]"],
            [encoded([image()]), CONTAINER_ID.encode(), encoded([container(image_id="bad")])],
        )
        for outputs in cases:
            with self.subTest(outputs=len(outputs)):
                with patch("managebase.images.run_readonly", side_effect=outputs):
                    result = execute("image-versions", self.root)
                self.assertEqual(result.code, 5)
                self.assertNotIn("SECRET", result.summary)

    def test_container_inspection_is_batched(self):
        containers = [container(identity=f"{index:064x}") for index in range(130)]
        outputs = [encoded([image()]), "\n".join(row["ID"] for row in containers).encode()]
        outputs += [encoded(containers[start:start + 64]) for start in range(0, 130, 64)]
        with patch("managebase.images.run_readonly", side_effect=outputs) as run:
            result = execute("image-versions", self.root)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.data["images"][0]["container_count"], 130)
        self.assertEqual(run.call_count, 5)

    def test_dry_run_does_not_query_docker(self):
        with patch("managebase.images.run_readonly") as run:
            result = execute("image-versions", self.root, dry_run=True)
        run.assert_not_called()
        self.assertEqual(result.code, 0)
        self.assertIn("image", result.data["argv"])
        self.assertIn("inspect", result.data["follow_up"])
        self.assertFalse(result.data["mutates_workloads"])

    def test_json_command_is_noninteractive(self):
        output = io.StringIO()
        with patch("managebase.images.run_readonly", return_value=b"[]"):
            with contextlib.redirect_stdout(output):
                code = cli.main(["image-versions", "--root", str(self.root), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["data"]["images"], [])


class ImageTableTests(unittest.TestCase):
    def rows(self, count):
        return [{"repository": f"registry.example.com/team/image-{index:03}", "tag": "v1",
                 "id": IMAGE_ID, "size": "120MB", "imported_at": None, "in_use": False,
                 "container_count": 0, "containers": []} for index in range(count)]

    def test_all_arrow_keys_and_back_use_shared_table(self):
        screen = Screen([curses.KEY_DOWN, curses.KEY_UP, curses.KEY_RIGHT,
                         curses.KEY_LEFT, "\x1b"], width=100)
        images_view(screen, self.rows(10))
        first, second, previous, horizontal, restored = screen.frames
        self.assertIn("本机镜像", first)
        self.assertIn("image-006", first)
        self.assertNotIn("image-007", first)
        self.assertIn("image-007", second)
        self.assertIn("第 2/2 页", second)
        self.assertEqual(first, previous)
        self.assertNotEqual(horizontal, first)
        self.assertIn("image-000", horizontal)
        self.assertEqual(restored, first)
        self.assertIn("Esc 返回上级", first)

    def test_empty_and_narrow_tables(self):
        screen = Screen(["\x1b"], width=64)
        images_view(screen, [])
        self.assertIn("没有本地镜像", screen.frames[0])
        screen = Screen([curses.KEY_RIGHT] * 10 + ["\x1b"], width=64)
        images_view(screen, self.rows(1))
        self.assertIn("未知（无记录）", image_table.format_table(self.rows(1)))


if __name__ == "__main__":
    unittest.main()
