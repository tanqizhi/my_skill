import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from managebase import cli, locations, location_table
from managebase.layout import Installation
from managebase.model import ManagementError
from managebase.operations import execute
from test_foundation import Fixture


IDENTITY = "a" * 64


class LocationTests(Fixture):
    def query(self, config, records=(), mounts=()):
        files = [
            {"path": str(self.root / path), "modified_at": "2026-09-08T01:00:00+00:00",
             "created_at": None}
            for path in ("deploy/docker/compose.yaml", "config/compose.override.yaml")
        ]
        responses = [json.dumps(config).encode(), json.dumps(records).encode()]
        if records:
            responses.append(json.dumps([{"ID": IDENTITY, "Mounts": mounts}]).encode())
        with patch("managebase.locations.file_metadata", return_value=files):
            with patch("managebase.locations.run_readonly", side_effect=responses) as run:
                result = execute("locations", self.root)
        return result, run

    def test_real_mounts_take_precedence_and_files_are_separate(self):
        data = self.root / "data/api"
        data.mkdir(parents=True)
        config_path = self.root / "config/compose.env"
        result, run = self.query(
            {"services": {"api": {"environment": {"SECRET": "hidden"},
                                 "volumes": [{"type": "bind", "source": "/old"}]}}},
            [{"ID": IDENTITY, "Service": "api"}],
            [{"Type": "bind", "Source": str(data)},
             {"Type": "bind", "Source": str(config_path)},
             {"Type": "tmpfs", "Source": ""}],
        )
        self.assertEqual(result.code, 0)
        row = result.data["locations"][0]
        self.assertEqual(row["persistent_directories"], [str(data)])
        self.assertEqual(row["file_mounts"], [str(config_path)])
        self.assertEqual(row["mount_source"], "actual-containers")
        self.assertEqual(len(row["compose_files"]), 2)
        self.assertNotIn("SECRET", json.dumps(result.as_dict()))
        self.assertNotIn("/old", json.dumps(result.as_dict()))
        self.assertTrue(all(call.args[0][:3] == ["/usr/bin/docker", "--host",
                                                "unix:///var/run/docker.sock"]
                            for call in run.call_args_list))

    def test_no_persistence_and_configured_service_without_container(self):
        result, _ = self.query({"services": {
            "web": {},
            "worker": {"volumes": [{"type": "bind", "source": str(self.root / "data/worker")}]},
        }})
        self.assertEqual(result.code, 0)
        rows = {row["service"]: row for row in result.data["locations"]}
        self.assertEqual(rows["web"]["persistent_directories"], [])
        self.assertEqual(rows["worker"]["mount_source"], "compose-config")
        self.assertIn("不涉及", cli.format_result(result))
        self.assertIn("未知（不支持）", cli.format_result(result))
        self.assertIn("创建日期", cli.format_result(result))

    def test_unnamed_and_unresolved_named_volumes_are_not_marked_absent(self):
        config = {"services": {"api": {"volumes": [
            {"type": "volume"}, {"type": "volume", "source": "external"},
        ]}}, "volumes": {"external": {"name": "external_volume"}}}
        with patch("managebase.locations.file_metadata", return_value=[]):
            with patch("managebase.locations.run_readonly", side_effect=[
                json.dumps(config).encode(), b"[]", ManagementError("unavailable"),
            ]):
                result = execute("locations", self.root)
        self.assertEqual(result.code, 0)
        text = cli.format_result(result)
        self.assertIn("匿名卷", text)
        self.assertIn("external_volume", text)

    def test_actual_named_volume_uses_docker_mountpoint(self):
        result, _ = self.query(
            {"services": {"api": {}}}, [{"ID": IDENTITY, "Service": "api"}],
            [{"Type": "volume", "Source": "/var/lib/docker/volumes/api/_data"}])
        self.assertEqual(result.data["locations"][0]["persistent_directories"],
                         ["/var/lib/docker/volumes/api/_data"])

    def test_missing_inspection_does_not_claim_no_persistence(self):
        with patch("managebase.locations.run_readonly", side_effect=[
            b'{"services":{"api":{}}}',
            json.dumps([{"ID": IDENTITY, "Service": "api"}]).encode(), b"[]",
        ]):
            self.assertEqual(execute("locations", self.root).code, 5)

    def test_bad_output_is_not_disclosed(self):
        with patch("managebase.locations.run_readonly", return_value=b"SECRET"):
            result = execute("locations", self.root)
        self.assertEqual(result.code, 5)
        self.assertNotIn("SECRET", result.summary)

    def test_file_creation_time_uses_birth_time_not_ctime(self):
        installation = Installation.load(self.root)
        metadata = SimpleNamespace(st_mtime=200, st_ctime=999)
        with patch.object(Path, "stat", return_value=metadata):
            with patch("managebase.locations.run_readonly", side_effect=[b"100\n", b"0\n"]):
                files = locations.file_metadata(installation)
        self.assertEqual(files[0]["created_at"], locations.iso_time(100))
        self.assertIsNone(files[1]["created_at"])
        self.assertEqual(files[0]["modified_at"], locations.iso_time(200))

    def test_birth_time_native_and_stat_unavailable(self):
        installation = Installation.load(self.root)
        with patch.object(Path, "stat", return_value=SimpleNamespace(st_mtime=200, st_birthtime=100)):
            with patch("managebase.locations.run_readonly") as run:
                files = locations.file_metadata(installation)
        run.assert_not_called()
        self.assertEqual(files[0]["created_at"], locations.iso_time(100))
        with patch("managebase.locations.run_readonly", side_effect=ManagementError("no stat")):
            files = locations.file_metadata(installation)
        self.assertTrue(all(row["created_at"] is None for row in files))

    def test_empty_and_dry_run(self):
        result, _ = self.query({"services": {}})
        self.assertEqual(result.data["locations"], [])
        self.assertIn("没有服务", location_table.format_table([]))
        with patch("managebase.locations.run_readonly") as run:
            result = execute("locations", self.root, dry_run=True)
        run.assert_not_called()
        self.assertEqual(result.code, 0)
        self.assertEqual(result.data["argv"][-3:], ["config", "--format", "json"])
