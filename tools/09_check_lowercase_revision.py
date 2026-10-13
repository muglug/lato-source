#!/usr/bin/env python3
"""Validate revised fonts, optionally comparing them to a pre-revision build.

Usage: python tools/09_check_lowercase_revision.py [--baseline-dir PATH]
PATH contains the old build/ contents (Carlito/, Lato3Upr2M/, Lato3Ita2M/).
Requires the build dependencies plus matplotlib for FreeType raster checks.
"""
import argparse
import copy
import importlib
import json
import math
from pathlib import Path

import openstep_plist
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from matplotlib.ft2font import FT2Font
from PIL import ImageFont
from modified_font_names import original_path, rename_font, FAMILY_NAME_IDS
from lowercase_kerning import (CONFIG as SPACING_CONFIG, strip_spacing,
                               spacing_strength, e_left_edge_difference, pair_advance, optical_addition)

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT


def rasterize(path, order):
    face = FT2Font(str(path))
    for index in range(len(order)):
        face.load_glyph(index)


def compare_unchanged(font, old, changed, spacing_metadata=None):
    rename_font(old)
    assert font.getGlyphOrder() == old.getGlyphOrder()
    assert font.getBestCmap() == old.getBestCmap()
    layout_font = font
    if spacing_metadata:
        layout_font = TTFont()
        layout_font.setGlyphOrder(font.getGlyphOrder())
        layout_font['GPOS'] = copy.deepcopy(font['GPOS'])
        strip_spacing(layout_font, spacing_metadata)
    for tag in ('GSUB', 'GPOS', 'GDEF', 'name', 'OS/2', 'cmap'):
        if tag in old:
            current = layout_font if tag == 'GPOS' else font
            if tag == 'GPOS':
                # Adding a lookup can repack existing OpenType offsets.
                assert current[tag].compile(current) == old[tag].compile(old), tag
            else:
                assert current.getTableData(tag) == old.getTableData(tag), tag
    current_set, old_set = font.getGlyphSet(), old.getGlyphSet()
    for name in font.getGlyphOrder():
        if name in changed:
            continue
        current, previous = RecordingPen(), RecordingPen()
        current_set[name].draw(current)
        old_set[name].draw(previous)
        assert current.value == previous.value, ('unrelated outline', name)
        assert font['hmtx'][name] == old['hmtx'][name], ('unrelated metrics', name)


def check_regular(baseline):
    reference = ROOT/'build/Lato3Upr2M/ds-ufo/masters/Lato26-Regular.glyphs'
    glyphs = {g['glyphname']: g for g in openstep_plist.load(reference.open())['glyphs']}
    font = TTFont(reference.with_suffix('.ttf'))
    if baseline:
        previous = baseline/'Lato3Upr2M/ds-ufo/masters/Lato-Regular.glyphs'
        old = {g['glyphname']: g for g in openstep_plist.load(previous.open())['glyphs']}
        for name in ('a', 'e'):
            assert glyphs[name]['layers'][0]['shapes'] == old[name]['layers'][0]['shapes']
    for name in ('a', 'e'):
        glyph = font['glyf'][name]
        start = 0
        shapes = glyphs[name]['layers'][0]['shapes']
        assert len(glyph.endPtsOfContours) == len(shapes)
        for end, shape in zip(glyph.endPtsOfContours, shapes):
            expected = [tuple(map(float, p[:2])) for p in shape['nodes']]
            actual = list(glyph.coordinates[start:end+1])
            start = end+1
            assert len(expected) == len(actual), name
            assert any(all(expected[i] == actual[(rotation+direction*i) % len(actual)]
                           for i in range(len(actual)))
                       for direction in (-1, 1) for rotation in range(len(actual))), name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    spacing = json.loads(SPACING_CONFIG.read_text()) if SPACING_CONFIG.exists() else None
    results = {'static_fonts': 0, 'interpolatable_masters': 0, 'carlito_fonts': 0,
               'glyph_rasterizations': 0, 'baseline_comparison': bool(args.baseline_dir)}
    if spacing:
        results['ae_master_joins_checked'] = 0
        results['spacing_shaped_pairs'] = 0
        results['doubled_l_shaping_checks'] = 0
        results['matched_e_o_gaps'] = 0
        results['matched_e_c_gaps'] = 0
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        if spacing:
            for name in ('ae', 'aeTurned', 'aeTurnedmod'):
                for black in (False, True):
                    e, _, a = build.revision.contours(build.revision.master(source.glyphs[name], black))
                    upper, lower = (16, 17) if len(e['nodes']) == 25 else (10, 11)
                    for ai, ei in ((12, lower), (13, upper)):
                        assert abs(build.revision.points(a['nodes'][ai])[-1, 1]-
                                   build.revision.points(e['nodes'][ei])[-1, 1]) < .001, name
                    results['ae_master_joins_checked'] += 1
        directory = Path(f'Lato3{style}2M/ds-ufo/masters')
        suffix = 'Italic' if style == 'Ita' else ''
        for weight, design in build.WEIGHTS.items():
            label = 'Italic' if suffix and weight == 'Regular' else weight+suffix
            for extension in ('ttf', 'otf'):
                relative = directory/f'Lato26-{label}.{extension}'
                path = ROOT/'build'/relative
                font = TTFont(path, checkChecksums=2)
                changed = {build.output_name(source, n, font) for n in source.affected}
                if args.baseline_dir:
                    metadata = spacing['fonts'][str(Path('build')/relative)] if spacing else None
                    compare_unchanged(font, TTFont(args.baseline_dir/original_path(relative)), changed, metadata)
                    if spacing:
                        before = ImageFont.truetype(str(args.baseline_dir/original_path(relative)), 2000)
                        after = ImageFont.truetype(str(path), 2000)
                        for sample in ('la', 'le', 'lo', 'lc', 'lè', 'lô', 'lé', 'ló', 'lv', 'lw', 'ly'):
                            base = 'o' if sample[-1] in 'oôó' else sample[-1]
                            matches_e = base in spacing.get('match_e_spacing_rights', [])
                            strength = spacing_strength(spacing, 'e' if sample[-1] in 'eèé' or matches_e else 'o', design)
                            item = spacing['styles'][style]['left']['l']
                            original_width = round(item['original_widths'][0]*(1-design/1000)+item['original_widths'][1]*design/1000)
                            restored = (font['hmtx']['l'][0]-original_width)*(1-strength)
                            if matches_e:
                                restored += e_left_edge_difference(source, base, design)
                            elif base in item['clearance']:
                                extra = item['clearance'][base]
                                restored += round(extra[0]*(1-design/1000)+extra[1]*design/1000)*strength
                            restored += optical_addition(spacing, base)
                            assert abs(before.getlength(sample)+restored-after.getlength(sample)) <= 1.01, (relative, sample)
                            results['spacing_shaped_pairs'] += 1
                        if spacing.get('l_pair_tightening'):
                            original_width = round(item['original_widths'][0]*(1-design/1000)+item['original_widths'][1]*design/1000)
                            added = font['hmtx']['l'][0]-original_width
                            tightening = added*spacing['l_pair_tightening']
                            for sample in ('ll', 'lll'):
                                expected = len(sample)*added-(len(sample)-1)*tightening
                                assert abs(after.getlength(sample)-before.getlength(sample)-expected) <= 2.01, (relative, sample)
                                results['doubled_l_shaping_checks'] += 1
                for record in font['name'].names:
                    if record.nameID in FAMILY_NAME_IDS:
                        assert 'Lato26' in record.toUnicode(), (relative, record.nameID)
                glyph_set = font.getGlyphSet()
                if spacing and spacing.get('match_e_spacing_rights'):
                    right_edges = {}
                    matched = ['o']+(['c'] if 'c' in spacing['match_e_spacing_rights'] else [])
                    for right in ['e']+matched:
                        pen = BoundsPen(glyph_set)
                        glyph_set[right].draw(pen)
                        right_edges[right] = pen.bounds[0]
                    for name in spacing['styles'][style]['left']:
                        left = build.output_name(source, name, font)
                        for right in matched:
                            gap_difference = (pair_advance(font, left, 'e')+right_edges['e']
                                              -pair_advance(font, left, right)-right_edges[right])
                            assert abs(gap_difference) <= 1.1, (relative, name, right, gap_difference)
                            results[f'matched_e_{right}_gaps'] += 1
                for name in source.affected:
                    output = build.output_name(source, name, font)
                    pen = BoundsPen(glyph_set)
                    glyph_set[output].draw(pen)
                    assert pen.bounds and all(math.isfinite(x) for x in pen.bounds), name
                    assert font['hmtx'][output][0] == source.width(name, design), name
                rasterize(path, font.getGlyphOrder())
                results['static_fonts'] += 1
                results['glyph_rasterizations'] += len(font.getGlyphOrder())
        paths = [ROOT/'build'/directory/'Lato26.~VF/master_ttf_interpolatable'/
                 f'Lato26-{weight}{suffix}.ttf' for weight in ('Hairline', 'Black')]
        a, b = [TTFont(p, checkChecksums=2) for p in paths]
        assert a.getGlyphOrder() == b.getGlyphOrder()
        for name in a.getGlyphOrder():
            ga, gb = a['glyf'][name], b['glyf'][name]
            assert ga.isComposite() == gb.isComposite(), name
            if ga.isComposite():
                assert [c.glyphName for c in ga.components] == [c.glyphName for c in gb.components], name
            elif ga.numberOfContours:
                assert ga.endPtsOfContours == gb.endPtsOfContours, name
                assert ga.flags == gb.flags, name
        for path, font in zip(paths, (a, b)):
            rasterize(path, font.getGlyphOrder())
            results['glyph_rasterizations'] += len(font.getGlyphOrder())
        results['interpolatable_masters'] += 2
        print(style, 'static exports and every master glyph passed', flush=True)
    check_regular(args.baseline_dir)
    results['regular_a_e_match_reference_exactly'] = True
    for label, style in (('Light', 'Upr'), ('LightItalic', 'Ita')):
        relative = Path('Carlito26')/f'Carlito26-{label}.ttf'
        font = TTFont(ROOT/'build'/relative, checkChecksums=2)
        if args.baseline_dir:
            old = TTFont(args.baseline_dir/original_path(relative))
            changed = set(build.Source(style).affected)
            compare_unchanged(font, old, changed)
            assert all(font['hmtx'][n][0] == w for n, (w, _) in old['hmtx'].metrics.items())
        rasterize(ROOT/'build'/relative, font.getGlyphOrder())
        for record in font['name'].names:
            if record.nameID in FAMILY_NAME_IDS:
                assert 'Carlito26' in record.toUnicode(), (relative, record.nameID)
        results['glyph_rasterizations'] += len(font.getGlyphOrder())
        results['carlito_fonts'] += 1
    results['status'] = 'passed'
    if args.report:
        args.report.write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
