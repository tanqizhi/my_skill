import contextlib
import errno
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from managebase import cli, compose
from managebase.layout import Installation, REQUIRED_FILES, read_registered
from managebase.model import ManagementError
from managebase.operations import execute
from managebase.runner import run_readonly

PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT / "work/tests"


class Fixture(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "state").mkdir()
        for relative in REQUIRED_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("services: {}\n" if path.suffix == ".yaml" else "", encoding="utf-8")
        self.state = {
            "layout_version": 1, "bundle_name": "example", "bundle_version": "0.1.0",
            "instance_id": "example-one", "install_root": str(self.root),
            "deploy_targets": ["docker"], "storage": [],
            "compose": {
                "project_name": "example-one", "docker_binary": "/usr/bin/docker",
                "files": ["deploy/docker/compose.yaml", "config/compose.override.yaml"],
                "env_files": ["config/compose.env"], "profiles": [],
            },
        }
        self.save()

    def save(self):
        (self.root / "state/installation.json").write_text(json.dumps(self.state), encoding="utf-8")

    def reject(self):
        with self.assertRaises(ManagementError):
            Installation.load(self.root)


class LayoutTests(Fixture):
    def test_valid_layout(self):
        installation = Installation.load(self.root)
        self.assertEqual(installation.project, "example-one")

    def test_relative_root_rejected(self):
        with self.assertRaises(ManagementError):
            Installation.load(Path("."))

    def test_root_identity_mismatch(self):
        self.state["install_root"] = "/unrelated"
        self.save()
        self.reject()

    def test_float_version_rejected(self):
        self.state["layout_version"] = 1.0
        self.save()
        self.reject()

    def test_boolean_version_rejected(self):
        self.state["layout_version"] = True
        self.save()
        self.reject()

    def test_k3s_not_claimed(self):
        self.state["deploy_targets"] = ["k3s"]
        self.save()
        self.reject()

    def test_duplicate_key_rejected(self):
        (self.root / "state/installation.json").write_text(
            '{"layout_version":1,"layout_version":1}', encoding="utf-8")
        self.reject()

    def test_secret_not_in_parse_error(self):
        (self.root / "state/installation.json").write_text(
            '{"password":"SENTINEL-SECRET", broken}', encoding="utf-8")
        result = execute("layout", self.root)
        self.assertNotEqual(result.code, 0)
        self.assertNotIn("SENTINEL", result.summary)

    def test_oversized_state_rejected(self):
        (self.root / "state/installation.json").write_bytes(b" " * 65537)
        self.reject()

    def test_symlink_file_rejected(self):
        path = self.root / "config/compose.env"
        path.unlink()
        path.symlink_to(self.root / "bundle.yaml")
        self.reject()

    def test_symlink_directory_rejected(self):
        config = self.root / "config"
        config.rename(self.root / "other")
        config.symlink_to(self.root / "other", target_is_directory=True)
        self.reject()

    def test_fifo_rejected_without_hanging(self):
        path = self.root / "config/compose.env"
        path.unlink()
        try:
            os.mkfifo(path)
        except OSError as error:
            if error.errno == errno.EOPNOTSUPP:
                self.skipTest("This mounted filesystem cannot create POSIX FIFOs.")
            raise
        self.reject()

    def test_nonregular_file_rejected(self):
        with patch("managebase.layout.os.fstat", return_value=SimpleNamespace(st_mode=0o010600)):
            with self.assertRaises(ManagementError):
                read_registered(self.root, "bundle.yaml")

    def test_missing_file_rejected(self):
        (self.root / "deploy/docker/compose.yaml").unlink()
        self.reject()

    def test_traversal_rejected(self):
        with self.assertRaises(ManagementError):
            read_registered(self.root, "../bundle.yaml")

    def test_compose_order_is_fixed(self):
        self.state["compose"]["files"].reverse()
        self.save()
        self.reject()

    def test_project_option_injection_rejected(self):
        self.state["compose"]["project_name"] = "--help"
        self.save()
        self.reject()

    def test_duplicate_profiles_rejected(self):
        self.state["compose"]["profiles"] = ["api", "api"]
        self.save()
        self.reject()

    def test_readonly_leaves_files_identical(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(execute("layout", self.root).code, 0)
        self.assertEqual(execute("status", self.root, dry_run=True).code, 0)
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class OperationTests(Fixture):
    def test_dry_run_does_not_spawn(self):
        with patch("subprocess.Popen") as spawn:
            result = execute("status", self.root, dry_run=True)
        spawn.assert_not_called()
        self.assertEqual(result.code, 0)
        args = result.data["argv"]
        self.assertEqual(args[:3], ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"])
        self.assertIn(str(self.root / "config/compose.env"), args)
        self.assertIn("--no-trunc", args)
        self.assertNotIn("--pull", args)

    def test_status_filters_private_fields(self):
        payload = b'[{"Service":"api","State":"running","Health":"healthy","Labels":"SECRET"}]'
        with patch("managebase.compose.run_readonly", return_value=payload):
            result = execute("status", self.root)
        self.assertEqual(result.code, 0)
        self.assertNotIn("SECRET", json.dumps(result.as_dict()))
        self.assertEqual(result.data["services"][0]["service"], "api")

    def test_ndjson_status(self):
        payload = b'{"Service":"api","State":"running"}\n{"Service":"db","State":"exited"}\n'
        with patch("managebase.compose.run_readonly", return_value=payload):
            self.assertEqual(len(compose.services(Installation.load(self.root))), 2)

    def test_invalid_status_hidden(self):
        with patch("managebase.compose.run_readonly", return_value=b"SECRET-invalid-json"):
            result = execute("status", self.root)
        self.assertEqual(result.code, 5)
        self.assertNotIn("SECRET", result.summary)

    def test_status_inspects_exact_times_image_and_restart_count(self):
        identity = "a" * 64
        payload = json.dumps([{"ID": identity, "Name": "project-api-1",
                               "Service": "api", "State": "running"}]).encode()
        inspected = json.dumps({
            "ID": identity, "CreatedAt": "2026-09-09T01:00:00Z",
            "StartedAt": "2026-09-09T02:00:00Z", "State": "running",
            "Health": "healthy", "Image": "registry/api:v2", "ImageID": "sha256:" + "b" * 64,
            "RestartCount": 2, "Env": ["SECRET"],
        }).encode()
        with patch("managebase.compose.run_readonly", side_effect=[payload, inspected]) as run:
            result = execute("status", self.root)
        self.assertEqual(result.code, 0)
        row = result.data["services"][0]
        self.assertEqual(row["created_at"], "2026-09-09T01:00:00Z")
        self.assertEqual(row["started_at"], "2026-09-09T02:00:00Z")
        self.assertEqual(row["image"], "registry/api:v2")
        self.assertEqual(row["restart_count"], 2)
        self.assertNotIn("SECRET", json.dumps(result.as_dict()))
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"])
        self.assertEqual(args[-1], identity)
        self.assertIn("--type", args)
        self.assertNotIn(".Config.Env", args[-2])

    def test_status_rejects_invalid_id_before_inspect(self):
        payload = b'[{"ID":"--help","Service":"api"}]'
        with patch("managebase.compose.run_readonly", return_value=payload) as run:
            result = execute("status", self.root)
        self.assertEqual(result.code, 5)
        self.assertEqual(run.call_count, 1)

    def test_status_rejects_missing_inspection(self):
        payload = json.dumps([{"ID": "a" * 64, "Service": "api"}]).encode()
        with patch("managebase.compose.run_readonly", side_effect=[payload, b""]):
            self.assertEqual(execute("status", self.root).code, 5)

    def test_status_batches_many_containers_and_keeps_replicas(self):
        records = [{"ID": f"{index:064x}", "Service": "api", "Name": f"api-{index:03}"}
                   for index in range(130)]
        inspected = [{"ID": row["ID"], "RestartCount": 0} for row in records]
        outputs = [json.dumps(records).encode()]
        outputs.extend("\n".join(json.dumps(row) for row in inspected[start:start + 64]).encode()
                       for start in range(0, 130, 64))
        with patch("managebase.compose.run_readonly", side_effect=outputs) as run:
            result = execute("status", self.root)
        self.assertEqual(result.code, 0)
        self.assertEqual(len(result.data["services"]), 130)
        self.assertEqual(run.call_count, 4)

    def test_empty_status_never_inspects(self):
        with patch("managebase.compose.run_readonly", return_value=b"[]") as run:
            result = execute("status", self.root)
        self.assertEqual(result.data["services"], [])
        self.assertEqual(run.call_count, 1)
        self.assertIn("没有容器", cli.format_result(result))

    def test_config_check_hides_rendered_content(self):
        with patch("managebase.operations.run_readonly", return_value=b"SECRET") as runtime:
            result = execute("config-check", self.root)
        self.assertEqual(result.code, 0)
        self.assertNotIn("SECRET", result.summary)
        self.assertEqual(runtime.call_args.args[0][-2:], ["config", "--quiet"])

    def test_unknown_operation(self):
        self.assertEqual(execute("unknown", self.root).code, 2)


class RunnerTests(Fixture):
    def test_environment_isolation(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "tcp://evil", "BUSINESS_SECRET": "SECRET"}):
            output = run_readonly(
                [sys.executable, "-c", "import os,json;print(json.dumps(dict(os.environ)))"],
                self.root)
        self.assertNotIn(b"tcp://evil", output)
        self.assertNotIn(b"BUSINESS_SECRET", output)

    def test_failure_output_is_not_disclosed(self):
        with self.assertRaises(ManagementError) as raised:
            run_readonly([sys.executable, "-c",
                          "import sys;print('SECRET',file=sys.stderr);sys.exit(7)"], self.root)
        self.assertNotIn("SECRET", str(raised.exception))
        self.assertIn("7", str(raised.exception))

    def test_timeout(self):
        with self.assertRaises(ManagementError):
            run_readonly([sys.executable, "-c", "import time;time.sleep(10)"],
                         self.root, timeout=0.1)

    def test_output_limit(self):
        with self.assertRaises(ManagementError):
            run_readonly([sys.executable, "-c", "print('x'*20000)"],
                         self.root, max_output=512)

    def test_missing_program(self):
        with self.assertRaises(ManagementError) as raised:
            run_readonly(["/does-not-exist/docker"], self.root)
        self.assertEqual(raised.exception.code, 4)


class CliTests(Fixture):
    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, str(PROJECT / "manage.py"), *args],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True, timeout=5,
        )

    def test_no_arguments_without_tty(self):
        self.assertEqual(self.invoke().returncode, 2)

    def test_help(self):
        self.assertEqual(self.invoke("--help").returncode, 0)

    def test_unknown_command_never_prompts(self):
        self.assertEqual(self.invoke("erase").returncode, 2)

    def test_missing_command_never_prompts(self):
        self.assertEqual(self.invoke("--root", str(self.root)).returncode, 2)

    def test_from_unrelated_cwd(self):
        result = self.invoke("layout", "--root", str(self.root), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "success")

    def test_json_failure(self):
        result = self.invoke("layout", "--root", "/does-not-exist", "--json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["status"], "failed")

    def test_cli_does_not_import_curses(self):
        with patch("builtins.__import__", wraps=__import__) as imported:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["doctor"]), 0)
        self.assertFalse(any(call.args[0] in ("curses", "managebase.tui")
                             for call in imported.call_args_list))
