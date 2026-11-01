"""Git integration checks for automatic resource-only synchronization."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "sync_resources", Path(__file__).with_name("sync_resources.py")
)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class ResourceSyncTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.root = Path(tempfile.mkdtemp(prefix="maa-resource-sync-test-")).resolve()
        os.chdir(self.root)
        self.git("init", "-b", "native")
        self.git("config", "user.name", "Resource Sync Test")
        self.git("config", "user.email", "test@example.invalid")
        self.write("resource/version.json", '{"last_updated":"2026-10-30"}')
        self.write("resource/task.json", '{"value":"base"}')
        self.write("src/core.txt", "base")
        self.save("base")
        self.git("branch", "official")

    def tearDown(self):
        # Keep the tiny fixture for inspection; never delete a computed directory.
        os.chdir(self.previous)

    def git(self, *args):
        return (
            subprocess.check_output(["git", *args], stderr=subprocess.STDOUT)
            .decode()
            .strip()
        )

    def write(self, name, content):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def save(self, title):
        self.git("add", ".")
        self.git("commit", "-m", title)

    def update_official(self):
        self.git("checkout", "official")
        self.write("resource/task.json", '{"value":"updated"}')
        self.write("resource/new.json", '{"new":true}')
        self.write("src/core.txt", "unreviewed program change")
        self.write(".github/workflows/unreviewed.yml", "must not be imported")
        self.save("upstream resource and program update")
        self.git("checkout", "native")

    def test_only_resources_commit_and_second_sync_is_noop(self):
        self.update_official()
        changed, report = sync.prepare("official")
        self.assertTrue(changed)
        self.assertIn("Program changes pending review", report)
        self.assertIn("upstream resource and program update", report)
        self.assertEqual(Path("src/core.txt").read_text(), "base")
        self.assertFalse(Path(".github/workflows/unreviewed.yml").exists())
        sync.commit()
        self.assertEqual(
            json.loads(Path("resource/task.json").read_text())["value"], "updated"
        )
        self.assertFalse(sync.prepare("official")[0])

    def test_conflict_is_not_committed(self):
        self.update_official()
        self.write("resource/task.json", '{"value":"native custom"}')
        self.save("custom resource")
        head = self.git("rev-parse", "HEAD")
        with self.assertRaises(subprocess.CalledProcessError):
            sync.prepare("official")
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertTrue(self.git("ls-files", "--unmerged"))

    def test_malformed_json_is_not_committed(self):
        self.git("checkout", "official")
        self.write("resource/task.json", "broken json")
        self.save("malformed resource")
        self.git("checkout", "native")
        head = self.git("rev-parse", "HEAD")
        with self.assertRaises(json.JSONDecodeError):
            sync.prepare("official")
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_staged_source_injection_blocks_commit(self):
        self.update_official()
        sync.prepare("official")
        self.write("src/core.txt", "unexpected build modification")
        self.git("add", "src/core.txt")
        with self.assertRaises(RuntimeError):
            sync.commit()

    def test_next_resource_update_does_not_reapply_old_patch(self):
        self.update_official()
        sync.prepare("official")
        sync.commit()
        self.git("checkout", "official")
        self.write("resource/task.json", '{"value":"next update"}')
        self.save("second resource update")
        self.git("checkout", "native")
        self.assertTrue(sync.prepare("official")[0])
        sync.commit()
        self.assertEqual(
            json.loads(Path("resource/task.json").read_text())["value"], "next update"
        )

    def test_program_notice_survives_resource_cursor_and_noop(self):
        self.update_official()
        sync.prepare("official")
        sync.commit()
        changed, summary = sync.prepare("official")
        self.assertFalse(changed)
        self.assertIn("upstream resource and program update", summary)
        self.git("checkout", "official")
        self.write("resource/new.json", '{"new":false}')
        self.save("resource only")
        self.git("checkout", "native")
        sync.prepare("official")
        state = json.loads(Path(sync.STATE).read_text(encoding="utf-8"))
        self.assertEqual(len(state["program_commits_not_merged"]), 1)

    def test_pure_resource_interval_retains_upstream_history(self):
        self.git("checkout", "official")
        self.write("resource/new.json", '{"pure_resource":true}')
        self.save("resource only")
        target = self.git("rev-parse", "HEAD")
        self.git("checkout", "native")
        self.write("src/native.txt", "keep native feature")
        self.save("native feature")
        self.assertTrue(sync.prepare("official")[0])
        sync.commit()
        self.git("merge-base", "--is-ancestor", target, "HEAD")
        self.assertEqual(Path("src/native.txt").read_text(), "keep native feature")


if __name__ == "__main__":
    unittest.main()
