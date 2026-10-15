#!/usr/bin/env python3
"""Refresh the Slack specimen from committed variable builds, including cache keys."""

import hashlib
from pathlib import Path
import re


FONT_FILES = {
    "Lato26-Variable.ttf": "lato26.ttf",
    "Lato26-VariableItalic.ttf": "lato26-italic.ttf",
}


def replace_once(pattern: str, replacement: str, text: str) -> str:
    result, count = re.subn(pattern, lambda _: replacement, text)
    if count != 1:
        raise ValueError(f"Expected exactly one reference matching {pattern!r}, got {count}")
    return result


def refresh(root: Path) -> None:
    specimen = root / "docs/slack"
    css_path = specimen / "style.css"
    html_path = specimen / "index.html"
    css = css_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    fonts = {}

    # Read and validate every reference before modifying any files.
    for source, target in FONT_FILES.items():
        data = (root / "build/Lato26-Variable" / source).read_bytes()
        if not data:
            raise ValueError(f"Empty variable font: {source}")
        fonts[target] = data
        version = hashlib.sha256(data).hexdigest()[:12]
        css = replace_once(
            r"assets/" + re.escape(target) + r"(?:\?v=[^'\"\s)]+)?",
            f"assets/{target}?v={version}",
            css,
        )

    css_bytes = css.encode("utf-8")
    css_version = hashlib.sha256(css_bytes).hexdigest()[:12]
    html = replace_once(
        r"style\.css(?:\?v=[^'\"\s>]+)?", f"style.css?v={css_version}", html
    )
    for target, data in fonts.items():
        (specimen / "assets" / target).write_bytes(data)
        print(f"Refreshed {target}: {hashlib.sha256(data).hexdigest()[:12]}")
    css_path.write_bytes(css_bytes)
    html_path.write_bytes(html.encode("utf-8"))


if __name__ == "__main__":
    refresh(Path(__file__).resolve().parents[2])
