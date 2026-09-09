import contextlib
from dataclasses import replace
import curses
import hashlib
import io
import json
from pathlib import Path
import tarfile
from unittest.mock import patch

from managebase import cli, image_import, images, tui
from managebase.layout import Installation
from managebase.model import ManagementError, Result
from managebase.operations import execute
from test_foundation import Fixture
from test_status_table import Screen


def save_archive(path, *, tags=None, extra=None, mode="w", manifest=None):
    layer = b"layer-content"
    config = json.dumps({"architecture": "amd64", "os": "linux",
                         "rootfs": {"type": "layers", "diff_ids": [
                             "sha256:" + hashlib.sha256(layer).hexdigest()]}}).encode()
    digest = hashlib.sha256(config).hexdigest()
    entry = {"Config": f"{digest}.json", "Layers": ["layer/layer.tar"],
             "RepoTags": ["example/old:wrong"] if tags is None else tags}
    contents = {f"{digest}.json": config, "layer/layer.tar": layer,
                "manifest.json": json.dumps([entry] if manifest is None else manifest).encode(),
                **(extra or {})}
    with tarfile.open(path, mode) as archive:
        for name, content in contents.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    return digest


class FormScreen(Screen):
    def move(self, y, x):
        assert 0 <= y < self.height
        assert 0 <= x < self.width - 1


class ImageImportTests(Fixture):
    def setUp(self):
        super().setUp()
        (self.root / "state/locks").mkdir()
        self.path = self.root / "test-image.tar"
        self.digest = save_archive(self.path)
        self.installation = Installation.load(self.root)

    def preview(self):
        preview = image_import.inspect(self.path)
        return preview, preview.images[0]

    def test_preview_reads_name_tag_size_without_docker_or_writes(self):
        before = self.path.read_bytes()
        with patch("managebase.image_import.run_command") as run:
            preview, image = self.preview()
        run.assert_not_called()
        self.assertEqual((image.repository, image.tag), ("example/old", "wrong"))
        self.assertEqual(image.identity, "sha256:" + self.digest)
        self.assertEqual(image.size, len(b"layer-content"))
        self.assertEqual(image.platform, "linux/amd64")
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse((self.root / "state/image-import").exists())

    def test_supported_compression(self):
        for mode in ("w:gz", "w:bz2", "w:xz"):
            save_archive(self.path, mode=mode)
            self.assertEqual(self.preview()[1].tag, "wrong")

    def test_registry_port_and_aliases(self):
        save_archive(self.path, tags=["registry:5000/team/api:v1", "other/name:V2"])
        preview, _ = self.preview()
        self.assertEqual(len(preview.images), 2)
        self.assertEqual(preview.images[0].repository, "registry:5000/team/api")
        self.assertEqual(preview.images[1].tag, "V2")
        self.assertEqual(image_import.canonical("alpine:latest"), "docker.io/library/alpine:latest")
        self.assertEqual(image_import.canonical("index.docker.io/library/alpine:latest"),
                         "docker.io/library/alpine:latest")
        self.assertEqual(image_import.reference("[fd00::1]:5000/team/api", "v1"),
                         "[fd00::1]:5000/team/api:v1")
        self.assertEqual(image_import.canonical("REGISTRY/team/api:v1"), "REGISTRY/team/api:v1")

    def test_untagged_requires_explicit_name_and_tag(self):
        save_archive(self.path, tags=[])
        _, image = self.preview()
        self.assertEqual((image.repository, image.tag), ("", ""))
        self.assertEqual(execute("image-import", self.root, archive=self.path, dry_run=True).code, 2)
        result = execute("image-import", self.root, archive=self.path, dry_run=True,
                         image_name="example/fixed", image_tag="v1")
        self.assertEqual(result.code, 0)

    def test_relative_missing_directory_and_symlink_rejected(self):
        link = self.root / "link.tar"
        link.symlink_to(self.path)
        for path in (Path("relative"), self.root, self.root / "missing", link):
            with self.assertRaises(ManagementError):
                image_import.inspect(path)

    def test_bad_archive_and_export_archive_rejected(self):
        self.path.write_bytes(b"SECRET-not-a-tar")
        with self.assertRaises(ManagementError) as error:
            image_import.inspect(self.path)
        self.assertNotIn("SECRET", str(error.exception))
        with tarfile.open(self.path, "w"):
            pass
        with self.assertRaisesRegex(ManagementError, "docker save"):
            image_import.inspect(self.path)

    def test_path_traversal_links_and_duplicate_members_rejected(self):
        for name in ("../escape", "/absolute", "bad\\path"):
            save_archive(self.path, extra={name: b"bad"})
            with self.assertRaises(ManagementError):
                self.preview()
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.REGTYPE):
            save_archive(self.path)
            with tarfile.open(self.path, "a") as archive:
                item = tarfile.TarInfo("manifest.json")
                item.type = kind
                item.linkname = "/etc/shadow"
                archive.addfile(item)
            with self.assertRaises(ManagementError):
                self.preview()

    def test_missing_layer_and_duplicate_json_keys_rejected(self):
        save_archive(self.path, manifest=[{"Config": f"{self.digest}.json",
                                          "Layers": ["missing"], "RepoTags": ["a:v1"]}])
        with self.assertRaises(ManagementError):
            self.preview()
        save_archive(self.path, extra={"manifest.json": b'[{"Config":"a","Config":"b"}]'})
        with self.assertRaises(ManagementError):
            self.preview()

    def test_invalid_target_names_and_tags(self):
        for name, tag in (("host/team/UPPER", "v1"), ("https://host/repo", "v1"), ("repo:old", "v1"),
                          ("repo", ""), ("repo", "-v1"), ("repo", "x" * 129),
                          ("../repo", "v1"), ("repo", "a;b"), ("", "v1")):
            with self.assertRaises(ManagementError):
                image_import.reference(name, tag)

    def test_no_confirmation_never_loads(self):
        preview, image = self.preview()
        with patch("managebase.image_import.run_command") as run:
            result = image_import.apply(self.installation, preview, image, "new/name", "v2")
        self.assertEqual(result.code, 2)
        run.assert_not_called()
        self.assertFalse((self.root / "state/locks/management.lock").exists())

    def test_repacked_archive_contains_only_confirmed_tag_and_selected_image(self):
        save_archive(self.path, tags=["example/old:wrong", "example/old:alias"],
                     extra={"unrelated.txt": b"should-not-import", "repositories": b"old"})
        preview, image = self.preview()
        staged = self.root / "staged.tar"
        image_import.stage(preview, image, "example/new:correct", staged, None)
        with tarfile.open(staged) as archive:
            self.assertEqual(set(archive.getnames()), {"config.json", "layer-0.tar", "manifest.json"})
            manifest = json.load(archive.extractfile("manifest.json"))
            self.assertEqual(manifest[0]["RepoTags"], ["example/new:correct"])
            self.assertEqual(archive.extractfile("layer-0.tar").read(), b"layer-content")
        self.assertEqual(self.preview()[1].repository, "example/old")

    def test_multi_image_archive_requires_selection_and_stages_selected_config(self):
        with tarfile.open(self.path) as archive:
            original = json.load(archive.extractfile(f"{self.digest}.json"))
        other = json.dumps({**original, "architecture": "arm64"}).encode()
        manifest = [
            {"Config": f"{self.digest}.json", "RepoTags": ["first:v1"], "Layers": ["layer/layer.tar"]},
            {"Config": "other.json", "RepoTags": ["second:v1"], "Layers": ["layer/layer.tar"]},
        ]
        save_archive(self.path, manifest=manifest, extra={"other.json": other})
        preview = image_import.inspect(self.path)
        self.assertEqual(len(preview.images), 2)
        self.assertNotEqual(preview.images[0].identity, preview.images[1].identity)
        staged = self.root / "staged.tar"
        image_import.stage(preview, preview.images[1], "selected:v2", staged, None)
        with tarfile.open(staged) as archive:
            self.assertEqual(archive.extractfile("config.json").read(), other)
        result = execute("image-import", self.root, archive=self.path, yes=True)
        self.assertEqual(result.code, 2)
        self.assertIn("image-index", result.summary)

    def test_invalid_time_record_remains_unknown(self):
        _, image = self.preview()
        parent = image_import.work_directory(self.root)
        record = parent / f"{self.digest}.json"
        for value in ("invalid", json.dumps({"image_id": image.identity,
                                             "imported_at": "2020-01-01T00:00:00"})):
            record.write_text(value)
            self.assertIsNone(image_import.imported_at(self.installation, image.identity))

    def test_changed_archive_does_not_load(self):
        preview, image = self.preview()
        save_archive(self.path, tags=["modified:v1"])
        with patch("managebase.image_import.run_readonly", return_value=b"[]"), \
                patch("managebase.image_import.run_command") as run:
            result = image_import.apply(self.installation, preview, image, "new/name", "v2",
                                        confirmed=True)
        self.assertNotEqual(result.code, 0)
        run.assert_not_called()

    def test_changed_archive_with_identical_stat_does_not_load(self):
        preview, image = self.preview()
        save_archive(self.path, tags=["modified:v1"])
        with patch("managebase.image_import.fingerprint", return_value=preview.fingerprint), \
                patch("managebase.image_import.run_readonly", return_value=b"[]"), \
                patch("managebase.image_import.run_command") as run:
            result = image_import.apply(self.installation, preview, image, "new/name", "v2",
                                        confirmed=True)
        self.assertNotEqual(result.code, 0)
        run.assert_not_called()

    def test_destination_collision_refused_including_docker_alias(self):
        preview, image = self.preview()
        rows = json.dumps([{"Repository": "docker.io/library/alpine", "Tag": "latest",
                            "ID": "sha256:" + "a" * 64}]).encode()
        with patch("managebase.image_import.run_readonly", return_value=rows), \
                patch("managebase.image_import.run_command") as run:
            result = image_import.apply(self.installation, preview, image, "alpine", "latest",
                                        confirmed=True)
        self.assertNotEqual(result.code, 0)
        self.assertIn("未覆盖", result.summary)
        run.assert_not_called()

    def test_success_records_time_and_removes_temporary_archive(self):
        preview, image = self.preview()
        archive_paths = []

        def load(argv, root, **kwargs):
            archive_paths.append(Path(argv[-1]))
            self.assertEqual(argv[-4:-1], ["image", "load", "--input"])
            self.assertTrue(archive_paths[-1].is_file())
            return b""

        with patch("managebase.image_import.run_readonly",
                   side_effect=[b"[]", b"[]", image.identity.encode()]), \
                patch("managebase.image_import.run_command", side_effect=load):
            result = image_import.apply(self.installation, preview, image, "new/name", "v2",
                                        confirmed=True)
        self.assertEqual(result.code, 0, result.summary)
        self.assertFalse(archive_paths[0].exists())
        self.assertEqual(image_import.imported_at(self.installation, image.identity),
                         result.data["imported_at"])

    def test_load_failure_and_post_load_mismatch_do_not_record_success(self):
        preview, image = self.preview()
        for failure in (True, False):
            with patch("managebase.image_import.run_readonly",
                       side_effect=[b"[]", b"[]", b"sha256:wrong"]), \
                    patch("managebase.image_import.run_command",
                          side_effect=ManagementError("Docker failed", 5) if failure else None):
                result = image_import.apply(self.installation, preview, image, "new/name", "v2",
                                            confirmed=True)
            self.assertNotEqual(result.code, 0)
            self.assertTrue(result.data["load_started"])
            self.assertIsNone(image_import.imported_at(self.installation, image.identity))
            self.assertEqual(list((self.root / "state/image-import").glob("load-*")), [])

    def test_low_disk_space_refused(self):
        preview, image = self.preview()
        with patch("managebase.image_import.shutil.disk_usage") as usage, \
                patch("managebase.image_import.run_readonly", return_value=b"[]"), \
                patch("managebase.image_import.run_command") as run:
            usage.return_value.free = 0
            result = image_import.apply(self.installation, preview, image, "new/name", "v2",
                                        confirmed=True)
        self.assertNotEqual(result.code, 0)
        run.assert_not_called()

    def test_compressed_preview_and_stage_with_progress(self):
        for mode in ("w:gz", "w:bz2", "w:xz"):
            save_archive(self.path, mode=mode)
            progress = []
            preview = image_import.inspect(self.path, lambda m, t: progress.append(m))
            staged = self.root / "staged.tar"
            image_import.stage(preview, preview.images[0], "new/name:v2", staged,
                               lambda m, t: progress.append(m))
            self.assertTrue(progress)
            self.assertEqual(image_import.inspect(staged).images[0].repository, "new/name")

    def test_cli_confirmation_and_parameter_scope(self):
        for args in (["image-import", "--archive", str(self.path)],
                     ["image-import", "--yes"],
                     ["status", "--archive", str(self.path)],
                     ["image-import", "--archive", str(self.path), "--yes", "--all"]):
            with contextlib.redirect_stderr(io.StringIO()), \
                    patch("managebase.image_import.run_command") as run:
                self.assertEqual(cli.main([*args, "--root", str(self.root)]), 2)
                run.assert_not_called()

    def test_cli_dry_run_edit_and_multi_selection(self):
        for tags in (["example/old:wrong"], ["example/old:wrong", "example/old:alias"]):
            save_archive(self.path, tags=tags)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch("managebase.image_import.run_command") as run:
                code = cli.main(["image-import", "--root", str(self.root), "--archive", str(self.path),
                                 "--image-index", "1", "--image-name", "new/name", "--image-tag", "v2",
                                 "--dry-run", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["data"]["reference"], "new/name:v2")
            run.assert_not_called()
        result = execute("image-import", self.root, archive=self.path, dry_run=True)
        self.assertEqual(len(result.data["archive_images"]), 2)

    def test_confirmation_default_return_and_escape(self):
        _, image = self.preview()
        for key in ("\n", "\x1b"):
            screen = FormScreen([key])
            with patch("managebase.tui.set_cursor"):
                self.assertIsNone(tui.image_confirmation(screen, image))
            for label in ("镜像名称：", "tag：", "镜像大小：", "确认导入", "返回"):
                self.assertIn(label, screen.frames[0])

    def test_edit_both_fields_then_confirm(self):
        _, image = self.preview()
        keys = [curses.KEY_UP] * 3 + ["\n", "\x15", *"new/name", "\n", curses.KEY_DOWN,
                                     "\n", "\x15", *"v2", "\n", curses.KEY_DOWN, "\n"]
        screen = FormScreen(keys)
        with patch("managebase.tui.set_cursor"):
            self.assertEqual(tui.image_confirmation(screen, image), ("new/name", "v2"))

    def test_cancel_edit_restores_old_value(self):
        _, image = self.preview()
        screen = FormScreen([curses.KEY_UP] * 3 + ["\n", "\x15", *"changed", "\x1b",
                                                  curses.KEY_DOWN, curses.KEY_DOWN, "\n"])
        with patch("managebase.tui.set_cursor"):
            self.assertEqual(tui.image_confirmation(screen, image), ("example/old", "wrong"))

    def test_long_fields_resize_and_horizontal_navigation(self):
        _, image = self.preview()
        image = replace(image, repository="team/" + "a" * 240)
        screen = FormScreen([curses.KEY_RIGHT] * 10 + [(8, 30), (16, 64)] +
                            [curses.KEY_UP] * 3 + ["\n", curses.KEY_HOME, curses.KEY_END, "\x1b", "\x1b"])
        with patch("managebase.tui.set_cursor"):
            self.assertIsNone(tui.image_confirmation(screen, image))
        self.assertIn("确认导入", screen.frames[-1])

    def test_view_cancel_returns_to_path_without_loading(self):
        screen = FormScreen([])
        with patch("managebase.tui.edit_text", side_effect=[str(self.path), None]) as edit, \
                patch("managebase.tui.image_confirmation", return_value=None), \
                patch("managebase.image_import.apply") as apply:
            self.assertEqual(tui.image_import_view(screen, self.root), "主菜单")
        self.assertEqual(edit.call_count, 2)
        apply.assert_not_called()

    def test_view_confirm_passes_edited_target(self):
        screen = FormScreen([])
        with patch("managebase.tui.edit_text", return_value=str(self.path)), \
                patch("managebase.tui.image_confirmation", return_value=("new/name", "v2")), \
                patch("managebase.image_import.apply", return_value=Result("导入完成")) as apply:
            self.assertEqual(tui.image_import_view(screen, self.root), "导入完成")
        self.assertEqual(apply.call_args.args[-2:], ("new/name", "v2"))
        self.assertTrue(apply.call_args.kwargs["confirmed"])
