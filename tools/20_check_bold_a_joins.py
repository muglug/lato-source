#!/usr/bin/env python3
"""Check contour connectivity and unchanged bowl hints across all Bold a forms."""
import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from bold_a_hint_controls import bold_a_matches, join_program
from lcd_font_proofs import RasterFace
from truetype_hinting import assert_same_outlines, bytecode, hint_font

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path('Lato3Upr2M/ds-ufo/masters/Lato26-Bold.ttf')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-build', required=True, type=Path)
    args = parser.parse_args()
    before_path, after_path = args.before_build/RELATIVE, ROOT/'build'/RELATIVE
    before, after = TTFont(before_path), TTFont(after_path, recalcTimestamp=False)
    assert_same_outlines(before, after)
    for tag in ('fpgm', 'prep', 'cvt ', 'gasp', 'hmtx', 'hhea', 'name', 'cmap', 'GPOS', 'GSUB', 'GDEF', 'OS/2'):
        assert before.getTableData(tag) == after.getTableData(tag), tag
    matches = dict(bold_a_matches(after))
    changed = {name for name in after.getGlyphOrder()
               if bytecode(before['glyf'][name]) != bytecode(after['glyf'][name])}
    assert changed == set(matches), changed.symmetric_difference(matches)
    for name, start in matches.items():
        assert bytecode(after['glyf'][name]) == bytecode(before['glyf'][name]) + join_program(start)
    # These exports decompose the a forms. Fail if a future export introduces
    # composite parents that need their own final-coordinate checks.
    parents = [name for name in after.getGlyphOrder() if after['glyf'][name].isComposite()
               and any(c.glyphName in matches for c in after['glyf'][name].components)]
    assert not parents, ('extend join coverage to composite parents', parents)
    faces = [RasterFace(p) for p in (before_path, after_path)]
    sizes = sorted(set(range(6, 202)) | {v/4 for v in range(32, 201)} | {256})
    report = {'font': str(after_path.relative_to(ROOT)),
              'sha256': hashlib.sha256(after_path.read_bytes()).hexdigest(),
              'forms': list(matches), 'sizes_ppem': sizes,
              'targets': ['grayscale', 'monochrome', 'LCD'], 'glyph_cases': 0,
              'minimum_join_overlap_px': float('inf'), 'samples': []}
    for target in (0, 2, 3):  # FT_RENDER_MODE_NORMAL, MONO, LCD
        for size in sizes:
            for name, start in matches.items():
                old, new = [face.hinted_points(name, size, target) for face in faces]
                assert len(old) == len(new)
                for index, (a, b) in enumerate(zip(old, new)):
                    assert a[0] == b[0], (name, size, target, index, 'x moved')
                    if index not in (start+29, start+30):
                        assert a == b, (name, size, target, index, 'bowl, curve or accent moved')
                overlaps = []
                for lower, upper in ((start+29, start+2), (start+30, start+1)):
                    assert new[lower][1] >= old[lower][1]
                    overlap = new[lower][1] - new[upper][1]
                    assert overlap >= 0, (name, size, target, 'open join', overlap)
                    # Two independently rounded 26.6 original coordinates.
                    assert overlap >= 16*size/after['head'].unitsPerEm - 1/32
                    overlaps.append(overlap)
                report['minimum_join_overlap_px'] = min(report['minimum_join_overlap_px'], *overlaps)
                thickness = new[start+57][1] - new[start+58][1]
                assert thickness == old[start+57][1] - old[start+58][1]
                report['glyph_cases'] += 1
                if name == 'a' and target == 3 and size in (12, 14, 16, 18, 20, 24):
                    report['samples'].append({'ppem': size, 'join_overlap_px': min(overlaps),
                                              'bowl_top_thickness_px': thickness})
    repeat = TTFont(after_path, recalcTimestamp=False)
    hint_font(repeat)
    for tag in ('glyf', 'fpgm', 'prep', 'cvt ', 'gasp', 'maxp', 'TTFA'):
        assert after.getTableData(tag) == repeat.getTableData(tag), ('non-idempotent', tag)
    report.update(status='passed', form_count=len(matches),
                  bowl_and_accent_coordinates_unchanged=True, hint_pass_idempotent=True)
    path = ROOT/'build/proofs/bold-a-join-validation.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('forms', 'sizes_ppem')}, indent=2))
    print(path)


if __name__ == '__main__':
    main()
