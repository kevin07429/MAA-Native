"""Exercise the automatic publisher with real local Git histories and fake GitHub responses."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/auto-update-native.py"
spec = importlib.util.spec_from_file_location("auto_update_native", SCRIPT)
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)
resolver_spec = importlib.util.spec_from_file_location(
    "resolve_update_conflicts", SCRIPT.with_name("resolve-update-conflicts.py")
)
resolver = importlib.util.module_from_spec(resolver_spec)
resolver_spec.loader.exec_module(resolver)
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
            "src/MaaWpfGui/ViewModels/UI/RootViewModel.cs": "NativeCaptureService.EnsureStartedAsync(); DebugControlService.Start(); _ = StartupIntegrityCheckAndUpdateAsync();",
            "src/MaaWpfGui/ViewModels/Dialogs/VersionUpdateDialogViewModel.cs": "return NativeUpdateService.CheckAndDownloadAsync();",
            "src/MaaWpfGui/ViewModels/UserControl/Settings/VersionUpdateSettingsUserControlModel.cs": "    public async Task ManualUpdateResource()\n    {\n        await ResourceUpdater.ResourceUpdateAndReloadAsync();\n    }\n\n    // UI ",
            "src/MaaWpfGui/Views/UserControl/Settings/VersionUpdateSettingsUserControl.xaml": "<UserControl />\n",
            "src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml": "<UserControl />\n",
            "src/MaaWpfGui/Models/ResourceUpdater.cs": "class ResourceUpdater {}\n",
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

    def test_known_conflict_resolver_applies_selected_side(self):
        root = Path(self.temp.name) / "src/MaaWpfGui"
        target = root / "ViewModels/Dialogs/VersionUpdateDialogViewModel.cs"
        target.parent.mkdir(parents=True)
        target.write_text(
            "before\n<<<<<<< HEAD\nnative\n=======\nupstream\n>>>>>>> dev-v2\nafter\n"
        )
        with patch.object(resolver, "ROOT", root):
            resolver.resolve(
                Path("ViewModels/Dialogs/VersionUpdateDialogViewModel.cs"),
                lambda native, upstream: native,
            )
        self.assertEqual(target.read_text(), "before\nnative\nafter\n")

    def test_real_guide_redesign_preserves_one_native_panel_and_agreement(self):
        self.seed()
        guide = Path("src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml")
        fixture = (FIXTURES / "guide-upstream-redesign.xaml.conflict").read_text(
            encoding="utf-8-sig"
        )
        for variant in (
            fixture,
            fixture.replace("                                    ", "    "),
            re.sub(r"<!--.*?-->", "", fixture, flags=re.DOTALL),
            fixture.replace("\n", "\r\n"),
        ):
            with self.subTest(reindented=variant != fixture):
                guide.write_text(variant, encoding="utf-8")
                resolver.main()
                resolved = guide.read_text(encoding="utf-8")
                ET.fromstring(resolved)
                self.assertEqual(resolved.count("About.NativeEditionInfo"), 1)
                self.assertEqual(resolved.count("Guide.ViewLog"), 1)
                self.assertEqual(resolved.count("Guide.Agreement.Link"), 1)
                self.assertNotIn("Guide.Documentation.Title", resolved)
                self.assertNotIn("Guide.GitHubIssue.Title", resolved)
                self.assertNotIn("<<<<<<<", resolved)

    def test_guide_partial_hunk_keeps_shared_agreement_and_other_upstream_changes(self):
        self.seed()
        guide = Path("src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml")
        guide.write_text(
            '<UserControl xmlns:controls="urn:controls">\n'
            "<UpstreamImprovement />\n<Panel>\n<<<<<<< HEAD\n"
            '<controls:TextBlock Text="{DynamicResource About.NativeEditionInfo}" />\n'
            '<controls:TextBlock Text="{DynamicResource Guide.ViewLog}" />\n'
            "=======\n<UpstreamIntroduction />\n>>>>>>> dev-v2\n"
            '<Agreement Key="Guide.Agreement.Link" />\n</Panel>\n</UserControl>\n',
            encoding="utf-8",
        )
        resolver.main()
        result = guide.read_text(encoding="utf-8")
        ET.fromstring(result)
        self.assertIn("UpstreamImprovement", result)
        self.assertEqual(result.count("Guide.Agreement.Link"), 1)
        self.assertNotIn("UpstreamIntroduction", result)

    def test_unrecognized_guide_conflict_is_not_silently_discarded(self):
        self.seed()
        guide = Path("src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml")
        original = "<UserControl>\n<<<<<<< HEAD\n<Unrelated />\n=======\n<NewFeature />\n>>>>>>> dev-v2\n</UserControl>\n"
        guide.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Unrecognized guide conflict"):
            resolver.main()
        self.assertEqual(guide.read_text(encoding="utf-8"), original)

    def test_resolver_rejects_leftover_markers_before_writing(self):
        target = Path("src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml")
        target.parent.mkdir(parents=True)
        original = "<UserControl>\n<<<<<<< HEAD\nunclosed conflict\n</UserControl>\n"
        target.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            resolver.resolve(
                Path("Views/UserControl/GuideUserControl.xaml"), lambda a, b: a
            )
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_resolver_rejects_invalid_xaml_before_writing(self):
        target = Path("src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml")
        target.parent.mkdir(parents=True)
        original = "<UserControl>\n<<<<<<< HEAD\n<Broken>\n=======\n<Valid />\n>>>>>>> dev-v2\n</UserControl>\n"
        target.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "XAML"):
            resolver.resolve(
                Path("Views/UserControl/GuideUserControl.xaml"), lambda a, b: a
            )
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_known_resource_and_localization_conflicts_still_resolve(self):
        self.seed()
        resources = Path("src/MaaWpfGui/Models/ResourceUpdater.cs")
        resources.write_text(
            "class ResourceUpdater {\n<<<<<<< HEAD\n            NativePreparation();\n"
            "            var (ret, uri, releaseNote) = OldCall();\n=======\n"
            "            var (ret, uri, releaseNote) = NewCall();\n>>>>>>> dev-v2\n}\n",
            encoding="utf-8",
        )
        localization = Path("src/MaaWpfGui/Res/Localizations/en-us.xaml")
        localization.parent.mkdir(parents=True)
        localization.write_text(
            "<Resources>\n<<<<<<< HEAD\n<Native />\n=======\n<Upstream />\n>>>>>>> dev-v2\n</Resources>\n",
            encoding="utf-8",
        )
        resolver.main()
        result = resources.read_text(encoding="utf-8")
        self.assertIn("NativePreparation();", result)
        self.assertIn("NewCall();", result)
        self.assertNotIn("OldCall();", result)
        self.assertEqual(
            len(ET.fromstring(localization.read_text(encoding="utf-8"))), 2
        )

    def test_battle_helper_conflict_preserves_adaptive_projection(self):
        root = Path(self.temp.name)
        helper = root / "src/MaaCore/Task/BattleHelper.cpp"
        helper.parent.mkdir(parents=True)
        helper.write_text(
            "before\n"
            "<<<<<<< HEAD\n"
            "        cv::Vec3d temp { point.x + (has_multi_stages ? m_map_data.view[0].x : 0), -point.y, Map::TileCalc2::rel_pos_z };\n"
            "        auto screen_pt = Config.get_options().native_resolution\n"
            "                             ? adaptive::project_battle(m_map_data, temp, true, cam_img.cols, cam_img.rows)\n"
            "                             : Map::TileCalc2::world_to_screen(m_map_data, temp, true);\n"
            "=======\n"
            "        cv::Vec3d temp { point.x + (has_multi_phases ? m_map_data.view[0].x : 0), -point.y, Map::TileCalc2::rel_pos_z };\n"
            "        auto screen_pt = Map::TileCalc2::world_to_screen(m_map_data, temp, true);\n"
            ">>>>>>> upstream/dev-v2\n"
            "after\n",
            encoding="utf-8",
        )
        with patch.object(resolver, "REPO_ROOT", root):
            resolver.resolve_battle_helper()
        result = helper.read_text(encoding="utf-8")
        self.assertIn("has_multi_phases", result)
        self.assertIn("adaptive::project_battle", result)
        self.assertNotIn("has_multi_stages", result)
        self.assertNotIn("<<<<<<<", result)

    def previous_resources_fixture(
        self, entry="resource/version.json", bad_digest=False
    ):
        archive = Path("previous.zip")
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(entry, '{"version":"previous"}')
            package.writestr("MAA.exe", "not a resource")
        asset = self.release["assets"][0]
        asset["digest"] = "sha256:" + (
            "bad" if bad_digest else hashlib.sha256(archive.read_bytes()).hexdigest()
        )
        auto.PLAN.parent.mkdir()
        auto.PLAN.write_text(
            json.dumps({"previous_release": self.release}), encoding="utf-8"
        )

        def download(*args):
            self.assertEqual(args[:3], ("gh", "release", "download"))
            (Path(args[-1]) / asset["name"]).write_bytes(archive.read_bytes())
            return ""

        with patch.object(auto, "command", side_effect=download):
            auto.previous_resources()

    def test_previous_resources_are_verified_and_extracted_without_program_files(self):
        self.previous_resources_fixture()
        root = Path("build-native/previous-client")
        self.assertEqual(
            json.loads((root / "resource/version.json").read_text()),
            {"version": "previous"},
        )
        self.assertFalse((root / "MAA.exe").exists())

    def test_previous_resources_reject_bad_digest(self):
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            self.previous_resources_fixture(bad_digest=True)
        self.assertFalse(Path("build-native/previous-client").exists())

    def test_previous_resources_reject_archive_path_traversal(self):
        with self.assertRaisesRegex(RuntimeError, "Unsafe archive path"):
            self.previous_resources_fixture(entry="resource/../../escape.json")
        self.assertFalse(Path("build-native/escape.json").exists())

    def test_successful_resolver_exit_does_not_hide_unresolved_conflicts(self):
        self.seed()
        guide = Path("src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml")
        guide.write_text('<UserControl Content="native" />\n', encoding="utf-8")
        self.git("commit", "-am", "native guide")
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "upstream/dev-v2")
        guide.write_text('<UserControl Content="upstream" />\n', encoding="utf-8")
        self.git("commit", "-am", "upstream guide")
        target = self.git("rev-parse", "HEAD")
        self.git("checkout", "native")
        script = Path(".github/scripts/resolve-update-conflicts.py")
        script.parent.mkdir(parents=True)
        script.write_text(
            "# Deliberately leave the conflict untouched.\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(RuntimeError, "git merge"):
            auto.merge_upstream(head, target)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertIn(
            str(guide).replace("\\", "/"),
            self.git("diff", "--name-only", "--diff-filter=U"),
        )
        self.assertTrue(Path("build-native/merge-conflict.json").exists())

    def test_upstream_update_resolves_and_stages_known_gui_conflicts(self):
        self.seed()
        dialog = Path(
            "src/MaaWpfGui/ViewModels/Dialogs/VersionUpdateDialogViewModel.cs"
        )
        settings = Path(
            "src/MaaWpfGui/ViewModels/UserControl/Settings/VersionUpdateSettingsUserControlModel.cs"
        )
        dialog.write_text("native dialog\n")
        settings.write_text(
            "class Settings {\n    native update\n"
            "    public async Task ManualUpdateResource()\n    {\n        await ResourceUpdater.ResourceUpdateAndReloadAsync();\n    }\n\n    // UI \n}\n"
        )
        self.git("add", ".")
        self.git("commit", "-m", "native update UI")
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "upstream/dev-v2")
        dialog.write_text("upstream dialog\n")
        settings.write_text(
            "class Settings {\n    upstream update\n"
            "    public async Task ManualUpdateResource()\n    {\n        await ResourceUpdater.ResourceUpdateAndReloadAsync();\n    }\n\n    // UI \n}\n"
        )
        self.git("add", ".")
        self.git("commit", "-m", "upstream update UI")
        target = self.git("rev-parse", "HEAD")
        self.git("checkout", "native")
        resolver_path = (
            Path(__file__).resolve().parents[2]
            / ".github/scripts/resolve-update-conflicts.py"
        )
        destination = Path(".github/scripts/resolve-update-conflicts.py")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            resolver_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        auto.merge_upstream(head, target)
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U"), "")
        self.assertIn("upstream update", settings.read_text())
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no"), "")
        self.assertNotEqual(self.git("rev-parse", "HEAD"), head)

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

    def test_missing_startup_update_check_blocks_release(self):
        self.seed()
        Path("src/MaaWpfGui/ViewModels/UI/RootViewModel.cs").write_text(
            "NativeCaptureService.EnsureStartedAsync(); DebugControlService.Start();"
        )
        self.git("commit", "-am", "removed startup update check")
        with self.assertRaisesRegex(RuntimeError, "Automatic startup update check"):
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
