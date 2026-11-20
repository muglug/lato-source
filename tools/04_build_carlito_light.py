#!/usr/bin/env python3
"""Build Carlito Light / Carlito Light Italic from Lato's interpolatable masters.

Carlito (https://github.com/googlefonts/carlito) is Lato reshaped to be
metric-compatible with Calibri. This script applies the same recipe -- measured
from Carlito Regular vs. Lato Regular vs. Calibri Regular -- to a light Lato,
using Calibri Light / Calibri Light Italic from the local Word install as the
metric reference:

  * Source weight: Lato is a two-master design and fontmake's interpolatable
    masters (Hairline, Black) are point-compatible, so any weight on the axis
    is a linear blend of the two. Lato Light (250/1000 on the design axis) is
    noticeably lighter than Calibri Light, Regular (540) much heavier; the
    blend is chosen so a run of English prose set in the *output* puts down
    as much ink as in Calibri Light (--target ink, the default; lands at
    about 361 upright / 364 italic, roughly wght 338-339), or so the output's
    vertical and diagonal strokes match Calibri Light's on average (--target
    strokes; about 346 / 351). Lato's horizontals and bowls are thinner than
    Calibri's, so the two disagree by ~15 design units: ink-matched text has
    stems ~6% heavier than Calibri's; stroke-matched text reads ~3% lighter.
    Either way a linear stroke model picks a starting point, then the built
    font is measured and the blend corrected. --weight D bypasses all this.
  * 2048 UPM (Calibri's). Uppercase letters, figures and currency are scaled
    uniformly by 1314/1432 (Carlito/Lato cap height); everything else by
    978/1012 (x-height). Both factors already include the 2000->2048 change.
  * Every glyph with a Calibri Light counterpart (matched through the cmap,
    through GSUB single/ligature substitutions, or through its base glyph) is
    fitted to Calibri Light's advance width: sidebearings are tightened about
    twice as much as the body (as in Carlito), the body is condensed with a
    shear-compensated x-scale (italic), and the lost vertical stem weight is
    restored with a FreeType-style horizontal embolden.
  * Vertical metrics, sub/superscript and strikeout values are Calibri Light's.
  * GSUB is compiled from sources/data/Lato3*2M.fea (the compiled Lato TTFs
    have an empty GSUB for the upright and an empty GPOS for the italic).
  * GPOS `kern` + `cpsp` are ported verbatim from Calibri Light (Carlito does
    the same: kerning is part of metric compatibility).

Usage:  python3 04_build_carlito_light.py [upright|italic|all] [--target ink|strokes] [--weight D]
        D is a Lato design-axis coordinate (Hairline 0, Light 250, Regular 540,
        Black 1000); default: calibrate to Calibri Light as described above.
Needs:  fontTools (with lxml/unicode extras), skia-pathops.
"""
import argparse
import copy
import math
import os
import re
import time
import unicodedata
from collections import Counter

from fontTools import subset
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib.error import FeatureLibError
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.transform import Transform
from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
BUILD = os.path.join(ROOT, "build")
DATA = os.path.join(ROOT, "sources", "data")
OUT_DIR = os.path.join(BUILD, "Carlito26")
WORD_FONTS = "/Applications/Microsoft Word.app/Contents/Resources/DFonts"

UPM = 2048
# Uniform scale factors, Lato units (2000 UPM) -> Carlito units (2048 UPM).
# Carlito Regular cap height 1314 / Lato Regular 1432; x-height 978 / 1012.
K_CAPS = 1314 / 1432
K_LC = 978 / 1012
# Sidebearings absorb BETA x their proportional share of a width change.
BETA = 2.0
SB_FLOOR = 0.4  # never reduce a positive sidebearing below 40% of itself
# Body condense/expand range before special handling. Beyond F_MAX a wider slot
# is padded rather than stretching the glyph (circled figures, IPA modifiers).
# References that don't come straight from the cmap (feature alternates, base
# glyphs of suffixed variants) are trusted only within [F_MIN_ALT, F_MAX].
F_MIN, F_MIN_ALT, F_MAX = 0.66, 0.85, 1.12
# Fraction of the source's vertical stem thickness that should survive the
# transform (Carlito Regular vs Lato Regular: caps ~0.94, lc ~0.985).
TAU_CAPS, TAU_LC = 0.95, 0.985
CAPS, LC = "caps", "lc"
# Stroke probes: (glyph, height as a fraction of x-height / cap height, index of
# the stroke among the outline crossings at that height, left to right).
# Vertical stems drive the embolden top-up. The stroke model that starts the
# weight calibration (and --target strokes) uses verticals and diagonals
# together, because Lato's diagonals are thinner relative to its verticals
# than Calibri's are (most of all in the italic), and matching verticals
# alone leaves the result looking light.
STEM_PROBES = {LC: (("l", 0.5, 0), ("n", 0.25, 0)), CAPS: (("H", 0.25, 0), ("I", 0.25, 0))}
DIAGONAL_PROBES = {LC: (("v", 0.5, 0), ("x", 0.75, 2)), CAPS: (("A", 0.6, 2), ("V", 0.5, 0))}
CALIBRATION_PROBES = {cls: STEM_PROBES[cls] + DIAGONAL_PROBES[cls] for cls in (LC, CAPS)}
# The default calibration target (--target ink): the ink a run of ordinary
# text puts down -- outline area per em of advance -- which also weighs in
# the horizontals, bowls and x-height that the stroke probes ignore. Set in a
# font with Calibri's advances, the two fonts' runs are the same length, so
# the areas compare directly. Public-domain English prose with a few figures.
INK_CORPUS = (
    "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of "
    "foolishness, it was the epoch of belief, it was the epoch of incredulity, it was the season of Light, "
    "it was the season of Darkness, it was the spring of hope, it was the winter of despair, we had "
    "everything before us, we had nothing before us, we were all going direct to Heaven, we were all going "
    "direct the other way. Call me Ishmael. Some years ago, never mind how long precisely, having little or "
    "no money in my purse, and nothing particular to interest me on shore, I thought I would sail about a "
    "little and see the watery part of the world. Whenever I find myself growing grim about the mouth; "
    "whenever it is a damp, drizzly November in my soul; then, I account it high time to get to sea as soon "
    "as I can. The Board approved the Q3 budget of $4,250,000 on 14 March 2024."
)

MASTERS_UPR = os.path.join(BUILD, "Lato3Upr2M", "ds-ufo", "masters")
MASTERS_ITA = os.path.join(BUILD, "Lato3Ita2M", "ds-ufo", "masters")
STYLES = {
    "upright": dict(
        masters=(os.path.join(MASTERS_UPR, "Lato26.~VF", "master_ttf_interpolatable", "Lato26-Hairline.ttf"),
                 os.path.join(MASTERS_UPR, "Lato26.~VF", "master_ttf_interpolatable", "Lato26-Black.ttf")),
        gdef_ref=os.path.join(MASTERS_UPR, "Lato26-Light.ttf"),
        fea=os.path.join(DATA, "Lato3Upr2M.fea"),
        calibri=os.path.join(WORD_FONTS, "calibril.ttf"),
        out=os.path.join(OUT_DIR, "Carlito26-Light.ttf"),
        italic=False,
        style_name="Light",
        ps_name="Carlito26-Light",
    ),
    "italic": dict(
        masters=(os.path.join(MASTERS_ITA, "Lato26.~VF", "master_ttf_interpolatable", "Lato26-HairlineItalic.ttf"),
                 os.path.join(MASTERS_ITA, "Lato26.~VF", "master_ttf_interpolatable", "Lato26-BlackItalic.ttf")),
        gdef_ref=os.path.join(MASTERS_ITA, "Lato26-LightItalic.ttf"),
        fea=os.path.join(DATA, "Lato3Ita2M.fea"),
        calibri=os.path.join(WORD_FONTS, "calibrili.ttf"),
        out=os.path.join(OUT_DIR, "Carlito26-LightItalic.ttf"),
        italic=True,
        style_name="Light Italic",
        ps_name="Carlito26-LightItalic",
    ),
}
# Lato design-axis coordinates (see sources/Lato3*2M.designspace)
DESIGN_LIGHT, DESIGN_REGULAR = 250, 540


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------- #
# Source weight: blend of the two interpolatable Lato masters
# --------------------------------------------------------------------------- #
def lerp(a, b, t):
    return a + (b - a) * t


def interpolate_lato(style, design):
    """Blend the Hairline and Black masters at `design` (0..1000). The masters
    are point-compatible (same contours, points, components); the blend is
    kept in float coordinates -- everything is redrawn later anyway. Layout
    tables and hinting are dropped: GSUB is compiled from the FEA, GPOS ported
    from Calibri."""
    t = design / 1000.0
    a, b = TTFont(style["masters"][0]), TTFont(style["masters"][1])
    order = a.getGlyphOrder()
    assert order == b.getGlyphOrder(), "masters differ in glyph order"
    glyf_a, glyf_b, hmtx_a, hmtx_b = a["glyf"], b["glyf"], a["hmtx"], b["hmtx"]
    for name in order:
        ga, gb = glyf_a[name], glyf_b[name]
        if ga.isComposite():
            assert gb.isComposite() and [c.glyphName for c in ga.components] == [c.glyphName for c in gb.components], name
            for ca, cb in zip(ga.components, gb.components):
                ca.x, ca.y = lerp(ca.x, cb.x, t), lerp(ca.y, cb.y, t)
                ta = getattr(ca, "transform", [[1, 0], [0, 1]])
                tb = getattr(cb, "transform", [[1, 0], [0, 1]])
                if ta != tb:
                    ca.transform = [[lerp(ta[i][j], tb[i][j], t) for j in range(2)] for i in range(2)]
        elif ga.numberOfContours > 0:
            assert len(ga.coordinates) == len(gb.coordinates) and ga.endPtsOfContours == gb.endPtsOfContours, name
            ga.coordinates = GlyphCoordinates(
                [(lerp(xa, xb, t), lerp(ya, yb, t)) for (xa, ya), (xb, yb) in zip(ga.coordinates, gb.coordinates)])
            ga.program = None
        hmtx_a[name] = (int(round(lerp(hmtx_a[name][0], hmtx_b[name][0], t))), hmtx_a[name][1])
    for tag in ("GSUB", "GPOS", "GDEF", "DSIG", "fpgm", "prep", "cvt "):
        if tag in a:
            del a[tag]
    return a


class FlattenPen(BasePen):
    """Approximates an outline by straight segments, for scanline measurements."""

    def __init__(self, glyph_set, steps=16):
        super().__init__(glyph_set)
        self.segments, self.steps = [], steps

    def _moveTo(self, p):
        self.cur = self.start = p

    def _lineTo(self, p):
        self.segments.append((self.cur, p))
        self.cur = p

    def _qCurveToOne(self, c, p):
        (x0, y0), n = self.cur, self.steps
        for i in range(1, n + 1):
            s = i / n
            q = ((1 - s) ** 2 * x0 + 2 * (1 - s) * s * c[0] + s * s * p[0],
                 (1 - s) ** 2 * y0 + 2 * (1 - s) * s * c[1] + s * s * p[1])
            self._lineTo(q)

    def _curveToOne(self, c1, c2, p):
        (x0, y0), n = self.cur, self.steps
        for i in range(1, n + 1):
            s, m = i / n, 1 - i / n
            q = (m ** 3 * x0 + 3 * m * m * s * c1[0] + 3 * m * s * s * c2[0] + s ** 3 * p[0],
                 m ** 3 * y0 + 3 * m * m * s * c1[1] + 3 * m * s * s * c2[1] + s ** 3 * p[1])
            self._lineTo(q)

    def _closePath(self):
        if self.cur != self.start:
            self._lineTo(self.start)

    def _endPath(self):
        pass


def measure_strokes(font, probes):
    """{cls: {(glyph, frac, index): thickness}}: stroke thickness in font units,
    perpendicular to the stroke (its direction is taken from the crossings a
    little higher up), for each probe."""
    gs, cmap = font.getGlyphSet(), font.getBestCmap()

    def top(ch):
        bp = BoundsPen(gs)
        gs[cmap[ord(ch)]].draw(bp)
        return bp.bounds[3]

    def crossings(segments, y):
        return sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                      for (x0, y0), (x1, y1) in segments if (y0 <= y < y1) or (y1 <= y < y0))

    heights = {LC: top("x"), CAPS: top("H")}
    out = {}
    for cls, cls_probes in probes.items():
        out[cls] = {}
        for probe in cls_probes:
            ch, frac, i = probe
            pen = FlattenPen(gs)
            gs[cmap[ord(ch)]].draw(pen)
            y, dy = heights[cls] * frac, heights[cls] * 0.01
            a, b = crossings(pen.segments, y), crossings(pen.segments, y + dy)
            width = a[i + 1] - a[i]
            slope = ((b[i] - a[i]) + (b[i + 1] - a[i + 1])) / 2.0 / dy  # dx/dy of the stroke
            out[cls][probe] = width / math.sqrt(1.0 + slope * slope)
    return out


def measure_stems(font):
    """{LC: units, CAPS: units}: vertical stem thickness, averaged per class."""
    return {cls: sum(v.values()) / len(v) for cls, v in measure_strokes(font, STEM_PROBES).items()}


def stroke_ratio(font, cal):
    """Mean over the calibration probes of font stroke / Calibri stroke."""
    a, b = measure_strokes(font, CALIBRATION_PROBES), measure_strokes(cal, CALIBRATION_PROBES)
    scale = cal["head"].unitsPerEm / font["head"].unitsPerEm
    ratios = [a[cls][p] * scale / b[cls][p] for cls in CALIBRATION_PROBES for p in CALIBRATION_PROBES[cls]]
    return sum(ratios) / len(ratios)


def ink_coverage(font, text=INK_CORPUS):
    """Outline area of `text` set in `font` (cmap glyphs, no shaping) as a
    fraction of the em-tall strip it occupies. Overlapping contours would count
    twice, so only use this on overlap-free fonts."""
    gs, cmap, hmtx, upm = font.getGlyphSet(), font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    areas = {}
    area = adv = 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        if g not in areas:
            pen = AreaPen(gs)
            gs[g].draw(pen)
            areas[g] = abs(pen.value)
        area += areas[g]
        adv += hmtx[g][0]
    return area / (adv * upm)


def ink_ratio(font, cal):
    """Ink coverage of INK_CORPUS in font / in Calibri."""
    return ink_coverage(font) / ink_coverage(cal)


TARGETS = {"strokes": stroke_ratio, "ink": ink_ratio}


def calibrate_weight(style, cal):
    """(design, slope): the design coordinate at which the recipe's output
    strokes (source stroke x TAU, see GlyphBuilder.top_up) equal Calibri
    Light's on average over the vertical and diagonal probes, and the rate at
    which that mean ratio grows per design unit. Strokes are linear along the
    axis, so the two masters fix them."""
    thin, black = TTFont(style["masters"][0]), TTFont(style["masters"][1])
    s_thin, s_black, s_cal = (measure_strokes(f, CALIBRATION_PROBES) for f in (thin, black, cal))
    taus = {LC: TAU_LC, CAPS: TAU_CAPS}
    # output stroke / Calibri's = tau * lerp(thin, black, d/1000) / cal is linear
    # in d, so its mean over the probes is too: solve mean == 1
    const = slope = count = 0.0
    for cls in CALIBRATION_PROBES:
        for probe in CALIBRATION_PROBES[cls]:
            c = taus[cls] / s_cal[cls][probe]
            const += c * s_thin[cls][probe]
            slope += c * (s_black[cls][probe] - s_thin[cls][probe]) / 1000.0
            count += 1
    design = (count - const) / slope
    for cls in CALIBRATION_PROBES:
        for probe in CALIBRATION_PROBES[cls]:
            here = taus[cls] * lerp(s_thin[cls][probe], s_black[cls][probe], design / 1000.0) / s_cal[cls][probe]
            light = taus[cls] * lerp(s_thin[cls][probe], s_black[cls][probe], DESIGN_LIGHT / 1000.0) / s_cal[cls][probe]
            log(f"  {cls} {probe[0]}: Calibri {s_cal[cls][probe]:.1f} units; modelled output/Calibri "
                f"{here - 1:+.1%} at design {design:.0f} (from Lato Light: {light - 1:+.1%})")
    return design, slope / count


def gdef_classes(lato, ref_path):
    """GDEF glyph classes (base/ligature/mark) taken from the compiled Lato
    static, by glyph name, else by glyph index (the upright static uses older
    names for a few glyphs)."""
    ref = TTFont(ref_path)
    classes = ref["GDEF"].table.GlyphClassDef.classDefs
    ref_order, order = ref.getGlyphOrder(), lato.getGlyphOrder()
    out, by_index = {}, 0
    for i, name in enumerate(order):
        if name in classes:
            out[name] = classes[name]
        elif i < len(ref_order) and ref_order[i] in classes and ref_order[i] not in order:
            out[name] = classes[ref_order[i]]
            by_index += 1
    log(f"  GDEF classes from {os.path.basename(ref_path)}: {len(out)} ({by_index} matched by index)")
    return out


# --------------------------------------------------------------------------- #
# Glyph classification (which uniform scale a glyph gets)
# --------------------------------------------------------------------------- #
def make_classifier(lato):
    rev = {}
    for cp, g in sorted(lato.getBestCmap().items()):
        rev.setdefault(g, cp)
    memo = {}

    def cls_of_unicode(cp):
        cat = unicodedata.category(chr(cp))
        if cat in ("Lu", "Lt", "Nd", "Sc", "No"):
            return CAPS
        return LC

    def classify(name, depth=0):
        if name in memo:
            return memo[name]
        res = None
        if name in rev:
            res = cls_of_unicode(rev[name])
        elif depth < 6:
            base, _, suffix = name.partition(".")
            if suffix:
                if suffix.startswith("onum"):
                    res = LC  # oldstyle figures sit on the x-height
                elif "case" in suffix.split(".") or suffix.startswith("case"):
                    res = CAPS  # accents/punctuation positioned for caps
                else:
                    res = classify(base, depth + 1) if base else LC
            elif "_" in name.strip("_"):
                parts = [p for p in name.strip("_").split("_") if p]
                res = CAPS if any(classify(p, depth + 1) == CAPS for p in parts) else LC
        if res is None:
            res = LC
        memo[name] = res
        return res

    return classify


# --------------------------------------------------------------------------- #
# GSUB helpers (used to match unencoded glyphs between Lato and Calibri)
# --------------------------------------------------------------------------- #
def gsub_maps(font):
    """{feature: [(inputs tuple, output)]} for single (type 1) and ligature
    (type 4) substitutions, including lookups reached through chain contexts."""
    if "GSUB" not in font:
        return {}
    gsub = font["GSUB"].table
    lookups = gsub.LookupList.Lookup
    out = {}

    def subtables(lk):
        for st in lk.SubTable:
            yield getattr(st, "ExtSubTable", st)

    def collect(li, tag, seen):
        if li in seen:
            return
        seen.add(li)
        for st in subtables(lookups[li]):
            t = st.LookupType
            if t == 1:
                for a, b in st.mapping.items():
                    out.setdefault(tag, []).append(((a,), b))
            elif t == 4:
                for first, ligs in st.ligatures.items():
                    for lig in ligs:
                        out.setdefault(tag, []).append((tuple([first] + list(lig.Component)), lig.LigGlyph))
            elif t in (5, 6):
                # (chained) contextual: follow the nested lookup records
                for set_attr, rule_attr in (("ChainSubRuleSet", "ChainSubRule"), ("SubRuleSet", "SubRule"),
                                            ("ChainSubClassSet", "ChainSubClassRule"), ("SubClassSet", "SubClassRule")):
                    for rs in getattr(st, set_attr, None) or []:
                        for rule in (getattr(rs, rule_attr, None) or []) if rs is not None else []:
                            for rec in rule.SubstLookupRecord:
                                collect(rec.LookupListIndex, tag, seen)
                for rec in getattr(st, "SubstLookupRecord", None) or []:
                    collect(rec.LookupListIndex, tag, seen)

    for fr in gsub.FeatureList.FeatureRecord:
        seen = set()
        for li in fr.Feature.LookupListIndex:
            collect(li, fr.FeatureTag, seen)
    return out


# Features whose single substitutions mean the same thing in both fonts.
MATCH_FEATURES = ["case", "sups", "subs", "sinf", "numr", "dnom", "onum", "lnum",
                  "tnum", "pnum", "locl", "ordn", "ccmp", "smcp", "c2sc", "frac"]


def build_glyph_mapping(lato, cal):
    """Return (width_source, cal2lato): width_source maps Lato glyph -> Calibri
    glyph used for its advance width (many-to-one allowed); cal2lato is the
    injective map used to rename Calibri's GPOS onto Lato glyph names."""
    lcm, ccm = lato.getBestCmap(), cal.getBestCmap()
    width_source, cal2lato, source_kind = {}, {}, {}

    def link(lg, cg, kind):
        if lg not in width_source:
            width_source[lg] = cg
            source_kind[lg] = kind
        if cg not in cal2lato and lg not in cal2lato.values():
            cal2lato[cg] = lg

    for cp in sorted(set(lcm) & set(ccm)):
        link(lcm[cp], ccm[cp], "cmap")
    n_cmap = len(width_source)

    lsub, csub = gsub_maps(lato), gsub_maps(cal)
    csingle = {tag: {ins: outg for ins, outg in v if len(ins) == 1} for tag, v in csub.items()}
    clig = {}
    for tag, v in csub.items():
        for ins, outg in v:
            if len(ins) > 1:
                clig.setdefault(ins, outg)
    # iterate single substitutions to a fixed point (handles chains like
    # one -> one.pnum -> one.onum_pnum)
    changed = True
    while changed:
        changed = False
        for tag in MATCH_FEATURES:
            for ins, outg in lsub.get(tag, []):
                if len(ins) != 1 or outg in width_source or ins[0] not in width_source:
                    continue
                cg = csingle.get(tag, {}).get((width_source[ins[0]],))
                if cg:
                    link(outg, cg, "gsub")
                    changed = True
    n_single = len(width_source) - n_cmap
    # ligatures: match through the component sequence
    lig_components = {}
    for tag, v in lsub.items():
        for ins, outg in v:
            if len(ins) > 1:
                lig_components.setdefault(outg, ins)
    for outg, ins in lig_components.items():
        if outg in width_source or not all(c in width_source for c in ins):
            continue
        cg = clig.get(tuple(width_source[c] for c in ins))
        if cg:
            link(outg, cg, "lig")
    n_lig = len(width_source) - n_cmap - n_single
    log(f"  matched glyphs: {n_cmap} via cmap, {n_single} via GSUB single subst, {n_lig} via ligatures; "
        f"{len(cal2lato)} Calibri glyphs renamable for GPOS")
    return width_source, source_kind, cal2lato, lig_components


# --------------------------------------------------------------------------- #
# Outline processing
# --------------------------------------------------------------------------- #
def embolden_xy(points, end_pts, xstrength, ystrength):
    """Port of FreeType's FT_Outline_EmboldenXY, in floating point.
    Moves points of each closed contour outward along the lateral bisector of
    the adjacent segments; the left and bottom borders stay put, the outline
    becomes xstrength wider and ystrength higher. Works on the TrueType control
    polygon (on- and off-curve points alike), like FreeType."""
    xs, ys = xstrength / 2.0, ystrength / 2.0
    if xs == 0 and ys == 0:
        return points
    # orientation: TrueType outlines have clockwise (negative area) outer contours
    area = 0.0
    first = 0
    for last in end_pts:
        pts = points[first:last + 1]
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            area += x0 * y1 - x1 * y0
        first = last + 1
    if area == 0:
        return points
    tt_orient = area < 0
    points = [tuple(p) for p in points]
    first = 0
    for last in end_pts:
        n = last - first + 1
        if n < 3:
            first = last + 1
            continue
        pts = points[first:last + 1]
        in_x = in_y = 0.0
        l_in = 0.0
        anchor = (0.0, 0.0)
        l_anchor = 0.0
        i, j, k = n - 1, 0, -1
        while j != i and i != k:
            if j != k:
                ox, oy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
                l_out = math.hypot(ox, oy)
                if l_out == 0:
                    j = j + 1 if j < n - 1 else 0
                    continue
                ox, oy = ox / l_out, oy / l_out
            else:
                ox, oy = anchor
                l_out = l_anchor
            if l_in != 0:
                if k < 0:
                    k = i
                    anchor = (in_x, in_y)
                    l_anchor = l_in
                d = in_x * ox + in_y * oy
                if d > -0.9375:  # turn less than ~160 degrees
                    d += 1.0
                    shift_x = in_y + oy
                    shift_y = in_x + ox
                    if tt_orient:
                        shift_x = -shift_x
                    else:
                        shift_y = -shift_y
                    q = ox * in_y - oy * in_x
                    if tt_orient:
                        q = -q
                    l = min(l_in, l_out)
                    shift_x = shift_x * xs / d if xs * q <= l * d else shift_x * l / q
                    shift_y = shift_y * ys / d if ys * q <= l * d else shift_y * l / q
                else:
                    shift_x = shift_y = 0.0
                while i != j:
                    pts[i] = (pts[i][0] + xs + shift_x, pts[i][1] + ys + shift_y)
                    i = i + 1 if i < n - 1 else 0
            else:
                i = j
            in_x, in_y = ox, oy
            l_in = l_out
            j = j + 1 if j < n - 1 else 0
        points[first:last + 1] = pts
        first = last + 1
    return points


def replay(recording, transform):
    """Replay recorded (decomposed) outline into a TTGlyphPen through an affine
    transform; returns the pen (points still float)."""
    pen = TTGlyphPen(None)
    recording.replay(TransformPen(pen, transform))
    return pen


def xbounds(points):
    xs = [p[0] for p in points]
    return (min(xs), max(xs)) if xs else (0.0, 0.0)


def ybounds(points):
    ys = [p[1] for p in points]
    return (min(ys), max(ys)) if ys else (0.0, 0.0)


def fit_sidebearings(lsb1, rsb1, adv1, target):
    """Carlito26-style split of a width change between sidebearings and body:
    sidebearings take BETA x their proportional share, floored at SB_FLOOR.
    Only positive sidebearings are tightened; when widening, overhanging
    (negative) italic sidebearings are pulled in as well."""
    d = target - adv1
    if d < 0:
        lp, rp = max(lsb1, 0.0), max(rsb1, 0.0)
    else:
        lp, rp = abs(lsb1), abs(rsb1)
    s = lp + rp
    if s <= 0 or adv1 <= 0:
        return lsb1, rsb1
    share = min(1.0, BETA * s / adv1)
    change = d * share
    if d < 0:
        change = max(change, -(1.0 - SB_FLOOR) * s)
    else:
        change = min(change, s)
    return lsb1 + change * lp / s, rsb1 + change * rp / s


class GlyphBuilder:
    def __init__(self, lato, cal, style, stems, classify, target_of, width_source):
        self.lato = lato
        self.glyph_set = lato.getGlyphSet()
        self.hmtx = lato["hmtx"]
        self.cal_glyph_set = cal.getGlyphSet()
        self.width_source = width_source
        self.style = style
        self.stems = stems  # {LC, CAPS}: source vertical stem, Lato units
        self.classify = classify
        self.target_of = target_of
        self.tan = math.tan(math.radians(7.0)) if style["italic"] else 0.0
        self.stats = Counter()
        self.factors = {}
        self.notes = []
        self.unicode_of = {}
        for cp, g in sorted(lato.getBestCmap().items()):
            self.unicode_of.setdefault(g, cp)

    def category(self, name):
        cp = self.unicode_of.get(name)
        return unicodedata.category(chr(cp)) if cp is not None else None

    def calibri_bounds(self, name):
        cg = self.width_source.get(name)
        if cg is None:
            return None
        bp = BoundsPen(self.cal_glyph_set)
        self.cal_glyph_set[cg].draw(bp)
        return bp.bounds

    def build(self, name):
        rec = DecomposingRecordingPen(self.glyph_set)
        self.glyph_set[name].draw(rec)
        cls = self.classify(name)
        k = K_CAPS if cls == CAPS else K_LC
        adv0 = self.hmtx[name][0]
        adv1 = k * adv0
        target, how = self.target_of(name)
        if name.startswith("_"):
            target, how = None, "none"  # pure component glyph: unreachable, keep as is
        self.stats[how] += 1
        cat = self.category(name) or ""
        cp = self.unicode_of.get(name)
        box_drawing = cp is not None and 0x2500 <= cp <= 0x257F
        symbolic = cat in ("So", "Sk") and not box_drawing

        pen1 = replay(rec, Transform().scale(k, k))
        pts1 = pen1.points
        if not pts1:  # empty glyph (space etc.)
            glyph = pen1.glyph()
            adv = target if target is not None else adv1
            return glyph, int(round(adv)), 0

        xmin1, xmax1 = xbounds(pts1)
        w1 = xmax1 - xmin1
        lsb1, rsb1 = xmin1, adv1 - xmax1
        stem = self.stems[cls]
        tau = TAU_CAPS if cls == CAPS else TAU_LC

        # Horizontal embolden that tops vertical stems back up after scaling:
        # a stem of `stem` units becomes stem*k*f wide; we want stem*tau.
        def top_up(fx):
            return max(0.0, stem * (tau - k * fx))

        f, delta, lsb2 = 1.0, top_up(1.0), lsb1
        symbol_box = None
        if target is None or target <= 0 or adv0 <= 0 or w1 <= 0:
            # no width reference (or a zero-width mark): uniform scale only
            adv = target if (target is not None and target >= 0) else adv1
            mode = "uniform"
        else:
            adv = target
            lsb2, rsb2 = fit_sidebearings(lsb1, rsb1, adv1, target)
            w2 = target - lsb2 - rsb2
            f0 = w2 / w1
            if box_drawing:
                mode, f, delta = "rule", f0, 0.0  # must span its advance
            elif w1 - stem * k < 0.3 * w1:
                # the glyph is essentially one stem wide (i, l, |): never
                # condense it, let the sidebearings take the whole change
                mode = "narrow"
                d = target - adv1 - delta
                lsb2 = lsb1 + d * (max(lsb1, 0) / (max(lsb1, 0) + max(rsb1, 0)) if (max(lsb1, 0) + max(rsb1, 0)) > 0 else 0.5)
            elif how != "cmap" and not (F_MIN_ALT <= f0 <= F_MAX):
                # a feature/suffix-derived reference that would distort the
                # glyph is a design mismatch, not a metric to honour
                mode, lsb2, adv, how = "uniform", lsb1, adv1, "none"
            elif f0 < F_MIN or (symbolic and f0 < F_MIN_ALT and self.calibri_bounds(name)):
                # far too wide for the slot: scale down uniformly. For symbols
                # (registered, tone letters...) sit exactly where Calibri's
                # glyph is -- this is what Carlito did with (R).
                symbol_box = self.calibri_bounds(name)
                if symbol_box:
                    f = (symbol_box[2] - symbol_box[0]) / w1
                    mode = "symbol"
                else:
                    f, mode = f0, "shrink"
                delta = 0.0
            elif f0 > F_MAX:
                h = ybounds(pts1)
                if (h[1] - h[0]) < 0.3 * w1:
                    mode, f = "rule", f0  # dashes, underscores: let them stretch
                else:
                    f = F_MAX
                    lsb2 += (w2 - f * w1) / 2.0
                    mode = "expand-capped"
                delta = top_up(f)
            else:
                mode, f = "fit", f0
                if top_up(f) > 0:
                    # solve f*w1 + top_up(f) == w2 so body + embolden fill the slot
                    f = (w2 - stem * tau) / (w1 - stem * k)
                delta = top_up(f)

        if mode == "symbol":
            t = Transform().scale(f, f).scale(k, k)
        elif mode == "shrink":
            ymin1, ymax1 = ybounds(pts1)
            cy = (ymin1 + ymax1) / 2.0
            t = Transform(f, 0, 0, f, 0, cy * (1 - f)).scale(k, k)  # about the bbox centre
        elif mode in ("uniform", "narrow"):
            t = Transform().scale(k, k)
        else:
            # condense in x; the shear term keeps the italic angle intact
            t = Transform(f, 0, (1 - f) * self.tan, 1, 0, 0).scale(k, k)

        pen = replay(rec, t)
        pts = pen.points
        if delta > 0.25:
            pts = embolden_xy(pts, pen.endPts, delta, 0.0)
            self.stats["emboldened"] += 1
        else:
            delta = 0.0
        xmin, xmax = xbounds(pts)
        if mode == "uniform":
            shift, yshift = -delta / 2.0, 0.0
        elif mode == "symbol":
            ymin, ymax = ybounds(pts)
            shift = (symbol_box[0] + symbol_box[2]) / 2.0 - (xmin + xmax) / 2.0
            yshift = (symbol_box[1] + symbol_box[3]) / 2.0 - (ymin + ymax) / 2.0
        else:
            shift, yshift = lsb2 - xmin, 0.0
        shift, yshift = round(shift), round(yshift)
        pen.points = [(x + shift, y + yshift) for x, y in pts]
        glyph = pen.glyph()
        glyph.recalcBounds(None)
        self.factors[name] = (mode, f, delta, cls, how, target, adv0, adv)
        if mode in ("shrink", "rule", "symbol"):
            self.notes.append(f"{name}: {mode} f={f:.3f} target={target:.0f} adv1={adv1:.0f} w1={w1:.0f}")
        return glyph, int(round(adv)), glyph.xMin


# --------------------------------------------------------------------------- #
# Width targets
# --------------------------------------------------------------------------- #
SIZE_SUFFIXES = ("sups", "subs", "sinf", "numr", "dnom", "small", "circled", "frac", "narrow", "short", "mid")
# spacing accents used as ligature "components" in Lato's FEA stand for the
# combining mark and contribute no width
ACCENT_NAMES = {"acute", "grave", "circumflex", "caron", "breve", "tilde", "dieresis", "macron", "ring",
                "hungarumlaut", "cedilla", "ogonek", "dotaccent", "commaaccent", "hookabove", "horn",
                "dotbelow", "ringbelow", "tonos", "dialytika", "psili", "dasia", "oxia", "varia", "perispomeni"}


def make_target_resolver(lato, cal, width_source, source_kind, lig_components, classify, glyph_classes):
    cal_hmtx = cal["hmtx"]
    glyf = lato["glyf"]
    memo = {}

    def is_accent(g):
        return glyph_classes.get(g) == 3 or g.endswith("comb") or g.split(".")[0] in ACCENT_NAMES

    def comp_widths(name):
        g = glyf[name]
        if not g.isComposite():
            return []
        return [(c.glyphName, lato["hmtx"][c.glyphName][0]) for c in g.components]

    def resolve(name, depth=0):
        if name in memo:
            return memo[name]
        if name not in glyf:
            return (None, "none")
        res = (None, "none")
        if name in width_source:
            res = (float(cal_hmtx[width_source[name]][0]), source_kind[name])
        elif depth < 8:
            if name in lig_components:
                comps = [c for c in lig_components[name] if not is_accent(c)]
                parts = [resolve(c, depth + 1) for c in comps]
                if parts and all(p[0] is not None for p in parts):
                    res = (sum(p[0] for p in parts), "ligsum")
            if res[0] is None and "." in name:
                base, suffix = name.rsplit(".", 1)
                # alternates keep their base's width; size-changing variants don't
                if base and base in glyf and not any(s in suffix for s in SIZE_SUFFIXES):
                    r = resolve(base, depth + 1)
                    if r[0] is not None:
                        res = (r[0], "suffix")
            if res[0] is None:
                comps = comp_widths(name)
                if comps:
                    # the widest component is the base letter
                    basec = max(comps, key=lambda c: c[1])[0]
                    r = resolve(basec, depth + 1)
                    if r[0] is not None:
                        res = (r[0], "component")
            if res[0] is None and "_" in name.strip("_") and not name.startswith("_"):
                parts = [resolve(p, depth + 1) for p in name.split("_") if not is_accent(p)]
                if parts and all(p[0] is not None for p in parts):
                    res = (sum(p[0] for p in parts), "namesum")
        memo[name] = res
        return res

    return resolve


# --------------------------------------------------------------------------- #
# FEA -> GSUB
# --------------------------------------------------------------------------- #
FEA_TOKEN_RENAMES = {"fi": "f_i", "fl": "f_l"}


def strip_comments(text):
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def compile_gsub(font, fea_path):
    text = strip_comments(open(fea_path, encoding="utf-8").read())
    for a, b in FEA_TOKEN_RENAMES.items():
        text = re.sub(rf"(?<![\w.\-@]){re.escape(a)}(?![\w\-])", b, text)
    removed = []
    for attempt in range(40):
        try:
            addOpenTypeFeaturesFromString(font, text, tables=["GSUB"])
            break
        except FeatureLibError as e:
            msg = str(e)
            names = re.findall(r'"([^"]+)" is not a glyph in the font', msg)
            if not names and "missing from the glyph set" in msg:
                names = [n.strip().split(" ")[0] for n in msg.split(":", 1)[1].split("\n") if n.strip()]
            if not names:
                raise
            for n in names:
                removed.append(n)
                pat = re.compile(rf"(?<![\w.\-@]){re.escape(n)}(?![\w.\-])")
                new_lines = []
                for line in text.splitlines():
                    if not pat.search(line):
                        new_lines.append(line)
                    elif re.match(r"\s*@[\w.\-]+\s*=", line):
                        new_lines.append(pat.sub("", line))  # drop from class def
                    else:
                        new_lines.append("")  # drop the statement
                text = "\n".join(new_lines)
            if "GSUB" in font:
                del font["GSUB"]
    else:
        raise RuntimeError("could not compile FEA")
    log(f"  GSUB compiled from {os.path.basename(fea_path)}; dropped unknown glyph names: {removed or 'none'}")
    gsub = font["GSUB"].table
    log(f"  GSUB: {len(gsub.LookupList.Lookup)} lookups, features {sorted({f.FeatureTag for f in gsub.FeatureList.FeatureRecord})}")


# --------------------------------------------------------------------------- #
# GPOS from Calibri Light (kern + cpsp), renamed onto Lato glyph names
# --------------------------------------------------------------------------- #
def resort_coverages(table, gid_of):
    """Glyph renaming changes glyph-ID order: re-sort every Coverage by the new
    IDs, permuting the arrays that run parallel to it."""
    def sort_parallel(cov, *arrays):
        order = sorted(range(len(cov.glyphs)), key=lambda i: gid_of[cov.glyphs[i]])
        cov.glyphs = [cov.glyphs[i] for i in order]
        for arr in arrays:
            if arr is not None:
                arr[:] = [arr[i] for i in order]

    def sort_cov(cov):
        if cov is not None:
            cov.glyphs.sort(key=gid_of.__getitem__)

    for lookup in table.LookupList.Lookup:
        for st in lookup.SubTable:
            st = getattr(st, "ExtSubTable", st)
            t, fmt = st.LookupType, st.Format
            if t == 2 and fmt == 1:  # PairPos: PairSet parallels Coverage
                sort_parallel(st.Coverage, st.PairSet)
            elif t == 1 and fmt == 2:  # SinglePos: Value parallels Coverage
                sort_parallel(st.Coverage, st.Value)
            elif t == 8 and fmt == 1:
                sort_parallel(st.Coverage, st.ChainPosRuleSet)
            elif t == 7 and fmt == 1:
                sort_parallel(st.Coverage, st.PosRuleSet)
            elif t in (7, 8) and fmt == 3:
                for attr in ("BacktrackCoverage", "InputCoverage", "LookAheadCoverage", "Coverage"):
                    for cov in getattr(st, attr, None) or []:
                        sort_cov(cov)
            elif hasattr(st, "Coverage"):  # class-based subtables, SinglePos 1, ...
                sort_cov(st.Coverage)
            else:
                raise NotImplementedError(f"GPOS lookup type {t} format {fmt}")


def port_gpos(cal_path, cal2lato, out_font):
    cal = TTFont(cal_path)
    cal.getGlyphOrder()
    # no outlines needed; without glyf the subsetter won't pull in component
    # glyphs we have no Lato counterpart for
    for tag in ("glyf", "loca"):
        del cal[tag]
    opts = subset.Options()
    opts.layout_features = ["kern", "cpsp"]
    opts.layout_scripts = ["DFLT", "latn", "cyrl", "grek"]
    opts.drop_tables = sorted(set(opts.drop_tables) | {"kern", "meta", "DSIG", "GSUB", "cvt ", "fpgm", "prep", "gasp", "hdmx", "LTSH", "VDMX", "name"})
    opts.glyph_names = True
    opts.hinting = False
    opts.notdef_outline = False
    sub = subset.Subsetter(opts)
    sub.populate(glyphs=list(cal2lato))
    sub.subset(cal)
    old_order = cal.getGlyphOrder()
    extra = [g for g in old_order if g not in cal2lato and g != ".notdef"]
    if extra:
        raise RuntimeError(f"subset kept unmapped Calibri glyphs: {extra[:10]}")
    data = cal["GPOS"].compile(cal)
    # re-read the table under the Lato glyph names
    cal.setGlyphOrder([cal2lato.get(g, g) for g in old_order])
    gpos = newTable("GPOS")
    gpos.decompile(data, cal)
    resort_coverages(gpos.table, out_font.getReverseGlyphMap())
    t = gpos.table
    # Calibri registers no DFLT script; give runs of unknown script the Latin kerning
    tags = [sr.ScriptTag for sr in t.ScriptList.ScriptRecord]
    if "DFLT" not in tags and "latn" in tags:
        latn = next(sr for sr in t.ScriptList.ScriptRecord if sr.ScriptTag == "latn")
        sr = ot.ScriptRecord()
        sr.ScriptTag = "DFLT"
        sr.Script = ot.Script()
        sr.Script.DefaultLangSys = copy.deepcopy(latn.Script.DefaultLangSys)
        sr.Script.LangSysRecord, sr.Script.LangSysCount = [], 0
        t.ScriptList.ScriptRecord.insert(0, sr)
        t.ScriptList.ScriptCount += 1
    gpos.compile(out_font)  # raises KeyError if any name is unknown to the new font
    feats = Counter(fr.FeatureTag for fr in t.FeatureList.FeatureRecord)
    scripts = [(sr.ScriptTag, [l.LangSysTag for l in sr.Script.LangSysRecord]) for sr in t.ScriptList.ScriptRecord]
    log(f"  GPOS ported from Calibri Light: {len(t.LookupList.Lookup)} lookups, features {dict(feats)}, scripts {scripts}")
    out_font["GPOS"] = gpos


# --------------------------------------------------------------------------- #
def build_glyphs(style, cal, design):
    """Interpolate the source at `design`, fit every glyph to Calibri Light and
    return (lato, FontBuilder, font with glyf/hmtx/cmap/maxp, GlyphBuilder,
    Calibri->Lato glyph name map, GDEF classes)."""
    lato = interpolate_lato(style, design)
    stems = measure_stems(lato)
    log(f"  source stems: lc {stems[LC]:.1f}, caps {stems[CAPS]:.1f} Lato units")
    glyph_order = lato.getGlyphOrder()
    # Lato's shipped GSUB is empty (upright) / GPOS is empty (italic): rebuild
    # GSUB from the FEA sources now, so features can guide glyph matching too.
    compile_gsub(lato, style["fea"])
    glyph_classes = gdef_classes(lato, style["gdef_ref"])
    classify = make_classifier(lato)
    width_source, source_kind, cal2lato, lig_components = build_glyph_mapping(lato, cal)
    target_of = make_target_resolver(lato, cal, width_source, source_kind, lig_components, classify, glyph_classes)

    gb = GlyphBuilder(lato, cal, style, stems, classify, target_of, width_source)
    glyphs, metrics = {}, {}
    for name in glyph_order:
        glyph, adv, lsb = gb.build(name)
        glyphs[name] = glyph
        metrics[name] = (adv, lsb)

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({cp: g for cp, g in lato.getBestCmap().items()})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupMaxp()
    out = fb.font
    removeOverlaps(out, ignoreErrors=True)  # also cleans up any self-intersection from emboldening
    # sync lsb after overlap removal / rounding
    glyf = out["glyf"]
    for name in glyph_order:
        g = glyf[name]
        g.recalcBounds(glyf)
        out["hmtx"][name] = (out["hmtx"][name][0], getattr(g, "xMin", 0) if g.numberOfContours else 0)
    return lato, fb, out, gb, cal2lato, glyph_classes


def build_style(style_key, design=None, target="ink"):
    style = STYLES[style_key]
    t0 = time.time()
    log(f"\n=== Building {style['ps_name']} ===")
    cal = TTFont(style["calibri"])
    calibrate = design is None
    if calibrate:
        design, slope = calibrate_weight(style, cal)
    history = []
    for attempt in range(4):
        wght = 300 + 100 * (design - DESIGN_LIGHT) / (DESIGN_REGULAR - DESIGN_LIGHT)  # designspace axis map
        log(f"  source weight: Lato design {design:.0f} (~wght {wght:.0f}; Light {DESIGN_LIGHT}, Regular {DESIGN_REGULAR})")
        lato, fb, out, gb, cal2lato, glyph_classes = build_glyphs(style, cal, design)
        if not calibrate:
            break
        # the calibration models the transform as source x TAU on the probes;
        # measure what the build really did (to the probes, or to the ink of a
        # text run) and correct: with the modelled slope first, then with the
        # slope between the last two builds
        mean = TARGETS[target](out, cal)
        log(f"  output {target} vs Calibri Light: {mean - 1:+.1%}")
        history.append((design, mean))
        if abs(mean - 1) < 0.005 or attempt == 3:
            break
        if len(history) > 1:
            (d0, m0), (d1, m1) = history[-2:]
            slope = (m1 - m0) / (d1 - d0)
        design += (1 - mean) / slope
    glyph_order = lato.getGlyphOrder()

    log(f"  glyphs: {len(glyph_order)}; width source: {dict(gb.stats)}")
    ncls = Counter(v[3] for v in gb.factors.values())
    nmode = Counter(v[0] for v in gb.factors.values())
    fs = sorted(v[1] for v in gb.factors.values() if v[0] == "fit")
    if fs:
        log(f"  classes: {dict(ncls)}; modes: {dict(nmode)}; body factor for fitted glyphs: "
            f"min {fs[0]:.3f} / median {fs[len(fs)//2]:.3f} / max {fs[-1]:.3f}")
    for n in gb.notes:
        log("    note:", n)
    os.makedirs(OUT_DIR, exist_ok=True)
    report = os.path.join(OUT_DIR, f"report-{style['ps_name']}.tsv")
    with open(report, "w") as fh:
        fh.write("glyph\tclass\tmode\tsource\tbody_factor\tembolden\ttarget\tlato_adv\tadv\n")
        for name in glyph_order:
            if name in gb.factors:
                mode, f, delta, cls, how, target, adv0, adv = gb.factors[name]
                fh.write(f"{name}\t{cls}\t{mode}\t{how}\t{f:.3f}\t{delta:.1f}\t{'' if target is None else int(target)}\t{adv0}\t{int(round(adv))}\n")
    log(f"  per-glyph report: {os.path.relpath(report, ROOT)}")

    # measured x-height / cap height
    glyf = out["glyf"]
    cmap = out.getBestCmap()
    def top(ch):
        g = glyf[cmap[ord(ch)]]
        g.recalcBounds(glyf)
        return g.yMax
    x_height, cap_height = top("x"), top("H")

    cal_os2, cal_hhea, cal_post = cal["OS/2"], cal["hhea"], cal["post"]
    fb.setupHorizontalHeader(
        ascent=cal_hhea.ascent, descent=cal_hhea.descent, lineGap=cal_hhea.lineGap,
        caretSlopeRise=UPM if style["italic"] else 1,
        caretSlopeRun=int(round(UPM * math.tan(math.radians(7.0)))) if style["italic"] else 0,
        caretOffset=0,
    )
    version = "1.000"
    fb.setupNameTable({
        "copyright": ('Copyright (c) 2011-2020 by tyPoland Lukasz Dziedzic (http://www.typoland.com/) with Reserved Font Name "Lato". '
                      f'Carlito {style["style_name"]} is derived from Lato and metric-compatible with Calibri Light. '
                      'Licensed under the SIL Open Font License, Version 1.1 (http://scripts.sil.org/OFL).'),
        "familyName": "Carlito26 Light",
        "styleName": "Italic" if style["italic"] else "Regular",
        "uniqueFontIdentifier": f"{version};UKWN;{style['ps_name']}",
        "fullName": f"Carlito26 {style['style_name']}",
        "version": f"Version {version}",
        "psName": style["ps_name"],
        "manufacturer": "tyPoland Lukasz Dziedzic (Lato); Carlito Light derivative built from lato-source",
        "designer": "Łukasz Dziedzic",
        "description": (f"Carlito {style['style_name']} is a Light companion to Carlito: Lato, at a weight matching Calibri Light's "
                        "stems, reshaped to be metric-compatible with Calibri Light (advance widths, kerning and vertical metrics)."),
        "vendorURL": "https://www.latofonts.com/",
        "designerURL": "http://www.typoland.com/",
        "licenseDescription": ('This Font Software is licensed under the SIL Open Font License, Version 1.1. '
                               'This license is available with a FAQ at: http://scripts.sil.org/OFL'),
        "licenseInfoURL": "http://scripts.sil.org/OFL",
        "typographicFamily": "Carlito26",
        "typographicSubfamily": style["style_name"],
    }, mac=False)  # Windows-platform names only, like Carlito (avoids an 'ltag' table)
    # OS/2: start from Lato's (Unicode/codepage ranges), overlay Calibri Light's metrics
    os2 = lato["OS/2"]
    os2.version = 4
    os2.usWeightClass = 300
    os2.usWidthClass = 5
    os2.fsType = 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = cal_os2.sTypoAscender, cal_os2.sTypoDescender, cal_os2.sTypoLineGap
    os2.usWinAscent, os2.usWinDescent = cal_os2.usWinAscent, cal_os2.usWinDescent
    for attr in ("ySubscriptXSize", "ySubscriptYSize", "ySubscriptXOffset", "ySubscriptYOffset",
                 "ySuperscriptXSize", "ySuperscriptYSize", "ySuperscriptXOffset", "ySuperscriptYOffset",
                 "yStrikeoutSize", "yStrikeoutPosition"):
        setattr(os2, attr, getattr(cal_os2, attr))
    os2.panose = cal_os2.panose
    os2.sxHeight, os2.sCapHeight = x_height, cap_height
    os2.fsSelection = 0x0100 | (0x0001 if style["italic"] else 0)  # WWS (+ ITALIC)
    os2.achVendID = "UKWN"
    os2.usDefaultChar, os2.usBreakChar = 0, 32
    out["OS/2"] = os2
    os2.recalcAvgCharWidth(out)

    head = out["head"]
    head.fontRevision = float(version)
    head.flags = 0x000B
    head.lowestRecPPEM = 8
    head.macStyle = 0x0002 if style["italic"] else 0
    fb.setupPost(isFixedPitch=0, italicAngle=-7.0 if style["italic"] else 0.0,
                 underlinePosition=cal_post.underlinePosition, underlineThickness=cal_post.underlineThickness)
    gasp = newTable("gasp")
    gasp.version = 1
    gasp.gaspRange = {0xFFFF: 0x000F}
    out["gasp"] = gasp

    # GDEF glyph classes from Lato (marks needed for IgnoreMarks kerning)
    gdef = ot.GDEF()
    gdef.Version = 0x00010000
    gdef.GlyphClassDef = ot.GlyphClassDef()
    gdef.GlyphClassDef.classDefs = dict(glyph_classes)
    gdef.AttachList = gdef.LigCaretList = gdef.MarkAttachClassDef = None
    gdef_table = newTable("GDEF")
    gdef_table.table = gdef
    out["GDEF"] = gdef_table

    out["GSUB"] = lato["GSUB"]  # same glyph names; compiled above
    port_gpos(style["calibri"], cal2lato, out)
    os2.usMaxContext = maxCtxFont(out)

    os.makedirs(OUT_DIR, exist_ok=True)
    from truetype_hinting import hint_font
    hint_font(out)
    out.save(style["out"])
    log(f"  wrote {os.path.relpath(style['out'], ROOT)}  ({os.path.getsize(style['out'])//1024} KB) in {time.time()-t0:.1f}s")
    log(f"  x-height {x_height}, cap height {cap_height} (Calibri Light: {cal_os2.sxHeight}/{cal_os2.sCapHeight}; Carlito Regular: 978/1314)")
    return style["out"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("style", nargs="?", default="all", choices=["all", "upright", "italic"])
    ap.add_argument("--weight", type=float, metavar="D",
                    help=f"Lato design-axis coordinate of the source (Light {DESIGN_LIGHT}, Regular {DESIGN_REGULAR}); "
                         "default: calibrate to Calibri Light (see --target)")
    ap.add_argument("--target", choices=sorted(TARGETS), default="ink",
                    help="what the calibration matches to Calibri Light: the ink coverage of a run of English prose, "
                         "or the vertical and diagonal stroke probes (default: %(default)s)")
    args = ap.parse_args()
    for key in (["upright", "italic"] if args.style == "all" else [args.style]):
        build_style(key, args.weight, args.target)
