"""Resolve the native fork's known update conflicts while preserving upstream changes."""

from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path("src/MaaWpfGui")
REPO_ROOT = Path(".")
CONFLICT_MARKER = r"^(?:<{7}|={7}|>{7}|\|{7})(?:\s|$)"


def validate(path, text):
    if re.search(CONFLICT_MARKER, text, re.MULTILINE):
        raise RuntimeError(f"Unresolved conflict markers in {path}")
    if path.suffix == ".xaml":
        try:
            ET.fromstring(text)
        except ET.ParseError as error:
            raise RuntimeError(f"Invalid resolved XAML in {path}: {error}") from error


def native_guide(native, upstream):
    # The native introduction deliberately replaces upstream contact/documentation UI.
    # Keep its complete conflict side, not a comment-delimited upstream suffix:
    # upstream may move the agreement and remove the ScrollViewer in the same hunk.
    if not all(key in native for key in ("About.NativeEditionInfo", "Guide.ViewLog")):
        raise RuntimeError(
            "Unrecognized guide conflict outside the native introduction"
        )
    return native


def resolve(relative, chooser):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8-sig")
    original = text
    text, count = re.subn(
        r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)",
        lambda match: chooser(match[1], match[2]),
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    validate(path, text)
    if text != original:
        path.write_text(text, encoding="utf-8")


def resolve_battle_helper():
    path = REPO_ROOT / "src/MaaCore/Task/BattleHelper.cpp"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    original = text
    conflict_pattern = r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)"
    native_pattern = re.compile(
        r"^        cv::Vec3d temp \{ point\.x \+ \(has_multi_stages \? m_map_data\.view\[0\]\.x : 0\), -point\.y, Map::TileCalc2::rel_pos_z \};\n"
        r"        auto screen_pt = Config\.get_options\(\)\.native_resolution\n"
        r"                             \? adaptive::project_battle\(m_map_data, temp, true, cam_img\.cols, cam_img\.rows\)\n"
        r"                             : Map::TileCalc2::world_to_screen\(m_map_data, temp, true\);\n$",
        re.MULTILINE,
    )
    upstream_pattern = re.compile(
        r"^        cv::Vec3d temp \{ point\.x \+ \(has_multi_phases \? m_map_data\.view\[0\]\.x : 0\), -point\.y, Map::TileCalc2::rel_pos_z \};\n"
        r"        auto screen_pt = Map::TileCalc2::world_to_screen\(m_map_data, temp, true\);\n$",
        re.MULTILINE,
    )

    def choose(native, upstream):
        if not native_pattern.fullmatch(native) or not upstream_pattern.fullmatch(
            upstream
        ):
            raise RuntimeError(
                "Unrecognized BattleHelper conflict outside the adaptive projection change"
            )
        return native.replace("has_multi_stages", "has_multi_phases")

    text, count = re.subn(
        conflict_pattern,
        lambda match: choose(match[1], match[2]),
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    text = re.sub(
        r"\b(layout|calc_result)\.has_multi_stages\b",
        r"\1.has_multi_phases",
        text,
    )
    validate(path, text)
    if text != original:
        path.write_text(text, encoding="utf-8")


def main():
    resolve_battle_helper()

    for path in (ROOT / "Res/Localizations").glob("*.xaml"):
        resolve(path.relative_to(ROOT), lambda native, upstream: upstream + native)

    resolve(
        Path("ViewModels/Dialogs/VersionUpdateDialogViewModel.cs"),
        lambda native, upstream: native,
    )
    resolve(
        Path("Views/UserControl/Settings/VersionUpdateSettingsUserControl.xaml"),
        lambda native, upstream: native,
    )
    resolve(
        Path("Views/UserControl/GuideUserControl.xaml"),
        native_guide,
    )

    resource_updater = ROOT / "Models/ResourceUpdater.cs"
    text = resource_updater.read_text(encoding="utf-8-sig")
    text, count = re.subn(
        r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)",
        lambda match: match[1][
            : match[1].index("            var (ret, uri, releaseNote)")
        ]
        + match[2],
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if count:
        resource_updater.write_text(text, encoding="utf-8")

    settings = (
        ROOT
        / "ViewModels/UserControl/Settings/VersionUpdateSettingsUserControlModel.cs"
    )
    text = settings.read_text(encoding="utf-8-sig")
    text, count = re.subn(
        r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)",
        lambda match: match[1]
        if "VersionUpdateAndAskToRestartAsync" in match[1]
        else match[2],
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if count:
        start = text.index("    public async Task ManualUpdateResource()")
        end = text.index("    // UI ", start)
        text = (
            text[:start]
            + "    public async Task ManualUpdateResource()\n    {\n        await ResourceUpdater.ResourceUpdateAndReloadAsync();\n    }\n\n"
            + text[end:]
        )
        settings.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
