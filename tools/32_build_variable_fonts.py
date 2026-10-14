#!/usr/bin/env python3
"""Export upright/italic weight-variable fonts from the current Glyphs sources.

The static desktop fonts retain their native TrueType hints. Variable fonts
are unhinted: static point-index instructions cannot be copied to newly
converted variable outlines.
"""
import argparse
import copy
import importlib
import json
import logging
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from glyphsLib import GSFont, to_designspace
from fontmake.font_project import FontProject
from lowercase_kerning import CONFIG, pair_advance

build = importlib.import_module('07_build_revised_lato')
export = importlib.import_module('11_export_editable_glyphs')
ROOT = build.ROOT
FALLBACKS = ('_zigzag', '_zigzag.case', 'zigzagabovecomb', 'zigzagabovecomb.case')


def normalize_names(font, italic):
    family = 'Lato26 Variable'
    style = 'Italic' if italic else 'Regular'
    postscript = 'Lato26Variable-' + style
    values = {1: family, 2: style, 4: family + ' ' + style, 6: postscript,
              16: family, 17: style, 25: 'Lato26VariableItalic' if italic else 'Lato26Variable'}
    for name_id, value in values.items():
        for platform, encoding, language in ((3, 1, 0x409), (1, 0, 0)):
            font['name'].setName(value, name_id, platform, encoding, language)


def preserve_pair_gaps(designspace, variable, source):
    """Compensate for conversion/sidebearing differences at the four masters."""
    spec = json.loads(CONFIG.read_text())['styles'][source.style]
    reverse_weights = {d: (100 + i * 100, name) for i, (name, d) in enumerate(build.WEIGHTS.items())}
    changes = []
    for descriptor in designspace.sources:
        if descriptor.layerName:
            # Sparse brace layers contain only the restored ligature outlines.
            continue
        weight, label = reverse_weights[int(descriptor.location[designspace.axes[0].name])]
        italic = 'Italic' if source.style == 'Ita' else ''
        label = 'Italic' if italic and label == 'Regular' else label + italic
        static = TTFont(ROOT / f'build/Lato3{source.style}2M/ds-ufo/masters/Lato26-{label}.ttf')
        old_set = static.getGlyphSet()
        new_set = variable.getGlyphSet(location={'wght': weight})
        names = set(spec['left']) | set(spec['right'])
        old_names = {n: build.output_name(source, n, static) for n in names}
        def edges(glyph_set, name):
            pen = BoundsPen(glyph_set)
            glyph_set[name].draw(pen)
            return pen.bounds[0], pen.bounds[2]
        old_bounds = {n: edges(old_set, old_names[n]) for n in names}
        new_bounds = {n: edges(new_set, n) for n in names}
        for left in spec['left']:
            for right in spec['right']:
                a, z = old_names[left], old_names[right]
                old_gap = static['hmtx'][a][0] + pair_advance(static, a, z) + old_bounds[right][0] - old_bounds[left][1]
                kern = otRound(old_gap - new_set[left].width - new_bounds[right][0] + new_bounds[left][1])
                previous = descriptor.font.kerning.get((left, right), 0)
                if kern != previous:
                    changes.append(kern - previous)
                descriptor.font.kerning[left, right] = kern
    return {'adjusted_master_pairs': len(changes), 'maximum_adjustment': max(map(abs, changes), default=0)}


def export_variable(style, directory):
    suffix = 'Italic' if style == 'Ita' else 'Upright'
    path = ROOT / f'sources/Lato26-{suffix}.glyphs'
    font = GSFont(path)
    font.familyName = 'Lato26 Variable'
    regular = next(m for m in font.masters if m.axes[0] == 540)
    font.customParameters['Variable Font Origin'] = regular.id
    source = build.Source(style)
    folder = ROOT / f'build/Lato3{style}2M/ds-ufo/masters/Lato26.~VF/master_ttf_interpolatable'
    italic = 'Italic' if style == 'Ita' else ''
    masters = [TTFont(folder / f'Lato26-{w}{italic}.ttf') for w in ('Hairline', 'Black')]
    for name in FALLBACKS:
        for master in font.masters:
            layer = font.glyphs[name].layers[master.id]
            layer.shapes = []
            export.fallback_layer(layer, name, master.axes[0], source, masters)
    designspace = to_designspace(font)
    axis = designspace.axes[0]
    axis.minimum, axis.default, axis.maximum = 100, 400, 900
    axis.map = [(100 + i * 100, design) for i, design in enumerate(build.WEIGHTS.values())]
    # The source custom weight classes describe the intended CSS weight axis.
    for instance, (name, design) in zip(designspace.instances, build.WEIGHTS.items()):
        assert instance.location[axis.name] == design, (instance.name, design)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f'Lato26-Variable{italic}.ttf'
    def compile_font():
        # Keep authored contour topology: the default per-master open-corner
        # filter removes different zigzag nodes at different weights.
        FontProject().run_from_designspace(copy.deepcopy(designspace), output=['variable'],
                                          output_path=str(output), use_production_names=False,
                                          filters=[])
    compile_font()
    spacing = preserve_pair_gaps(designspace, TTFont(output), source)
    compile_font()
    result = TTFont(output, recalcTimestamp=False)
    normalize_names(result, bool(italic))
    assert len(result['fvar'].axes) == 1
    assert [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in result['fvar'].axes] == [('wght', 100, 400, 900)]
    assert len(result['fvar'].instances) == 9
    result.save(output)
    print(output, flush=True)
    return {'path': str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
            'source': str(path.relative_to(ROOT)), 'compatible_fallbacks': list(FALLBACKS),
            'hinting': 'unhinted', 'axis': {'wght': [100, 400, 900]}, 'spacing': spacing}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--style', choices=['Upr', 'Ita', 'all'], default='all')
    ap.add_argument('--output-dir', type=Path, default=ROOT / 'build/Lato26-Variable')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    records = [export_variable(style, args.output_dir) for style in
               (('Upr', 'Ita') if args.style == 'all' else (args.style,))]
    (args.output_dir / 'build-info.json').write_text(json.dumps(records, indent=2) + '\n')
    if args.style == 'all':
        package(args.output_dir)


def package(directory):
    path = directory.with_suffix('.zip')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('Lato26-Variable.ttf', 'Lato26-VariableItalic.ttf'):
            archive.write(directory / name, name)
        archive.write(ROOT / 'sources/data/variable-readme.txt', 'README.txt')
        archive.write(ROOT / 'LICENSE.txt', 'LICENSE.txt')
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
    print(path, flush=True)


if __name__ == '__main__':
    main()
