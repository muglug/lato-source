#!/usr/bin/env python3
"""Restore l bowl allowance in sources and exports without rebuilding outlines.

The Fira l/I comparison informs the shape categories, not absolute spacing.
The four design stops match the editable Glyphs masters. Run once to migrate
the VFJ kerning; --refresh-only reapplies the recorded policy to built fonts.
"""
import argparse
import copy
import importlib
import json
import shutil
import zipfile
from pathlib import Path

import openstep_plist
from fontTools.ttLib import TTFont

from lowercase_kerning import (CONFIG, _base_correction, apply_spacing,
                              correction, pair_advance)

build = importlib.import_module('07_build_revised_lato')
refine = importlib.import_module('10_refine_ae_and_l_spacing')
ROOT = build.ROOT
DESIGNS = (0, 540, 780, 1000)
# Maximum restoration, native 2000 UPM. Cap at the original compensation
# before the existing a/w/y breathing-room additions. Calculate the cap at
# masters, then interpolate the additions, just as the Glyphs sources do.
BUDGETS = {
    'Upr': {'round': (90, 70, 30, 20), 'diagonal': (100, 90, 70, 60)},
    'Ita': {'round': (75, 55, 15, 10), 'diagonal': (80, 65, 30, 20),
            'y': (40, 25, 10, 5)},
}


def make_policy(old):
    config = copy.deepcopy(old)
    policy = {'description': 'Restore part of the l advance cancelled by pair kerning; preserve vertical pairs, ll, and fl ligatures.',
              'designs': list(DESIGNS), 'budgets': BUDGETS, 'lefts': {}, 'additions': {}}
    for style, spec in old['styles'].items():
        source = build.Source(style)
        policy['lefts'][style] = [n for n in spec['left'] if n.startswith('l')]
        additions = policy['additions'][style] = {}
        for right in spec['right']:
            if right in old['l_rights']:
                continue
            if right in old.get('e_rights', []) or right in old['match_e_spacing_rights']:
                base = 'e'
            else:
                base = next((b for b in ('schwa', 'eopen', 'ereversed', 'eturned', 'eth', 'a', 'd', 'g', 'q', 's', 'v', 'w', 'x', 'y')
                             if right.startswith(b)), None)
            if base is None:
                raise ValueError((style, right))
            category = 'diagonal' if base in ('v', 'w', 'x', 'y') else 'round'
            if style == 'Ita' and base == 'y':
                category = 'y'
            additions[right] = [[design, min(budget, max(0, -_base_correction(source, 'l', base, design, old)))]
                                for design, budget in zip(DESIGNS, BUDGETS[style][category])]
    config['bowl_allowance'] = policy
    return config


def migrate_sources(old, config):
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        path = ROOT/f'sources/Lato3{style}2M.vfj'
        text = path.read_text()
        data = json.loads(text)['font']
        for wrapped in data['masters']:
            master = wrapped['fontMaster']
            design = 1000 if master['name'].startswith('Black') else 0
            kerning = master['kerning']; before = copy.deepcopy(kerning)
            for left in config['bowl_allowance']['lefts'][style]:
                for right in config['bowl_allowance']['additions'][style]:
                    delta = correction(source, left, right, design, config)-correction(source, left, right, design, old)
                    if delta:
                        value = refine.effective(before['pairs'], before['kerningClasses'], left, right)
                        kerning['pairs'].setdefault(left, {})[right] = str(value+delta)
            text = refine.patch_json_block(text, before, kerning, 10)
        path.write_text(text)
    CONFIG.write_text(json.dumps(config, indent=2)+'\n')


def update_static_glyphs():
    # Replace kerning only: preserve the authored a/e quadratics and all hints.
    path = build.REGULAR
    text = path.read_text(); parsed = openstep_plist.loads(text)
    font = TTFont(path.with_suffix('.ttf'))
    source = build.Source('Upr')
    spec = json.loads(CONFIG.read_text())['styles']['Upr']
    kerning = copy.deepcopy(parsed['kerningLTR'])
    pairs = next(iter(kerning.values()))
    for name in spec['left']:
        left = build.output_name(source, name, font)
        for members in spec['right'].values():
            for name in members:
                right = build.output_name(source, name, font)
                pairs.setdefault(left, {})[right] = pair_advance(font, left, right)
    start = text.index('kerningLTR = {')+len('kerningLTR = ')
    depth = 0
    for end in range(start, len(text)):
        if text[end] == '{': depth += 1
        elif text[end] == '}':
            depth -= 1
            if not depth: break
    updated = text[:start]+openstep_plist.dumps(kerning, indent=0, sort_keys=False)+text[end+1:]
    check = openstep_plist.loads(updated)
    assert check['glyphs'] == parsed['glyphs']
    path.write_text(updated)


def refresh_fonts(config):
    sources = {s: build.Source(s) for s in ('Upr', 'Ita')}
    for filename in config['fonts']:
        path = ROOT/filename
        style = 'Ita' if 'Lato3Ita2M' in filename else 'Upr'
        label = path.stem.removeprefix('Lato26-').removesuffix('Italic') or 'Regular'
        font = TTFont(path, recalcTimestamp=False, recalcBBoxes=False)
        before = {tag: font.getTableData(tag) for tag in font.keys() if tag not in ('GlyphOrder', 'GPOS', 'head')}
        head = font['head'].__dict__.copy()
        apply_spacing(font, path, sources[style], build.WEIGHTS[label], build.output_name)
        font.save(path)
        current = TTFont(path)
        assert all(current.getTableData(tag) == data for tag, data in before.items()), filename
        for key, value in head.items():
            if key != 'checkSumAdjustment': assert getattr(current['head'], key) == value, (filename, key)
        print(path.name, 'layout refreshed; every other table preserved', flush=True)
    update_static_glyphs()


def package():
    path = ROOT/'build/Lato26-Desktop.zip'
    with zipfile.ZipFile(path) as old:
        entries = [(item, old.read(item.filename)) for item in old.infolist()]
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for item, data in entries:
            name = Path(item.filename)
            if item.filename == 'README.txt':
                data = (ROOT/'sources/data/desktop-readme.txt').read_bytes()
                extracted = ROOT/'build/Lato26-Desktop/README.txt'
                if extracted.exists(): extracted.write_bytes(data)
            if name.suffix in ('.ttf', '.otf'):
                if name.parts[0] == 'Lato26':
                    style = 'Ita' if 'Italic' in name.name else 'Upr'
                    source = ROOT/f'build/Lato3{style}2M/ds-ufo/masters'/name.name
                else:
                    source = ROOT/'build'/name
                data = source.read_bytes()
                extracted = ROOT/'build/Lato26-Desktop'/name
                if extracted.exists(): shutil.copy2(source, extracted)
            output.writestr(item, data)
    with zipfile.ZipFile(path) as check:
        assert check.testzip() is None
    print('Desktop archive and existing extracted copies refreshed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    if not args.refresh_only:
        if 'bowl_allowance' in config:
            raise SystemExit('Already applied; use --refresh-only to update built fonts.')
        updated = make_policy(config)
        migrate_sources(config, updated)
        config = updated
    assert 'bowl_allowance' in config
    refresh_fonts(config)
    package()


if __name__ == '__main__':
    main()
