import copy
import curses
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
from unittest.mock import patch

from managebase import backups, changes, compose, config_io, tui
from managebase.layout import Installation
from managebase.model import ManagementError, Result
from managebase.operations import execute
from test_foundation import Fixture, PROJECT
from test_image_import import FormScreen
from test_status_table import Screen

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64


class ChangeFixture(Fixture):
    def setUp(self):
        with patch("test_foundation.WORK", Path(tempfile.gettempdir()) / "managebase-change-tests"):
            super().setUp()
        (self.root / "state/locks").mkdir()
        self.base = {"services": {"api": {"image": "old:v1"}, "db": {"image": "db:v1"}}}
        (self.root / "deploy/docker/compose.yaml").write_bytes(config_io.encode(self.base))
        (self.root / config_io.OVERRIDE).write_bytes(
            b"# operator comment\nservices:\n  api:\n    environment:\n      VALUE: '${VALUE:-yes}'\n")
        self.installation = Installation.load(self.root)
        self.row = {"service": "api", "container": "test-api", "id": "c" * 64,
                    "image_id": OLD, "state": "running", "health": "healthy"}

    def render(self, installation, *, override=None):
        base = config_io.decode((self.root / "deploy/docker/compose.yaml").read_bytes())
        other = config_io.decode((override or self.root / config_io.OVERRIDE).read_bytes())
        result = copy.deepcopy(base)
        for group, values in other.items():
            target = result.setdefault(group, {})
            for name, value in values.items():
                if name in target and isinstance(value, dict):
                    target[name].update(copy.deepcopy(value))
                else:
                    target[name] = copy.deepcopy(value)
        return result

    def reads(self, argv, root, **kwargs):
        if "{{json .Config.Volumes}}" in argv:
            return b"null"
        if "config-hash" in " ".join(argv):
            return b"expected"
        if "--hash" in argv:
            return b"api expected"
        raise AssertionError(argv)

    def image(self, installation, reference):
        return OLD if reference in ("old:v1", OLD) else NEW

    def mocks(self):
        self.enterContext(patch("managebase.changes.compose.configuration", side_effect=self.render))
        self.enterContext(patch("managebase.changes.compose.services", return_value=[self.row]))
        self.enterContext(patch("managebase.changes.local_image", side_effect=self.image))
        self.enterContext(patch("managebase.changes.run_readonly", side_effect=self.reads))

    def switch(self):
        self.mocks()
        return changes.prepare_switch(self.installation, "api", "new:v2")


class ChangeTests(ChangeFixture):
    def test_yaml_round_trip_keeps_comments_quotes_and_interpolation(self):
        plan = self.switch()
        self.assertIn(b"# operator comment", plan.candidate)
        self.assertIn(b"'${VALUE:-yes}'", plan.candidate)
        self.assertEqual(config_io.decode(plan.candidate)["services"]["api"]["image"], NEW)
        self.assertEqual(plan.inputs, config_io.snapshot(self.installation))

    def test_invalid_duplicate_yaml_and_unsafe_objects(self):
        for raw in (b"services: {}\nservices: {}", b"- list", b"services: ["):
            with self.assertRaises(ManagementError):
                config_io.decode(raw)
        # Round-trip loading must never construct arbitrary Python objects.
        config_io.decode(b"x-item: !!python/object/apply:os.system ['false']\nservices: {}\n")

    def test_only_chosen_service_changes(self):
        plan = self.switch()
        before = self.render(self.installation)
        after = changes.candidate_config(self.installation, plan.candidate)
        self.assertEqual(before["services"]["db"], after["services"]["db"])
        changed = copy.deepcopy(after)
        changed["services"]["db"]["image"] = NEW
        with self.assertRaises(ManagementError):
            changes.verify_unchanged_services(before, changed, "api")

    def test_no_confirm_no_writes(self):
        plan = self.switch()
        with patch("managebase.changes.run_command") as run:
            result = changes.apply(plan)
        self.assertEqual(result.code, 2)
        run.assert_not_called()
        self.assertFalse((self.root / "backups").exists())

    def test_same_image_is_no_op(self):
        self.mocks()
        plan = changes.prepare_switch(self.installation, "api", OLD)
        self.assertTrue(plan.no_change)
        with patch("managebase.changes.run_command") as run:
            result = changes.apply(plan, confirmed=True)
        self.assertEqual(result.code, 0)
        run.assert_not_called()
        self.assertFalse((self.root / "backups").exists())

    def test_dirty_compose_hash_refused(self):
        self.mocks()
        with patch("managebase.changes.run_readonly", side_effect=[b"null", b"api newhash", b"oldhash"]):
            with self.assertRaisesRegex(ManagementError, "尚未应用"):
                changes.prepare_switch(self.installation, "api", NEW)

    def test_changed_config_or_container_refuses_apply(self):
        plan = self.switch()
        (self.root / config_io.OVERRIDE).write_text("services: {}\n")
        with patch("managebase.changes.run_command") as run:
            self.assertNotEqual(changes.apply(plan, confirmed=True).code, 0)
            run.assert_not_called()
        (self.root / config_io.OVERRIDE).write_bytes(plan.inputs[config_io.OVERRIDE])
        with patch("managebase.changes.compose.services", return_value=[]), \
                patch("managebase.changes.run_command") as run:
            self.assertNotEqual(changes.apply(plan, confirmed=True).code, 0)
            run.assert_not_called()

    def test_success_backs_up_and_only_recreates_target(self):
        plan = self.switch()
        with patch("managebase.changes.run_command", return_value=b"") as run, \
                patch("managebase.changes.wait_service", return_value=[]):
            result = changes.apply(plan, confirmed=True)
        self.assertEqual(result.code, 0, result.summary)
        args = run.call_args.args[0]
        self.assertEqual(args[-1], "api")
        self.assertIn("--no-deps", args)
        self.assertIn("--no-build", args)
        self.assertEqual(args[args.index("--pull") + 1], "never")
        self.assertNotIn("--remove-orphans", args)
        backup = Path(result.data["backup"])
        self.assertEqual((backup / config_io.OVERRIDE).read_bytes(), plan.inputs[config_io.OVERRIDE])
        self.assertEqual((self.root / config_io.OVERRIDE).read_bytes(), plan.candidate)
        self.assertEqual(json.loads((backup / "result.json").read_text())["status"], "complete")

    def test_failure_restores_old_config_and_image(self):
        plan = self.switch()
        with patch("managebase.changes.run_command", side_effect=[ManagementError("failed", 5), b""]) as run, \
                patch("managebase.changes.wait_service", return_value=[]):
            result = changes.apply(plan, confirmed=True)
        self.assertEqual(result.code, 5)
        self.assertTrue(result.data["recovery"]["runtime_restored"])
        self.assertEqual((self.root / config_io.OVERRIDE).read_bytes(), plan.inputs[config_io.OVERRIDE])
        self.assertEqual(run.call_count, 2)

    def test_failure_does_not_overwrite_concurrent_edits(self):
        plan = self.switch()
        changed = b"# manual concurrent change\nservices: {}\n"

        def fail(*args, **kwargs):
            (self.root / config_io.OVERRIDE).write_bytes(changed)
            raise ManagementError("failed", 5)

        with patch("managebase.changes.run_command", side_effect=fail) as run:
            result = changes.apply(plan, confirmed=True)
        self.assertEqual(run.call_count, 1)
        self.assertTrue(result.data["recovery"]["recovery_incomplete"])
        self.assertEqual((self.root / config_io.OVERRIDE).read_bytes(), changed)

    def test_add_creates_only_new_service_without_starting(self):
        self.mocks()
        source = self.root / "input.yaml"
        source.write_text("services:\n  new-api:\n    image: new:v1\n")
        plan = changes.prepare_add(self.installation, "new-api", source)
        self.assertEqual(set(self.render(self.installation)["services"]), {"api", "db"})
        with patch("managebase.changes.run_command", return_value=b"") as run, \
                patch("managebase.changes.wait_service", return_value=[]) as wait:
            result = changes.apply(plan, confirmed=True)
        self.assertEqual(result.code, 0, result.summary)
        self.assertIn("--no-start", run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-1], "new-api")
        self.assertFalse(wait.call_args.kwargs["running"])
        self.assertIn("new-api", self.render(self.installation)["services"])

    def test_add_refuses_existing_name_and_unsafe_input(self):
        self.mocks()
        source = self.root / "input.yaml"
        source.write_text("services: {api: {image: new:v1}}")
        with self.assertRaises(ManagementError):
            changes.prepare_add(self.installation, "api", source)
        for definition in (
            {"extends": "another", "image": "new:v1"},
            {"image": "new:v1", "env_file": "/etc/passwd"},
            {"image": "new:v1", "profiles": ["not-registered"]},
        ):
            source.write_bytes(config_io.encode({"services": {"new-api": definition}}))
            with self.assertRaises(ManagementError):
                changes.prepare_add(self.installation, "new-api", source)

    def test_storage_contract_and_image_anonymous_volumes(self):
        with self.assertRaises(ManagementError):
            changes.validate_storage(self.installation, "new-api", {"volumes": [
                {"type": "bind", "source": "/etc", "target": "/data"}]})
        changes.validate_storage(self.installation, "new-api", {"volumes": [
            {"type": "bind", "source": str(self.root / "data/new-api"), "target": "/data"}]})
        self.mocks()
        source = self.root / "input.yaml"
        source.write_text("services: {new-api: {image: new:v1}}")
        with patch("managebase.changes.run_readonly", return_value=b'{"/data":{}}'):
            with self.assertRaisesRegex(ManagementError, "VOLUME"):
                changes.prepare_add(self.installation, "new-api", source)

    def test_new_cli_commands_require_confirmation_and_validate_option_scope(self):
        for name in (*changes.COMMANDS, *backups.COMMANDS):
            self.assertEqual(execute(name, self.root).code, 2)
        self.assertEqual(execute("status", self.root, service="api").code, 2)
        self.assertEqual(execute("service-add", self.root, image="new:v1", yes=True).code, 2)
        self.assertEqual(execute("image-switch", self.root, yes=True).code, 2)


class BackupTests(ChangeFixture):
    def setUp(self):
        super().setUp()
        self.enterContext(patch("managebase.backups.compose.configuration", side_effect=self.render))
        self.enterContext(patch("managebase.backups.locations.locations", return_value=[]))
        self.data = self.root / "data/api"
        self.data.mkdir(parents=True)
        (self.data / "payload.txt").write_text("backup-content")
        (self.root / "data/db").mkdir()
        (self.root / "data/db/private.txt").write_text("unselected")

    def test_selected_data_only_and_gzip_contents(self):
        plan = backups.prepare(self.installation, "backup-data", service="api")
        result = backups.apply(plan, confirmed=True)
        self.assertEqual(result.code, 0, result.summary)
        path = Path(result.data["path"])
        with tarfile.open(path, "r:gz") as archive:
            self.assertEqual(archive.extractfile("data/api/payload.txt").read(), b"backup-content")
            self.assertNotIn("data/db/private.txt", archive.getnames())
            manifest = json.load(archive.extractfile("backup-manifest.json"))
            self.assertFalse(manifest["database_consistent"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_all_services_and_compose_original_files(self):
        plan = backups.prepare(self.installation, "backup-compose", all_services=True)
        result = backups.apply(plan, confirmed=True)
        self.assertEqual(result.code, 0)
        with tarfile.open(result.data["path"], "r:gz") as archive:
            self.assertEqual(archive.extractfile(config_io.OVERRIDE).read(),
                             plan.inputs[config_io.OVERRIDE])
            self.assertEqual(json.load(archive.extractfile("backup-manifest.json"))["selected_services"],
                             ["api", "db"])
        plan = backups.prepare(self.installation, "backup-data", all_services=True)
        result = backups.apply(plan, confirmed=True)
        with tarfile.open(result.data["path"], "r:gz") as archive:
            self.assertIn("data/db/private.txt", archive.getnames())

    def test_cancel_never_creates_output(self):
        plan = backups.prepare(self.installation, "backup-compose", service="api")
        self.assertEqual(backups.apply(plan).code, 2)
        self.assertFalse((self.root / "backups").exists())

    def test_destination_extension_no_overwrite_and_no_data_recursion(self):
        plan = backups.prepare(self.installation, "backup-data", service="api")
        self.assertTrue(str(backups.destination(plan, self.root / "custom")).endswith(".tar.gz"))
        for output in (self.data / "copy.tar.gz", self.root / "config/copy.tar.gz", Path("relative")):
            with self.assertRaises(ManagementError):
                backups.destination(plan, output)
        output = self.root / "existing.tar.gz"
        output.write_bytes(b"existing")
        result = backups.apply(plan, output, confirmed=True)
        self.assertNotEqual(result.code, 0)
        self.assertEqual(output.read_bytes(), b"existing")

    def test_empty_service_has_no_backup(self):
        self.base["services"]["empty"] = {"image": "new:v1"}
        (self.root / "deploy/docker/compose.yaml").write_bytes(config_io.encode(self.base))
        plan = backups.prepare(self.installation, "backup-data", service="empty")
        result = backups.apply(plan, confirmed=True)
        self.assertEqual(result.code, 0)
        self.assertIn("不涉及", result.summary)
        self.assertFalse(plan.default_path().exists())

    def test_symlinks_stored_not_followed_and_external_mount_refused(self):
        (self.data / "outside").symlink_to(self.root / "data/db/private.txt")
        plan = backups.prepare(self.installation, "backup-data", service="api")
        result = backups.apply(plan, confirmed=True)
        with tarfile.open(result.data["path"], "r:gz") as archive:
            self.assertTrue(archive.getmember("data/api/outside").issym())
            self.assertNotIn("data/db/private.txt", archive.getnames())
        with patch("managebase.backups.locations.locations", return_value=[
            {"service": "api", "persistent_directories": ["/var/lib/external"], "file_mounts": []}
        ]):
            with self.assertRaises(ManagementError):
                backups.prepare(self.installation, "backup-data", service="api")

    def test_changed_file_is_not_published(self):
        plan = backups.prepare(self.installation, "backup-data", service="api")
        original = backups.add_data

        def changed(*args, **kwargs):
            original(*args, **kwargs)
            (self.data / "payload.txt").write_text("changed-after-read")

        with patch("managebase.backups.add_data", side_effect=changed):
            result = backups.apply(plan, confirmed=True)
        self.assertNotEqual(result.code, 0)
        self.assertFalse(plan.default_path().exists())
        self.assertFalse(list(plan.default_path().parent.glob("*.partial")))

    def test_output_race_never_replaces_other_file(self):
        plan = backups.prepare(self.installation, "backup-data", service="api")
        target = plan.default_path()
        original = backups.add_data

        def raced(*args, **kwargs):
            original(*args, **kwargs)
            target.write_bytes(b"another-writer")

        with patch("managebase.backups.add_data", side_effect=raced):
            result = backups.apply(plan, confirmed=True)
        self.assertNotEqual(result.code, 0)
        self.assertEqual(target.read_bytes(), b"another-writer")


class WorkflowTests(ChangeFixture):
    def test_searchable_images_keep_original_index_and_allow_no_matches(self):
        screen = Screen([*"redis", "\n"])
        self.assertEqual(tui.choose(screen, "镜像", [], ["mysql:v1", "redis:v2"], searchable=True), 1)
        screen = Screen([*"missing", "\n", "\x15", curses.KEY_DOWN, "\n"])
        self.assertEqual(tui.choose(screen, "镜像", [], ["mysql:v1", "redis:v2"], searchable=True), 1)
        self.assertTrue(any("没有匹配项" in frame for frame in screen.frames))

    def test_two_field_form_edit_and_default_return(self):
        with patch("managebase.tui.set_cursor"):
            self.assertIsNone(tui.input_form(FormScreen(["\n"]), "增加服务", [("服务名", ""), ("文件", "")]))
            screen = FormScreen([curses.KEY_UP] * 3 + ["\n", *"api", "\n", curses.KEY_DOWN,
                                                       "\n", *"/tmp/input.yaml", "\n", curses.KEY_DOWN, "\n"])
            self.assertEqual(tui.input_form(screen, "增加服务", [("服务名", ""), ("文件", "")]),
                             ("api", "/tmp/input.yaml"))

    def test_switch_four_levels_default_back_does_not_execute(self):
        self.mocks()
        inventory = [{"repository": "new", "tag": "v1", "size": "1MB", "id": NEW}]
        with patch("managebase.tui.choose", side_effect=[0, 0, 1, None, None]) as choose, \
                patch("managebase.tui.images.inventory", return_value=inventory), \
                patch("managebase.changes.apply") as apply:
            self.assertEqual(tui.image_switch_view(Screen([]), self.root), "主菜单")
        apply.assert_not_called()
        self.assertEqual(choose.call_args_list[2].kwargs["selected"], 1)
        self.assertIn("最终确认", choose.call_args_list[2].args[1])

    def test_switch_confirm_executes_frozen_plan(self):
        self.mocks()
        with patch("managebase.tui.choose", side_effect=[0, 0, 0]), \
                patch("managebase.tui.images.inventory", return_value=[
                    {"repository": "new", "tag": "v1", "size": "1MB", "id": NEW}]), \
                patch("managebase.changes.apply", return_value=Result("切换完成")) as apply:
            self.assertEqual(tui.image_switch_view(Screen([]), self.root), "切换完成")
        self.assertTrue(apply.call_args.kwargs["confirmed"])
        self.assertEqual(apply.call_args.args[0].service, "api")

    def test_backup_all_last_and_third_level_tar_gz(self):
        self.mocks()
        plan = backups.Plan(self.installation, "backup-compose", ("api", "db"), (self.root,),
                            config_io.snapshot(self.installation), "test-backup")
        with patch("managebase.tui.choose", side_effect=[2, None]) as choose, \
                patch("managebase.backups.prepare", return_value=plan) as prepare, \
                patch("managebase.tui.input_form", return_value=None) as form, \
                patch("managebase.backups.apply") as apply:
            self.assertEqual(tui.backup_view(Screen([]), self.root, "backup-compose"), "主菜单")
        self.assertEqual(choose.call_args_list[0].args[3][-1], "我全都要")
        self.assertTrue(prepare.call_args.kwargs["all_services"])
        self.assertTrue(any("tar.gz" in note for note in form.call_args.kwargs["notes"]))
        apply.assert_not_called()


class RealComposeTests(ChangeFixture):
    def setUp(self):
        super().setUp()
        binary = Path(os.environ.get("MANAGEBASE_TEST_DOCKER",
                                     str(PROJECT / "work/test-runtime/docker")))
        plugin = Path(os.environ.get("MANAGEBASE_TEST_COMPOSE_DIR",
                                     str(PROJECT / "work/test-runtime/compose")))
        if not binary.is_file() or not (plugin / "docker-compose").is_file():
            self.skipTest("Bundled Compose CLI not available for local parser integration")
        directory = self.root / "config/services/installer/docker-cli"
        directory.mkdir(parents=True)
        (directory / "config.json").write_text(json.dumps({"cliPluginsExtraDirs": [str(plugin)]}))
        self.state["compose"].update(docker_binary=str(binary),
                                     docker_config="config/services/installer/docker-cli")
        self.save()
        self.installation = Installation.load(self.root)

    def test_real_compose_round_trip_and_image_only_scope(self):
        before = compose.configuration(self.installation)
        document = config_io.decode((self.root / config_io.OVERRIDE).read_bytes())
        document["services"]["api"]["image"] = NEW
        after = changes.candidate_config(self.installation, config_io.encode(document))
        changes.verify_unchanged_services(before, after, "api")
        self.assertEqual(after["services"]["api"]["image"], NEW)
        self.assertEqual(before["services"]["api"]["environment"], after["services"]["api"]["environment"])

    def test_real_compose_rejects_invalid_candidate_without_replacing_config(self):
        before = config_io.snapshot(self.installation)
        with self.assertRaises(ManagementError):
            changes.candidate_config(self.installation, b"services: {api: {ports: invalid}}")
        self.assertEqual(before, config_io.snapshot(self.installation))
        self.assertFalse(list((self.root / "config").glob(".manage-preview-*")))

    def test_real_compose_add_preparation_preserves_other_services(self):
        source = self.root / "new.yaml"
        source.write_text("services:\n  new-api:\n    image: local/new:v1\n")
        with patch("managebase.changes.compose.services", return_value=[]), \
                patch("managebase.changes.local_image", return_value=NEW), \
                patch("managebase.changes.run_readonly", return_value=b"null"):
            plan = changes.prepare_add(self.installation, "new-api", source)
        self.assertIn("new-api", changes.candidate_config(self.installation, plan.candidate)["services"])
