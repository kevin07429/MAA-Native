"""Resolve the native fork's known update UI conflicts while preserving upstream changes."""

from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path("src/MaaWpfGui")
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
    text, count = re.subn(
        r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)",
        lambda match: chooser(match[1], match[2]),
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    validate(path, text)
    if count:
        path.write_text(text, encoding="utf-8")


def main():
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
