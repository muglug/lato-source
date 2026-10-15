#!/usr/bin/env python3
"""Vector before/after proofs for the punctuation kerning revision."""
import argparse
import importlib
import json
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from lowercase_kerning import CONFIG, pair_advance
from punctuation_kerning import adjustment
from variable_font_support import ProofFace

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT
INK = '#202B36'
AFTER = '#185C62'
MUTED = '#64717D'


def label(c, x, y, text, size=10, color=INK, bold=False):
    c.setFillColor(HexColor(color))
    c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
    c.drawString(x, y, text)


def specimen(c, face, text, x, y, size, color=INK):
    c.saveState()
    c.setFillColor(HexColor(color))
    c.translate(x, y)
    c.scale(size / face.upm, size / face.upm)
    cursor = 0
    for gid, ax, ay, ox, oy in face.shaped(text):
        assert gid and ay == 0
        c.saveState()
        c.translate(cursor + ox, oy)
        c.drawPath(face.outline(gid, c), fill=1, stroke=0, fillMode=1)
        c.restoreState()
        cursor += ax
    c.restoreState()
    return cursor * size / face.upm


def path(style, weight):
    name = weight if style == 'Upr' else ('Italic' if weight == 'Regular' else weight + 'Italic')
    return Path(f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{name}.ttf')


def header(c, title, subtitle, page):
    c.setFillColor(HexColor('#FAFAF7'))
    c.rect(0, 0, 612, 842, fill=1, stroke=0)
    label(c, 36, 803, title, 21, bold=True)
    label(c, 36, 779, subtitle, 9, MUTED)
    label(c, 36, 27, 'Lato26  /  punctuation spacing  /  vector outlines, native HarfBuzz placement', 8, MUTED)
    label(c, 565, 27, str(page), 8, MUTED)


def gap(face):
    cmap = face.tt.getBestCmap()
    left, right = cmap[108], cmap[46]
    bounds = []
    for name in (left, right):
        pen = BoundsPen(face.glyphs)
        face.glyphs[name].draw(pen)
        bounds.append(pen.bounds)
    return face.tt['hmtx'][left][0] + pair_advance(face.tt, left, right) + bounds[1][0] - bounds[0][2]


def proof(snapshot, output):
    policy = json.loads(CONFIG.read_text())['punctuation_allowance']
    previous = json.loads((snapshot / CONFIG.relative_to(ROOT)).read_text()).get('punctuation_allowance')
    def prior(right, design):
        return adjustment(previous, right, design) if previous else 0
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=(612, 842), pageCompression=1)
    c.setTitle('Lato26 - l punctuation spacing before and after')
    c.setAuthor('Lato26')
    for page, (style, title) in enumerate((('Upr', 'Upright'), ('Ita', 'Italic')), 1):
        heavier = [adjustment(policy, 'period', build.WEIGHTS[w]) for w in ('Bold', 'Heavy', 'Black')]
        header(c, title + ': before and after',
               f'Punctuation allowances: Bold +{heavier[0]}, Heavy +{heavier[1]}, Black +{heavier[2]} (2000 UPM).', page)
        label(c, 145, 745, 'BEFORE', 9, MUTED, True)
        label(c, 362, 745, 'AFTER', 9, AFTER, True)
        for row, (weight, design) in enumerate(build.WEIGHTS.items()):
            y = 704 - row * 67
            rel = path(style, weight)
            a, b = ProofFace(snapshot / rel), ProofFace(ROOT / rel)
            label(c, 36, y + 7, weight, 10, bold=True)
            delta = adjustment(policy, 'period', design)
            label(c, 36, y - 9, f'period +{prior("period", design)} to +{delta}', 8, MUTED)
            specimen(c, a, 'l. l, l\u2026 l: l; l!', 145, y, 24)
            specimen(c, b, 'l. l, l\u2026 l: l; l!', 362, y, 24, AFTER)
            specimen(c, a, 'l] l} l\u201a l\u201e', 145, y - 22, 17)
            specimen(c, b, 'l] l} l\u201a l\u201e', 362, y - 22, 17, AFTER)
            c.setStrokeColor(HexColor('#E0E4E3'))
            c.line(36, y - 32, 576, y - 32)
        colons = [adjustment(policy, 'colon', build.WEIGHTS[w]) for w in ('Bold', 'Heavy', 'Black')]
        label(c, 36, 82, f'Colon group: +20 through Semibold; Bold +{colons[0]}, Heavy +{colons[1]}, Black +{colons[2]}.', 9, MUTED)
        label(c, 36, 65, 'Letter-pair spacing, fl ligatures, glyph widths, outlines and hinting are unchanged.', 9, MUTED)
        c.showPage()
    header(c, 'Enlarged period comparison', 'Equal em size. Fira is the kerning reference; its outlines and sidebearings differ.', 3)
    label(c, 36, 763, 'Gap labels use horizontal outline bounds; italic overhang can produce a negative value.', 8, MUTED)
    for x, title in ((132, 'BEFORE'), (305, 'AFTER'), (469, 'FIRA SANS')):
        label(c, x, 745, title, 9, MUTED, True)
    for row, (style, weight) in enumerate((('Upr', 'Heavy'), ('Upr', 'Black'), ('Ita', 'Heavy'), ('Ita', 'Black'))):
        y = 628 - row * 157
        rel = path(style, weight)
        ref = ('ExtraBold' if weight == 'Heavy' else 'Heavy') + ('Italic' if style == 'Ita' else '')
        faces = [ProofFace(snapshot / rel), ProofFace(ROOT / rel), ProofFace(ROOT / f'.cache/fira-sans-4.301/FiraSans-{ref}.ttf')]
        label(c, 36, y + 61, weight, 10, bold=True)
        label(c, 36, y + 45, 'Upright' if style == 'Upr' else 'Italic', 9, MUTED)
        for x, face, color in zip((132, 305, 469), faces, (INK, AFTER, MUTED)):
            specimen(c, face, 'l.', x, y, 128, color)
            label(c, x, y - 24, f'ink gap: {gap(face) * 2000 / face.upm:.0f} units', 9, color)
        total = adjustment(policy, 'period', build.WEIGHTS[weight])
        delta = total - prior('period', build.WEIGHTS[weight])
        label(c, 132, y - 44, f'This pass: +{delta} units; total allowance +{total}. Change at 16 px: {delta * 16 / 2000:.3f} px.', 9, MUTED)
    c.showPage()
    header(c, 'Accents and variable fonts', 'The same punctuation policy applies to l variants; established letter-pair rhythm is preserved.', 4)
    label(c, 36, 742, 'ACCENTED FORMS - BLACK', 10, MUTED, True)
    label(c, 155, 718, 'BEFORE', 9, MUTED, True)
    label(c, 365, 718, 'AFTER', 9, AFTER, True)
    for row, style in enumerate(('Upr', 'Ita')):
        y = 684 - row * 51
        rel = path(style, 'Black')
        label(c, 36, y, 'Upright' if style == 'Upr' else 'Italic', 10)
        specimen(c, ProofFace(snapshot / rel), '\u013a. \u013c, \u013e\u2026 \u0142: \u1e37;', 155, y, 26)
        specimen(c, ProofFace(ROOT / rel), '\u013a. \u013c, \u013e\u2026 \u0142: \u1e37;', 365, y, 26, AFTER)
    label(c, 36, 582, 'VARIABLE EXPORTS - AFTER', 10, MUTED, True)
    label(c, 157, 558, 'UPRIGHT', 9, MUTED, True)
    label(c, 365, 558, 'ITALIC', 9, MUTED, True)
    for row, weight in enumerate(range(100, 901, 100)):
        y = 528 - row * 40
        label(c, 36, y, f'wght {weight}', 9)
        for x, suffix in ((155, ''), (365, 'Italic')):
            face = ProofFace(ROOT / f'build/Lato26-Variable/Lato26-Variable{suffix}.ttf', weight)
            specimen(c, face, 'l. l, l\u2026 le lo ly ll', x, y, 22, AFTER)
    label(c, 36, 154, 'Sources: four editable Glyphs masters. Built variable fonts: exact nine-weight spacing curve.', 9, MUTED)
    additions = ', '.join(str(v) for _, v in policy['curves']['period'])
    label(c, 36, 133, f'Period-group additions: {additions} units from Hairline to Black.', 9, MUTED)
    label(c, 36, 100, 'Reference: bBoxType/FiraSans, Fira Sans 4.301; pinned commit f54eeb3124c6.', 8, MUTED)
    c.linkURL('https://github.com/bBoxType/FiraSans/tree/f54eeb3124c63fe9b5bcd36d09d1cd46788cd15e', (36, 94, 560, 112), relative=0)
    c.showPage()
    c.save()
    print(output, '4 vector pages', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/pdf/Lato26-Punctuation-Spacing.pdf')
    args = parser.parse_args()
    proof(args.snapshot, args.output)
