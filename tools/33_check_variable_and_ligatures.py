#!/usr/bin/env python3
"""Exercise source ligatures, variable spacing, and native variation rendering."""
import ctypes as C
import hashlib
import importlib
import json
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from lcd_font_proofs import RasterFace, bind, FaceRecord, set_size, load, render
from lowercase_kerning import pair_advance, CONFIG
from variable_font_support import ProofFace, PairValues

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT
set_design = bind('FT_Set_Var_Design_Coordinates', C.c_int,
                  [C.POINTER(FaceRecord), C.c_uint, C.POINTER(C.c_long)])


def check_ligatures(face, report):
    for text, codepoint in [('fi', 0xfb01), ('ffi', 0xfb03), ('fl', 0xfb02)]:
        result = face.shaped(text)
        assert len(result) == 1 and face.order[result[0][0]] == face.tt.getBestCmap()[codepoint], (face.path, text, result)
        plain = face.shaped(text, liga=False)
        assert [face.order[g[0]] for g in plain] == list(text), (face.path, text, plain)
        report['shaping_checks'] += 2
    for text in ('fį', 'fí', 'office', 'affinity', 'finite'):
        shaped = face.shaped(text)
        assert all(g[0] for g in shaped) and len(shaped) < len(text), (face.path, text, shaped)
        report['shaping_checks'] += 1


def bounds(glyph_set, name):
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def main():
    report = {'status': 'running', 'static_fonts': 0, 'shaping_checks': 0,
              'native_loads': 0, 'native_renders': 0, 'pair_gap_checks': 0, 'variable_fonts': []}
    config = json.loads(CONFIG.read_text())
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        folder = ROOT / f'build/Lato3{style}2M/ds-ufo/masters'
        for path in sorted(folder.glob('Lato26-*')):
            if path.suffix not in ('.otf', '.ttf'):
                continue
            check_ligatures(ProofFace(path), report)
            report['static_fonts'] += 1
        italic = 'Italic' if style == 'Ita' else ''
        path = ROOT / f'build/Lato26-Variable/Lato26-Variable{italic}.ttf'
        font = TTFont(path, checkChecksums=2)
        assert [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in font['fvar'].axes] == [('wght', 100, 400, 900)]
        assert [i.coordinates['wght'] for i in font['fvar'].instances] == list(range(100, 901, 100))
        assert all(not getattr(font['glyf'][n], 'program', None) or not font['glyf'][n].program.getBytecode()
                   for n in font.getGlyphOrder())
        native = RasterFace(path)
        for weight in range(100, 901, 50):
            check_ligatures(ProofFace(path, weight), report)
            coordinate = (C.c_long * 1)(weight * 65536)
            assert set_design(native.handle, 1, coordinate) == 0
            for ppem in (14, 16, 24):
                assert set_size(native.handle, 0, ppem * 64, 72, 72) == 0
                for gid in range(len(font.getGlyphOrder())):
                    assert load(native.handle, gid, (3 << 16) | (1 << 15) | (1 << 7)) == 0, (style, weight, ppem, gid)
                    report['native_loads'] += 1
                    assert render(native.handle.contents.glyph, 3) == 0, (style, weight, ppem, gid)
                    report['native_renders'] += 1
        gap_errors = []
        for i, (label, design) in enumerate(build.WEIGHTS.items()):
            weight = 100 + i * 100
            label = 'Italic' if italic and label == 'Regular' else label + italic
            static = TTFont(folder / f'Lato26-{label}.ttf')
            old_set, new_set = static.getGlyphSet(), font.getGlyphSet(location={'wght': weight})
            pairs = PairValues(font, weight)
            old_bounds = {n: bounds(old_set, n) for n in 'laceowyl'}
            new_bounds = {n: bounds(new_set, n) for n in 'laceowyl'}
            for right in 'aceowyl':
                old_gap = static['hmtx']['l'][0] + pair_advance(static, 'l', right) + old_bounds[right][0] - old_bounds['l'][2]
                new_gap = new_set['l'].width + pairs('l', right) + new_bounds[right][0] - new_bounds['l'][2]
                error = abs(new_gap - old_gap)
                # Between the four masters, interpolation and independent
                # static conversion can differ by up to 3/2000 em (0.024 px
                # at 16 px). The authored master pairs are checked to .51 below.
                assert error <= 3, (style, weight, right, old_gap, new_gap)
                gap_errors.append(error)
                report['pair_gap_checks'] += 1
            # e's authored master geometry survives the variable conversion.
            if style == 'Upr' and design in (0, 540, 780, 1000):
                assert max(abs(a-b) for a,b in zip(bounds(old_set, 'e'), bounds(new_set, 'e'))) <= 1
            # Compare the complete special-pair set at the four authored masters.
            if design in (0, 540, 780, 1000):
                spec = config['styles'][style]
                names = set(spec['left']) | set(spec['right'])
                mapped = {n: build.output_name(source, n, static) for n in names}
                ob = {n: bounds(old_set, mapped[n]) for n in names}
                nb = {n: bounds(new_set, n) for n in names}
                for left in spec['left']:
                    for right in spec['right']:
                        a, z = mapped[left], mapped[right]
                        old_gap = static['hmtx'][a][0] + pair_advance(static, a, z) + ob[right][0] - ob[left][2]
                        new_gap = new_set[left].width + pairs(left, right) + nb[right][0] - nb[left][2]
                        assert abs(new_gap-old_gap) <= .51, (style, weight, left, right, old_gap, new_gap)
                        report['pair_gap_checks'] += 1
        report['variable_fonts'].append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                         'glyphs': len(font.getGlyphOrder()), 'rendered_weights': list(range(100,901,50)),
                                         'maximum_common_pair_gap_error': max(gap_errors), 'hinting': 'unhinted'})
        print(path.name, 'shaping, continuous weight, pair spacing and native rendering passed', flush=True)
    report['status'] = 'passed'
    (ROOT / 'build/proofs/variable-ligature-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print({k: v for k, v in report.items() if k != 'variable_fonts'}, flush=True)


if __name__ == '__main__':
    main()
