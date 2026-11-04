"""Exercise the automatic publisher with real local Git histories and fake GitHub responses."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/auto-update-native.py"
spec = importlib.util.spec_from_file_location("auto_update_native", SCRIPT)
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_cwd = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, self.old_cwd)
        self.release = {
            "tag_name": "v6.21.0-native.5",
            "assets": [
                {"name": "MAA-v6.21.0-native.5-win-x64.zip", "state": "uploaded"}
            ],
        }
        self.output = str(Path("output.txt").resolve())
        self.environment = patch.dict(os.environ, {"GITHUB_OUTPUT": self.output})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def git(self, *args):
        return auto.command("git", *args)

    def seed(self):
        self.git("init", "-b", "native")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.invalid")
        files = {
            "src/MaaCore/CMakeLists.txt": 'set(NATIVE_APP_VERSION "v6.21.0-native.5")\n',
            "src/MaaWpfGui/Services/NativeUpdateService.cs": auto.REPO,
            "src/MaaWpfGui/Services/DebugControlService.cs": "debug-control.json",
            "src/MaaWpfGui/ViewModels/UI/RootViewModel.cs": "NativeCaptureService.EnsureStartedAsync(); DebugControlService.Start();",
            "src/MaaWpfGui/ViewModels/Dialogs/VersionUpdateDialogViewModel.cs": "return NativeUpdateService.CheckAndDownloadAsync();",
            "src/MaaWpfGui/Views/UserControl/Settings/AboutUserControl.xaml": "<UserControl />",
            ".github/native-resource-sync.json": "{}",
            "resource/version.json": '{"last_updated":"old"}',
            "README.md": "original\n",
        }
        for name, content in files.items():
            file = Path(name)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.git("branch", "upstream/dev-v2")
        Path(".gitignore").write_text("output.txt\nbuild-native/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "native")

    def api(self, path):
        if auto.UPSTREAM in path:
            return {"tag_name": "v6.21.0"}
        return self.release

    def prepare(self):
        with patch.object(auto, "api", side_effect=self.api):
            auto.prepare()
        return json.loads(auto.PLAN.read_text(encoding="utf-8"))

    def test_detection_and_check_only(self):
        for behind, paths, check, expected in [
            (0, ["README.md"], False, False),
            (1, [], False, True),
            (0, ["resource/version.json"], False, True),
            (1, [], True, False),
            (0, [".github/scripts/auto-update-native.py"], False, False),
        ]:
            with self.subTest(behind=behind, paths=paths, check=check):
                Path(self.output).unlink(missing_ok=True)
                with patch.object(
                    auto,
                    "api",
                    side_effect=[
                        self.release,
                        {"behind_by": behind},
                        {"files": [{"filename": p} for p in paths]},
                    ],
                ):
                    auto.inspect(check)
                self.assertEqual(
                    Path(self.output).read_text().strip(),
                    "changed=" + str(expected).lower(),
                )
        self.release["assets"] = []
        with patch.object(
            auto, "api", side_effect=[self.release, {"behind_by": 1}, {}]
        ):
            auto.inspect()
        self.assertTrue(Path(self.output).read_text().endswith("changed=false\n"))

    def test_merge_and_version_are_local_until_validation(self):
        self.seed()
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "upstream/dev-v2")
        Path("resource/version.json").write_text('{"last_updated":"new"}')
        self.git("commit", "-am", "official resource update")
        target = self.git("rev-parse", "HEAD")
        self.git("checkout", "native")
        plan = self.prepare()
        self.assertEqual(plan["head"], head)
        self.assertEqual(plan["version"], "v6.21.0-native.6")
        self.assertEqual(plan["validated_commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(
            json.loads(Path(".github/native-resource-sync.json").read_text())[
                "upstream_commit"
            ],
            target,
        )
        self.assertEqual(
            json.loads(Path("resource/version.json").read_text())["last_updated"], "new"
        )
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no"), "")
        self.assertEqual(self.git("remote"), "")

    def test_conflicting_merge_does_not_publish_or_allocate_version(self):
        self.seed()
        Path("README.md").write_text("native edits\n")
        self.git("commit", "-am", "native edits")
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "upstream/dev-v2")
        Path("README.md").write_text("official edits\n")
        self.git("commit", "-am", "official edits")
        self.git("checkout", "native")
        with self.assertRaisesRegex(RuntimeError, "README.md"):
            self.prepare()
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertFalse(auto.PLAN.exists())
        report = json.loads(Path("build-native/merge-conflict.json").read_text())
        self.assertEqual(report["files"], ["README.md"])
        self.assertEqual(report["head"], head)
        self.assertEqual(report["upstream"], self.git("rev-parse", "upstream/dev-v2"))
        self.assertIn(
            f"merge_key=native-merge-v1-{head}-{report['upstream']}",
            Path(self.output).read_text(),
        )

    def test_non_conflict_merge_error_is_not_cached(self):
        self.seed()
        original = auto.command

        def fail_merge(*args):
            if args[:2] == ("git", "merge"):
                raise RuntimeError("temporary git error")
            return original(*args)

        with patch.object(auto, "command", side_effect=fail_merge):
            with self.assertRaisesRegex(RuntimeError, "temporary git error"):
                self.prepare()
        self.assertFalse(Path("build-native/merge-conflict.json").exists())

    def test_command_error_includes_stdout_and_stderr(self):
        result = subprocess.CompletedProcess(
            ["git", "merge"], 1, b"CONFLICT in file.cs", b"merge failed"
        )
        with patch.object(auto.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(
                RuntimeError, "CONFLICT in file.cs\nmerge failed"
            ):
                auto.command("git", "merge")

    def test_missing_background_control_blocks_release(self):
        self.seed()
        Path("src/MaaWpfGui/ViewModels/UI/RootViewModel.cs").write_text(
            "NativeCaptureService.EnsureStartedAsync();"
        )
        self.git("commit", "-am", "removed native hook")
        with self.assertRaisesRegex(RuntimeError, "Background debug control"):
            self.prepare()

    def test_failed_release_can_retry_the_same_version(self):
        self.seed()
        first = self.prepare()
        second = self.prepare()
        third = self.prepare()
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(second["validated_commit"], third["validated_commit"])

    def test_workflow_permission_failure_is_reported_immediately(self):
        self.seed()
        self.prepare()
        original_run = subprocess.run

        def reject_push(args, **kwargs):
            if args[:2] == ["git", "push"]:
                return subprocess.CompletedProcess(
                    args, 1, b"", b"refusing workflow update without workflow scope"
                )
            return original_run(args, **kwargs)

        with patch.object(auto.subprocess, "run", side_effect=reject_push):
            with self.assertRaisesRegex(
                RuntimeError, "requires repo and workflow access"
            ):
                auto.publish()

    def publish_fixture(self, bad_digest=False):
        self.seed()
        plan = self.prepare()
        remote = Path(self.temp.name) / "remote.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        assets = Path("build-native/assets")
        assets.mkdir(parents=True)
        artifacts = {}
        for name in ["program.zip", "full.zip"]:
            data = name.encode()
            (assets / name).write_bytes(data)
            artifacts[name] = hashlib.sha256(data).hexdigest()
            (assets / (name + ".sha256")).write_text(artifacts[name])
        (assets / "native-release.json").write_text(
            json.dumps({"version": plan["version"], "artifacts": artifacts})
        )
        uploaded = []
        published = []
        original_command = auto.command

        def fake_command(*args):
            if args[0] != "gh":
                return original_command(*args)
            if args[2] == "upload":
                uploaded.append(Path(args[4]).name)
            if args[2] == "view":
                return json.dumps(
                    {
                        "assets": [
                            {
                                "name": n,
                                "state": "uploaded",
                                "digest": "sha256:"
                                + ("bad" if bad_digest else artifacts.get(n, "")),
                            }
                            for n in uploaded
                        ]
                    }
                )
            if "--draft=false" in args:
                self.assertEqual(len(uploaded), 5)
                published.append(args)
            return ""

        original_run = subprocess.run

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return subprocess.CompletedProcess(args, 1, b"", b"not found")
            return original_run(args, **kwargs)

        with (
            patch.object(auto, "command", side_effect=fake_command),
            patch.object(auto.subprocess, "run", side_effect=fake_run),
        ):
            if bad_digest:
                with self.assertRaisesRegex(
                    RuntimeError, "Uploaded asset verification"
                ):
                    auto.publish()
            else:
                auto.publish()
        self.assertEqual(bool(published), not bad_digest)

    def test_publish_only_after_all_uploads_and_server_hash_verification(self):
        self.publish_fixture()

    def test_incorrect_server_hash_leaves_release_as_draft(self):
        self.publish_fixture(bad_digest=True)


if __name__ == "__main__":
    unittest.main()
