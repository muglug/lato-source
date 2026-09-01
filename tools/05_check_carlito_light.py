#!/usr/bin/env python3
"""Check Carlito Light / Light Italic for metric compatibility with Calibri Light.

  * every shared codepoint has the same advance width
  * text shaped with HarfBuzz (kerning + ligatures on, and off) is the same
    width as in Calibri Light, for a corpus of Latin/Cyrillic/Greek strings
  * kerning pairs agree with Calibri Light's
  * vertical metrics agree
  * vertical and diagonal strokes are within STEM_TOLERANCE of Calibri Light's
    on average; round and horizontal strokes, and the ink coverage of text
    runs (what the build calibrates the source weight on), are reported
  * FreeType can load and rasterise every glyph

Exit status 1 if any hard check fails.
"""
import importlib.util
import os
import sys
from itertools import product

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from PIL import ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "build", "Carlito")
WORD = "/Applications/Microsoft Word.app/Contents/Resources/DFonts"
PAIRS = [
    ("Carlito-Light.ttf", os.path.join(WORD, "calibril.ttf")),
    ("Carlito-LightItalic.ttf", os.path.join(WORD, "calibrili.ttf")),
]
STEM_TOLERANCE = 0.05  # relative, on the vertical stem probes

_spec = importlib.util.spec_from_file_location("build_carlito", os.path.join(HERE, "04_build_carlito_light.py"))
build_carlito = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_carlito)

CORPUS = [
    "The quick brown fox jumps over the lazy dog. THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG!",
    "Sphinx of black quartz, judge my vow. 0123456789 ($1,234.56) 50% #42 @home & Co.",
    "AVATAR Type Wave Ty To Yo LT Wa r. f) 7. 11 “Quoted” ‘single’ — dash – en… ¿Qué? ¡Sí!",
    "fi fl ff ffi ffl fj fb fh fk ft office waffle fjord shelf fifty-five",
    "Ŵŷ Ąę ĞğĪī Łł Őő Şş Ţţ Žž Ćć Đđ Ńń Ŕŕ Ůů Źź Æ æ Ø ø Å å Ç ç Ñ ñ Ü ü ß",
    "Съешь же ещё этих мягких французских булок, да выпей чаю. ЁЙЪЭЮЯ Ђђ Љљ Њњ Ћћ Џџ Ґґ Єє Іі Її",
    "Ξεσκεπάζω τὴν ψυχοφθόρα βδελυγμία. ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ αβγδεζηθικλμνξοπρστυφχψω άέήίόύώ ΆΈΉΊΌΎΏ",
    "Vietnamese: Tiếng Việt có dấu — Ắ ằ Ẳ ẵ Ặ ệ Ỉ ộ Ợ ữ Ỷ. Turkish: İstanbul'da ışıklı gece. Polish: Zażółć gęślą jaźń.",
    "½ ¼ ¾ ² ³ ¹ ™ © ® § ¶ † ‡ • · ° ± × ÷ ≠ ≈ ≤ ≥ ∞ µ € £ ¥ ¢ ← ↑ → ↓",
]
KERN_SAMPLE = list("AVWTYLFPKXvwyrfkbcdeghmnopqstuz.,;:'\"-()[]/") + ["quoteright", "quotedblleft"]
INK_RUNS = [
    ("prose", build_carlito.INK_CORPUS),
    ("caps", "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG. SPHINX OF BLACK QUARTZ, JUDGE MY VOW. PACK MY BOX WITH FIVE DOZEN LIQUOR JUGS."),
    ("figures", "0123456789 1,234,567.89 (0.5%) 2024-03-14 12:45:00 +1 (555) 010-9876"),
    ("cyrillic", CORPUS[5]),
    ("greek", CORPUS[6]),
]


def shape(font, text, features):
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, features)
    return sum(p.x_advance for p in buf.glyph_positions), buf


def hb_font(path):
    return hb.Font(hb.Face(hb.Blob.from_file_path(path)))


STRAIGHT_PROBES = {cls: build_carlito.STEM_PROBES[cls] + build_carlito.DIAGONAL_PROBES[cls] for cls in ("lc", "caps")}
ROUND_PROBES = {"lc": (("o", 0.5, 0),), "caps": (("O", 0.5, 0),)}


def stroke_widths(font):
    """Per-mille stroke thicknesses: the build's vertical and diagonal probes,
    the left side of o/O, and horizontal strokes of H (bar) and o (bottom)."""
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    scale = 1000 / upm

    def flat(ch):
        pen = build_carlito.FlattenPen(gs)
        gs[cmap[ord(ch)]].draw(pen)
        return pen.segments

    def top(ch):
        bp = BoundsPen(gs)
        gs[cmap[ord(ch)]].draw(bp)
        return bp.bounds[3]

    def xcross(segs, y):
        return sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in segs if (y0 <= y < y1) or (y1 <= y < y0))

    def ycross(segs, x):
        return sorted(y0 + (x - x0) * (y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in segs if (x0 <= x < x1) or (x1 <= x < x0))

    out = {}
    for probes in (STRAIGHT_PROBES, ROUND_PROBES):
        for cls, strokes in build_carlito.measure_strokes(font, probes).items():
            for (g, frac, i), v in strokes.items():
                out[g] = v * scale
    xh, ch = top("x"), top("H")
    segs = flat("H")
    xs = xcross(segs, ch * 0.25)
    ys = ycross(segs, (xs[1] + xs[2]) / 2)
    out["H-bar"] = (ys[1] - ys[0]) * scale
    segs = flat("o")
    xs = xcross(segs, xh * 0.5)
    ys = ycross(segs, (xs[0] + xs[-1]) / 2)
    out["o-bottom"] = (ys[1] - ys[0]) * scale
    return out


def check(name, cal_path):
    out_path = os.path.join(OUT, name)
    ok = True
    print(f"\n=== {name} vs {os.path.basename(cal_path)} ===")
    out, cal = TTFont(out_path), TTFont(cal_path)

    # --- advance widths -------------------------------------------------
    ocm, ccm = out.getBestCmap(), cal.getBestCmap()
    shared = sorted(set(ocm) & set(ccm))
    bad = [(cp, out["hmtx"][ocm[cp]][0], cal["hmtx"][ccm[cp]][0]) for cp in shared
           if out["hmtx"][ocm[cp]][0] != cal["hmtx"][ccm[cp]][0]]
    print(f"advance widths: {len(shared) - len(bad)}/{len(shared)} shared codepoints identical")
    for cp, a, b in bad[:20]:
        print(f"   U+{cp:04X} {ocm[cp]}: {a} vs Calibri {b}")
    ok &= not bad

    # --- shaped text ----------------------------------------------------
    of, cf = hb_font(out_path), hb_font(cal_path)
    for feats, label in (({}, "default features"), ({"kern": False, "liga": False, "calt": False}, "kern/liga off")):
        diffs = 0
        for text in CORPUS:
            a, _ = shape(of, text, feats)
            b, _ = shape(cf, text, feats)
            if a != b:
                diffs += 1
                print(f"   width mismatch ({label}): {a} vs {b}  {text[:50]!r}")
        print(f"shaped corpus ({label}): {len(CORPUS) - diffs}/{len(CORPUS)} strings identical width")
        ok &= diffs == 0

    # --- kerning pairs --------------------------------------------------
    chars = [c for c in KERN_SAMPLE if len(c) == 1]
    n = mism = kerned = 0
    for a, b in product(chars, chars):
        wa, _ = shape(of, a + b, {})
        wb, _ = shape(cf, a + b, {})
        ua, _ = shape(of, a + b, {"kern": False})
        n += 1
        if wa != ua:
            kerned += 1
        if wa != wb:
            mism += 1
            if mism <= 10:
                print(f"   kern mismatch {a}{b}: {wa} vs {wb}")
    print(f"kerning: {n} pairs checked, {kerned} kerned in Carlito Light, {mism} differ from Calibri Light")
    ok &= mism == 0

    # --- vertical metrics -----------------------------------------------
    rows = []
    for tbl, attrs in (("hhea", ("ascent", "descent", "lineGap")),
                       ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent", "usWinDescent",
                                 "ySubscriptYSize", "ySuperscriptYOffset", "yStrikeoutPosition", "usWeightClass")),
                       ("head", ("unitsPerEm",))):
        for a in attrs:
            va, vb = getattr(out[tbl], a), getattr(cal[tbl], a)
            rows.append((f"{tbl}.{a}", va, vb))
            ok &= va == vb
    print("vertical metrics: " + ", ".join(f"{k}={a}{'' if a == b else f' (Calibri {b})'}" for k, a, b in rows))
    o2 = out["OS/2"]
    print(f"x-height {o2.sxHeight} (Calibri {cal['OS/2'].sxHeight}), cap height {o2.sCapHeight} (Calibri {cal['OS/2'].sCapHeight}), "
          f"avg char width {o2.xAvgCharWidth} (Calibri {cal['OS/2'].xAvgCharWidth}), italic angle {out['post'].italicAngle}")

    # --- stroke weight --------------------------------------------------
    so, sc = stroke_widths(out), stroke_widths(cal)
    straight = [g for probes in STRAIGHT_PROBES.values() for g, _, _ in probes]
    ratios = {g: so[g] / sc[g] for g in so}
    mean = sum(ratios[g] for g in straight) / len(straight)
    print("strokes (per mille of em, Carlito Light / Calibri Light): "
          + ", ".join(f"{g} {so[g]:.1f}/{sc[g]:.1f}" for g in so))
    print(f"   straight strokes: {mean - 1:+.1%} of Calibri Light on average (tolerance {STEM_TOLERANCE:.0%}); "
          + ", ".join(f"{g} {ratios[g] - 1:+.0%}" for g in straight))
    ok &= abs(mean - 1) <= STEM_TOLERANCE

    # --- ink coverage of text runs ---------------------------------------
    # outline area per em of advance: the darkness of set text, all strokes
    # and the x-height included (informational; the build can target it)
    inks = [(label, build_carlito.ink_coverage(out, text), build_carlito.ink_coverage(cal, text)) for label, text in INK_RUNS]
    print("ink coverage of text runs (Carlito Light vs Calibri Light): "
          + ", ".join(f"{label} {a * 100:.2f}% ({a / b - 1:+.1%})" for label, a, b in inks))

    # --- names / tables -------------------------------------------------
    nm = out["name"]
    print("names: " + " | ".join(f"{i}={nm.getDebugName(i)}" for i in (1, 2, 4, 6, 16, 17)))
    print("tables:", " ".join(sorted(t for t in out.keys() if t != "GlyphOrder")), f"| glyphs={len(out.getGlyphOrder())}")
    gsub = out["GSUB"].table
    gpos = out["GPOS"].table
    print(f"GSUB features: {sorted({f.FeatureTag for f in gsub.FeatureList.FeatureRecord})}")
    print(f"GPOS features: {sorted({f.FeatureTag for f in gpos.FeatureList.FeatureRecord})}, scripts "
          f"{[s.ScriptTag for s in gpos.ScriptList.ScriptRecord]}")

    # --- FreeType smoke test -------------------------------------------
    ft = ImageFont.truetype(out_path, 48)
    for cp in shared[:: max(1, len(shared) // 400)]:
        ft.getbbox(chr(cp))
    gs = out.getGlyphSet()
    from fontTools.pens.boundsPen import BoundsPen
    empty = 0
    for g in out.getGlyphOrder():
        bp = BoundsPen(gs)
        gs[g].draw(bp)
        if bp.bounds is None:
            empty += 1
    print(f"FreeType loads the font; {len(out.getGlyphOrder()) - empty} glyphs with outlines, {empty} empty")

    # --- liga parity ----------------------------------------------------
    for text in ("fi", "fl", "ff", "ffi", "ffl", "ft", "fb", "fh", "fk", "fj", "fí", "ffj"):
        a, ba = shape(of, text, {})
        b, bb = shape(cf, text, {})
        la, lb = len(ba.glyph_infos), len(bb.glyph_infos)
        flag = "" if (a == b and la == lb) else "  <-- differs"
        print(f"   liga {text!r}: Carlito Light {la} glyph(s) width {a}; Calibri Light {lb} glyph(s) width {b}{flag}")
    return ok


if __name__ == "__main__":
    all_ok = True
    for name, cal in PAIRS:
        all_ok &= check(name, cal)
    print("\nRESULT:", "all hard checks passed" if all_ok else "FAILURES above")
    sys.exit(0 if all_ok else 1)
