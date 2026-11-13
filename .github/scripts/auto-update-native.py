"""Detect upstream/app changes, validate a local merge, then publish from GitHub."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET

REPO = "kevin07429/MAA-Native"
UPSTREAM = "MaaAssistantArknights/MaaAssistantArknights"
PLAN = Path(".git/native-auto-update.json")
VERSION_FILE = Path("src/MaaCore/CMakeLists.txt")
PATTERN = r"^v(\d+\.\d+\.\d+)-native\.(\d+)$"


def command(*args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        details = (
            (result.stdout + b"\n" + result.stderr)
            .decode("utf-8", errors="replace")
            .strip()
        )
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{details}"
        )
    return result.stdout.decode("utf-8").strip()


def api(path):
    return json.loads(command("gh", "api", path))


def app_file(name):
    return name.startswith(
        ("src/", "include/", "resource/", "cmake/", "tools/wireless-native/")
    ) or name in (
        "CMakeLists.txt",
        "CMakePresets.json",
        "tools/native-release/package_native.py",
        ".github/scripts/build-native.ps1",
    )


def inspect(check_only=False):
    release = api(f"repos/{REPO}/releases/latest")
    comparison = api(f"repos/{REPO}/compare/MaaAssistantArknights:dev-v2...native")
    own = api(f"repos/{REPO}/compare/{release['tag_name']}...native")
    changed = comparison["behind_by"] > 0 or any(
        app_file(f["filename"]) for f in own.get("files", [])
    )
    full = f"MAA-{release['tag_name']}-win-x64.zip"
    complete = any(
        a["name"] == full and a["state"] == "uploaded" for a in release["assets"]
    )
    summary = f"Upstream commits pending: {comparison['behind_by']}. App changes: {changed}. Latest release complete: {complete}. Check only: {check_only}.\n"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(
                f"changed={str(changed and complete and not check_only).lower()}\n"
            )
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(summary)
    print(summary)


def merge_upstream(head, target):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(f"merge_key=native-merge-v1-{head}-{target}\n")
    try:
        command("git", "merge", "--no-commit", "--no-ff", target)
    except RuntimeError:
        conflicts = command(
            "git", "diff", "--name-only", "--diff-filter=U"
        ).splitlines()
        resolvable = {
            "src/MaaCore/Task/BattleHelper.cpp",
            "src/MaaWpfGui/Models/ResourceUpdater.cs",
            "src/MaaWpfGui/ViewModels/Dialogs/VersionUpdateDialogViewModel.cs",
            "src/MaaWpfGui/ViewModels/UserControl/Settings/VersionUpdateSettingsUserControlModel.cs",
            "src/MaaWpfGui/Views/UserControl/Settings/VersionUpdateSettingsUserControl.xaml",
            "src/MaaWpfGui/Views/UserControl/GuideUserControl.xaml",
        }
        if conflicts and all(
            name in resolvable or name.startswith("src/MaaWpfGui/Res/Localizations/")
            for name in conflicts
        ):
            try:
                command("python", ".github/scripts/resolve-update-conflicts.py")
                # A zero exit status alone must never mark leftover conflicts resolved.
                for name in conflicts:
                    text = Path(name).read_text(encoding="utf-8-sig")
                    if re.search(
                        r"^(?:<{7}|={7}|>{7}|\|{7})(?:\s|$)", text, re.MULTILINE
                    ):
                        raise RuntimeError("Unresolved conflict markers in " + name)
                    if name.endswith(".xaml"):
                        try:
                            ET.fromstring(text)
                        except ET.ParseError as error:
                            raise RuntimeError(
                                f"Invalid resolved XAML in {name}: {error}"
                            ) from error
                command("git", "add", "--", *conflicts)
                remaining = command(
                    "git", "diff", "--name-only", "--diff-filter=U"
                ).splitlines()
                if not remaining:
                    command("git", "commit", "-m", "Merge upstream update UI changes")
                    return
                conflicts = remaining
            except RuntimeError as exception:
                print(f"Known conflict resolution failed: {exception}", flush=True)
                conflicts = command(
                    "git", "diff", "--name-only", "--diff-filter=U"
                ).splitlines()
        if conflicts:
            report = Path("build-native/merge-conflict.json")
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps(
                    {"head": head, "upstream": target, "files": conflicts}, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
            summary = (
                "Upstream merge blocked by conflicts; no build or publication started.\n\n"
                + "\n".join("- `" + name + "`" for name in conflicts)
                + "\n"
            )
            print(summary, flush=True)
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(
                    os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8"
                ) as out:
                    out.write(summary)
        raise


def prepare():
    if command("git", "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("A clean tracked checkout is required")
    head = command("git", "rev-parse", "HEAD")
    target = command("git", "rev-parse", "upstream/dev-v2")
    release = api(f"repos/{REPO}/releases/latest")
    previous = re.fullmatch(PATTERN, release["tag_name"])
    if not previous:
        raise RuntimeError("Unexpected previous native release tag")
    merge_upstream(head, target)
    required = {
        "src/MaaWpfGui/Services/NativeUpdateService.cs": REPO,
        "src/MaaWpfGui/Services/DebugControlService.cs": "debug-control.json",
        "src/MaaWpfGui/ViewModels/UI/RootViewModel.cs": "NativeCaptureService.EnsureStartedAsync",
        "src/MaaWpfGui/ViewModels/Dialogs/VersionUpdateDialogViewModel.cs": "return NativeUpdateService.CheckAndDownloadAsync",
    }
    for name, marker in required.items():
        if marker not in Path(name).read_text(encoding="utf-8-sig"):
            raise RuntimeError("A native integration invariant was lost: " + name)
    if "DebugControlService.Start()" not in Path(
        "src/MaaWpfGui/ViewModels/UI/RootViewModel.cs"
    ).read_text(encoding="utf-8-sig"):
        raise RuntimeError("Background debug control was disabled")
    if "_ = StartupIntegrityCheckAndUpdateAsync();" not in Path(
        "src/MaaWpfGui/ViewModels/UI/RootViewModel.cs"
    ).read_text(encoding="utf-8-sig"):
        raise RuntimeError("Automatic startup update check was disabled")
    about = Path(
        "src/MaaWpfGui/Views/UserControl/Settings/AboutUserControl.xaml"
    ).read_text(encoding="utf-8-sig")
    if "Hyperlink" in about or "CheckAndDownloadAnnouncement" in about:
        raise RuntimeError("Upstream contact or announcement UI was restored")
    current = re.search(
        r'set\(NATIVE_APP_VERSION "(v[^"]+)"', VERSION_FILE.read_text(encoding="utf-8")
    )
    current = re.fullmatch(PATTERN, current[1])
    stable = api(f"repos/{UPSTREAM}/releases/latest")["tag_name"]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", stable):
        raise RuntimeError("Unexpected official stable version")
    base = max(
        [previous[1], current[1], stable[1:]],
        key=lambda v: tuple(map(int, v.split("."))),
    )
    number = (
        int(current[2]) if int(current[2]) > int(previous[2]) else int(previous[2]) + 1
    )
    version = f"v{base}-native.{number}"
    text = VERSION_FILE.read_text(encoding="utf-8")
    text, count = re.subn(
        r'set\(NATIVE_APP_VERSION "v[^"]+"', f'set(NATIVE_APP_VERSION "{version}"', text
    )
    if count != 1:
        raise RuntimeError("Could not set the native version")
    VERSION_FILE.write_text(text, encoding="utf-8")
    state_path = Path(".github/native-resource-sync.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        upstream_commit=target,
        resource_version=json.loads(
            Path("resource/version.json").read_text(encoding="utf-8-sig")
        ),
        program_commits_not_merged=[],
        automatic_full_update=True,
    )
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    changes = command("git", "log", "--format=%h %s", head + ".." + target)
    report = f"# MAA Native {version}\n\n自动同步官方 dev-v2 `{target}`，保留手机适配、快速截图、后台控制与暂停/恢复。\n\n## 本次官方提交\n\n{changes or '本仓库程序更新。'}\n\n完整包用于新安装；程序更新包由内置更新器使用，保留配置、数据、资源和壁纸。资源继续同步官方 MaaResource。\n\nAGPL-3.0，非官方发行版。\n"
    Path("RESOURCE_UPDATES.md").write_text(report, encoding="utf-8")
    command("git", "add", "-u")
    if (
        command("git", "diff", "--cached", "--name-only")
        or Path(".git/MERGE_HEAD").exists()
    ):
        command(
            "git",
            "commit",
            "-m",
            f"chore: automatically synchronize and prepare {version}",
        )
    PLAN.write_text(
        json.dumps(
            {
                "head": head,
                "validated_commit": command("git", "rev-parse", "HEAD"),
                "version": version,
                "previous_release": release,
            }
        ),
        encoding="utf-8",
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("version=" + version + "\n")


def previous_resources():
    release = json.loads(PLAN.read_text(encoding="utf-8"))["previous_release"]
    name = f"MAA-{release['tag_name']}-win-x64.zip"
    asset = next(a for a in release["assets"] if a["name"] == name)
    folder = Path("build-native/previous-archive")
    folder.mkdir(parents=True)
    command(
        "gh",
        "release",
        "download",
        release["tag_name"],
        "--repo",
        REPO,
        "--pattern",
        name,
        "--dir",
        str(folder),
    )
    package = folder / name
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    if asset.get("digest") != "sha256:" + digest:
        raise RuntimeError("Previous package digest mismatch")
    destination = Path("build-native/previous-client").resolve()
    destination.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        for entry in archive.infolist():
            if entry.filename.startswith("resource/"):
                if (
                    not (destination / entry.filename)
                    .resolve()
                    .is_relative_to(destination)
                ):
                    raise RuntimeError("Unsafe archive path")
                archive.extract(entry, destination)


def publish():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if command("git", "rev-parse", "HEAD") != plan["validated_commit"] or command(
        "git", "status", "--porcelain", "--untracked-files=no"
    ):
        raise RuntimeError("Validated tracked source changed during the build")
    for attempt in range(3):
        pushed = subprocess.run(
            ["git", "push", "origin", "HEAD:native"], capture_output=True
        )
        if pushed.returncode == 0:
            break
        failure = pushed.stderr.decode("utf-8", errors="replace")
        print("Source push failed:", failure, flush=True)
        if (
            "workflow" in failure.lower()
            or "403" in failure
            or "permission" in failure.lower()
        ):
            raise RuntimeError(
                "Source push authorization failed; NATIVE_UPDATE_TOKEN requires repo and workflow access"
            )
        command(
            "git", "fetch", "--no-tags", "origin", "native:refs/remotes/origin/native"
        )
        remote = command("git", "rev-parse", "origin/native")
        command("git", "merge-base", "--is-ancestor", plan["head"], remote)
        paths = command("git", "diff", "--name-only", plan["head"], remote).splitlines()
        if any(p != "README.md" and not p.startswith("docs/") for p in paths):
            raise RuntimeError(
                "Concurrent code/resource changes require another validation; no force push"
            )
        command(
            "git",
            "merge",
            "--no-edit",
            "-m",
            "Preserve concurrent documentation",
            remote,
        )
    else:
        raise RuntimeError("Could not publish the validated source: " + failure)
    version = plan["version"]
    existing = subprocess.run(
        ["gh", "release", "view", version, "--repo", REPO, "--json", "isDraft"],
        capture_output=True,
    )
    target = command("git", "rev-parse", "HEAD")
    if existing.returncode == 0:
        if not json.loads(existing.stdout)["isDraft"]:
            raise RuntimeError(
                "This version is already public; refusing to replace its files"
            )
        command(
            "gh",
            "release",
            "edit",
            version,
            "--repo",
            REPO,
            "--target",
            target,
            "--notes-file",
            "RESOURCE_UPDATES.md",
        )
    else:
        command(
            "gh",
            "release",
            "create",
            version,
            "--repo",
            REPO,
            "--target",
            target,
            "--title",
            "MAA Native " + version,
            "--notes-file",
            "RESOURCE_UPDATES.md",
            "--draft",
        )
    assets = Path("build-native/assets")
    metadata = json.loads((assets / "native-release.json").read_text(encoding="utf-8"))
    if metadata["version"] != version or len(metadata["artifacts"]) != 2:
        raise RuntimeError("Unexpected release artifact manifest")
    expected = ["native-release.json"]
    for name, digest in metadata["artifacts"].items():
        if (
            Path(name).name != name
            or hashlib.sha256((assets / name).read_bytes()).hexdigest() != digest
        ):
            raise RuntimeError("Local package digest mismatch: " + name)
        expected.extend([name, name + ".sha256"])
    for name in expected:
        command(
            "gh",
            "release",
            "upload",
            version,
            str(assets / name),
            "--repo",
            REPO,
            "--clobber",
        )
    uploaded = json.loads(
        command("gh", "release", "view", version, "--repo", REPO, "--json", "assets")
    )
    for name in expected:
        item = next(a for a in uploaded["assets"] if a["name"] == name)
        if item["state"] != "uploaded":
            raise RuntimeError("Asset upload incomplete: " + name)
    for name, digest in metadata["artifacts"].items():
        item = next(a for a in uploaded["assets"] if a["name"] == name)
        if item["state"] != "uploaded" or item.get("digest") != "sha256:" + digest:
            raise RuntimeError("Uploaded asset verification failed: " + name)
    command(
        "gh",
        "release",
        "edit",
        version,
        "--repo",
        REPO,
        "--draft=false",
        "--prerelease=false",
        "--latest",
    )
    print("Published", version)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=["inspect", "prepare", "previous-resources", "publish"]
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.phase == "inspect":
        inspect(args.check_only)
    elif args.phase == "prepare":
        prepare()
    elif args.phase == "previous-resources":
        previous_resources()
    else:
        publish()
