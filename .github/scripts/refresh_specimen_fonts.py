#!/usr/bin/env python3
"""Refresh the Slack specimen from committed hinted static builds and cache keys."""

import hashlib
from pathlib import Path
import re


WEIGHTS = (
    "Hairline", "Thin", "Light", "Regular", "Medium",
    "Semibold", "Bold", "Heavy", "Black",
)


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

    faces = []
    for orientation, suffix in (("Upr", ""), ("Ita", "Italic")):
        for weight, name in enumerate(WEIGHTS, 1):
            label = "Italic" if suffix and name == "Regular" else name + suffix
            source = root / f"build/Lato3{orientation}2M/ds-ufo/masters/Lato26-{label}.ttf"
            target = f"lato26-{label.lower()}.ttf"
            data = source.read_bytes()
            if not data:
                raise ValueError(f"Empty static font: {source}")
            fonts[target] = data
            version = hashlib.sha256(data).hexdigest()[:12]
            style = ";font-style:italic" if suffix else ""
            faces.append(
                "@font-face{font-family:Lato26;"
                f"src:url('assets/{target}?v={version}') format('truetype');"
                f"font-weight:{weight * 100}{style};font-display:swap}}"
            )
    css = replace_once(
        r"(?:@font-face\{font-family:Lato26;[^}]*\}\s*)+",
        "\n".join(faces) + "\n",
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
    (specimen / "assets/lato26.ttf").unlink(missing_ok=True)
    css_path.write_bytes(css_bytes)
    html_path.write_bytes(html.encode("utf-8"))


if __name__ == "__main__":
    refresh(Path(__file__).resolve().parents[2])
