"""Build public Windows x64 releases from clean runtime inputs, never user data."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


def archive_tree(source, destination, exclude=()):
    with zipfile.ZipFile(
        destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.relative_to(source).as_posix() not in exclude:
                archive.write(path, path.relative_to(source).as_posix())
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    Path(str(destination) + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="ascii"
    )
    return digest


def build(args):
    if not re.fullmatch(r"v\d+\.\d+\.\d+-native\.\d+", args.version):
        raise ValueError("Expected vX.Y.Z-native.N")
    source = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    program = out / ("program-" + args.version)
    portable = out / ("portable-" + args.version)
    # Refuse reuse instead of removing a directory computed from an argument.
    program.mkdir()
    portable.mkdir()
    shutil.copytree(
        args.gui,
        program,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "*.pdb", "*.tmp", "cache", "debug", "config", "resource", "__pycache__"
        ),
    )
    for path in args.core.glob("*.dll"):
        shutil.copy2(path, program / path.name)
    for name in ["MaaAdbControlUnit.dll", "MaaWin32ControlUnit.dll", "MAA.Updater.exe"]:
        shutil.copy2(args.runtime / name, program / name)
    shutil.copy2(source / "LICENSE", program / "LICENSE")
    (program / "changes.json").write_text(json.dumps({"deleted": []}), encoding="utf-8")
    for name in [
        "MAA.exe",
        "MAA.dll",
        "MAA.deps.json",
        "MAA.runtimeconfig.json",
        "MaaCore.dll",
        "MAA.Updater.exe",
    ]:
        assert (program / name).is_file(), name
    runtime_config = json.loads(
        (program / "MAA.runtimeconfig.json").read_text(encoding="utf-8-sig")
    )
    assert "includedFrameworks" in runtime_config["runtimeOptions"], (
        "A self-contained GUI is required"
    )
    shutil.copytree(
        program,
        portable,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("changes.json"),
    )
    shutil.copytree(
        args.resources,
        portable / "resource",
        ignore=shutil.ignore_patterns("*.bak", "*.tmp", ".git"),
    )
    shutil.copytree(
        args.adb, portable / "platform-tools", ignore=shutil.ignore_patterns("adbkey*")
    )
    task_types = [
        "StartUpTask",
        "FightTask",
        "InfrastTask",
        "RecruitTask",
        "MallTask",
        "AwardTask",
        "RoguelikeTask",
        "UserDataUpdateTask",
    ]
    config = {
        "ConfigVersion": 1,
        "Current": "Default",
        "Configurations": {
            "Default": {
                "TaskQueue": [
                    {"$type": name, "IsEnable": False} for name in task_types
                ],
                "Gui": {
                    "ConnectSettings": {
                        "Config": "Compatible",
                        "AdbPath": "platform-tools/adb.exe",
                        "Address": "",
                        "AddressHistory": [],
                        "AutoDetect": False,
                        "AlwaysAutoDetect": False,
                    },
                    "StartUpSettings": {
                        "RunDirectly": False,
                        "StartEmulator": False,
                        "StartPcClient": False,
                    },
                },
            }
        },
        "Update": {
            "UpdateSource": "GitHub",
            "AutoInstallUpdatePackage": False,
            "UpdatePackage": "",
        },
    }
    (portable / "config").mkdir()
    (portable / "config/gui.new.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (portable / "config/gui.json").write_text(
        '{"Configurations":{"Default":{}},"Current":"Default","Global":{}}',
        encoding="utf-8",
    )
    debug_client = source / "tools/native-release/maa_debug.py"
    if debug_client.exists():
        (portable / "optimization").mkdir()
        shutil.copy2(debug_client, portable / "optimization/maa_debug.py")
    (portable / "使用说明.md").write_text(
        f"""# MAA Native {args.version}

完整解压后打开 MAA.exe，首次使用选择手机连接并允许 USB 调试。
ADB 路径为 platform-tools/adb.exe；无线连接填手机的无线 ADB 地址，有线连接填设备序列号。
保持手机原生分辨率，明日方舟的异形屏 UI 适配设为 0。
程序更新来自 https://github.com/kevin07429/MAA-Native/releases ，资源更新来自官方 MaaResource。
设置页可分别检查程序更新、更新游戏资源。程序更新会校验 SHA256，并在空闲后提示重启。
暂停保留当前任务，恢复时重新截图识别；停止会结束任务。暂停 MAA 不会暂停游戏。
首次使用游戏内容时，请先关闭游戏自己的首次介绍窗口。
本包为 Windows x64 自包含程序，不需要安装 Python 或 .NET。后台调试客户端可选使用 Python。
不包含作者的手机连接、账号、任务设置、缓存或日志。基于官方 MAA 修改，非官方发行版，许可证见 LICENSE。
""",
        encoding="utf-8",
    )
    manifest = {
        p.relative_to(portable).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(portable.rglob("*"))
        if p.is_file()
    }
    (portable / "文件校验-SHA256.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    artifacts = {}
    for path, name in [
        (program, f"MAA-Native-{args.version}-program-win-x64.zip"),
        (portable, f"MAA-{args.version}-win-x64.zip"),
    ]:
        # Existing native installations already contain these user-selectable assets.
        # Preserve their wallpaper folder during program updates; fresh installs get the complete set.
        excluded = (
            tuple(
                p.relative_to(program).as_posix()
                for p in program.rglob("*")
                if p.is_file()
                and p.relative_to(program)
                .as_posix()
                .startswith("Res/Backgrounds/Wallpapers/")
            )
            if path == program
            else ()
        )
        artifacts[name] = archive_tree(path, out / name, exclude=excluded)
    manifest = {
        "version": args.version,
        "repository": "kevin07429/MAA-Native",
        "artifacts": artifacts,
        "resource_source": "MaaAssistantArknights/MaaResource",
        "program_update_preserves": [
            "config",
            "data",
            "cache",
            "debug",
            "resource",
            "Res/Backgrounds/Wallpapers",
        ],
    }
    (out / "native-release.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["gui", "core", "runtime", "resources", "adb", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--version", required=True)
    build(parser.parse_args())
