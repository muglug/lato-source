#!/usr/bin/env python3
"""Reproduce all 18 Lato 2.015 hint sets and measure the rebuilt fonts at 16 px."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from fontTools.ttLib import TTFont
from lcd_font_proofs import RasterFace
from truetype_hinting import run_engine, bytecode, engine_version, OPTIONS

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ('Hairline', 'Thin', 'Light', 'Regular', 'Medium', 'Semibold', 'Bold', 'Heavy', 'Black')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dir', type=Path, required=True)
    args = parser.parse_args()
    report = {'engine': engine_version(), 'options': OPTIONS, 'fonts': []}
    with tempfile.TemporaryDirectory(prefix='lato-2015-reference-') as temporary:
        for italic in (False, True):
            for weight in WEIGHTS:
                suffix = 'Italic' if italic and weight == 'Regular' else weight + ('Italic' if italic else '')
                path = args.reference_dir / f'Lato-{suffix}.ttf'
                reference = TTFont(path, recalcTimestamp=False)
                version = reference['name'].getDebugName(5)
                assert version.startswith('Version 2.015;'), (path, version)
                regenerated = Path(temporary)/path.name
                run_engine(path, regenerated)
                actual = TTFont(regenerated)
                assert reference.getGlyphOrder() == actual.getGlyphOrder()
                for tag in ('fpgm', 'prep', 'cvt '):
                    assert reference.getTableData(tag) == actual.getTableData(tag), (path, tag)
                for name in reference.getGlyphOrder():
                    assert bytecode(reference['glyf'][name]) == bytecode(actual['glyf'][name]), (path, name)
                current_path = ROOT/f'build/Lato3{"Ita" if italic else "Upr"}2M/ds-ufo/masters/Lato26-{suffix}.ttf'
                faces = [RasterFace(p) for p in (path, current_path)]
                measurements = {}
                for char in ('a', 'h', 'k', 'n', 'o', 'H'):
                    bounds = []
                    for face in faces:
                        ys = [y for _, y in face.hinted_points(char)]
                        bounds.append([min(ys), max(ys)])
                    measurements[char] = {'reference': bounds[0], 'current': bounds[1]}
                row = {'reference': str(path), 'reference_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'current': str(current_path.relative_to(ROOT)),
                       'current_sha256': hashlib.sha256(current_path.read_bytes()).hexdigest(),
                       'version': version, 'global_tables_reproduced': ['fpgm', 'prep', 'cvt '],
                       'glyph_programs_reproduced': len(reference.getGlyphOrder()),
                       'nonempty_programs_reproduced': sum(bool(bytecode(reference['glyf'][n])) for n in reference.getGlyphOrder()),
                       'bounds_16px': measurements}
                if not italic and weight == 'Bold':
                    coords = faces[1].hinted_points('a')
                    gap = coords[57][1] - coords[58][1]
                    assert 1 <= gap <= 1.5, ('Bold a bowl-top too thick or thin at 16 px', gap)
                    row['bowl_top_edge_separation_16px'] = gap
                report['fonts'].append(row)
                print(path.name, 'original hint programs reproduced exactly', flush=True)
    report.update(status='passed', reference_fonts=18)
    output = ROOT/'build/proofs/lato-2015-hint-validation.json'
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(output)


if __name__ == '__main__':
    main()
