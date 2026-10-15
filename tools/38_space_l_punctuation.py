#!/usr/bin/env python3
"""Copy Fira's positive l/punctuation kerns; preserve outlines and letter pairs.

One-time migration. A before snapshot is required for validation and proofs.
Subsequent normal static/variable builds use punctuation_kerning.py.
"""
import argparse
import copy
import hashlib
import importlib
import json
import re
from pathlib import Path

import openstep_plist
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from lowercase_kerning import CONFIG, apply_spacing, pair_advance
from punctuation_kerning import adjustment, append_variable_adjustments

build = importlib.import_module('07_build_revised_lato')
refine = importlib.import_module('10_refine_ae_and_l_spacing')
balanced_end = importlib.import_module('27_propagate_smaller_l').balanced_end
ROOT = build.ROOT
REFERENCES = ('Thin', 'UltraLight', 'Light', 'Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold', 'Heavy')
RIGHTS = {'period': '.', 'comma': ',', 'ellipsis': '\u2026', 'exclam': '!',
          'bracketright': ']', 'braceright': '}', 'quotesinglbase': '\u201a',
          'quotedblbase': '\u201e', 'colon': ':', 'semicolon': ';', 'questiongreek': '\u037e'}


def make_policy(config):
    policy = {'description': 'Positive Fira Sans l/punctuation kerning, scaled from 1000 to 2000 UPM. Existing Lato kerning is retained; fl ligatures are excluded.',
              'reference': json.loads((ROOT / '.cache/fira-sans-4.301/source.json').read_text()),
              'lefts': config['bowl_allowance']['lefts'],
              'rights': {n: 'colon' if n in ('colon', 'semicolon', 'questiongreek') else 'period' for n in RIGHTS},
              'curves': {'period': [], 'colon': []}, 'reference_fonts': []}
    for design, reference in zip(build.WEIGHTS.values(), REFERENCES):
        for style in ('Upr', 'Ita'):
            name = reference if style == 'Upr' else ('Italic' if reference == 'Regular' else reference + 'Italic')
            path = ROOT / f'.cache/fira-sans-4.301/FiraSans-{name}.ttf'
            font = TTFont(path)
            cmap = font.getBestCmap()
            values = {right: pair_advance(font, cmap[108], cmap[ord(char)]) * 2000 // font['head'].unitsPerEm
                      for right, char in RIGHTS.items()}
            for right, group in policy['rights'].items():
                assert values[right] == values[group]
            for group in policy['curves']:
                if style == 'Upr':
                    policy['curves'][group].append([design, values[group]])
                else:
                    assert values[group] == policy['curves'][group][-1][1]
            policy['reference_fonts'].append({'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return policy


def glyphs_effective(pairs, glyphs, left, right):
    lc = '@MMK_L_' + glyphs[left].get('kernRight', '')
    rc = '@MMK_R_' + glyphs[right].get('kernLeft', '')
    for a, b in ((left, right), (left, rc), (lc, right), (lc, rc)):
        if b in pairs.get(a, {}):
            return pairs[a][b]
    return 0


def patch_glyphs(path, style, policy, static=False):
    text = path.read_text()
    before = openstep_plist.loads(text, use_numbers=True)
    expected = copy.deepcopy(before)
    glyphs = {g['glyphname']: g for g in expected['glyphs']}
    if style == 'Upr' and not static:
        black = next(m['id'] for m in expected['fontMaster'] if m['axesValues'] == [1000])
        layer = next(l for l in glyphs['l']['layers'] if l['layerId'] == black)
        assert layer['width'] == 607, layer['width']
        layer['width'] = 580.7
        match = re.search(r'^glyphname = l;$', text, re.M)
        start = text.rfind('{', 0, match.start())
        end = balanced_end(text, start)
        block = text[start:end]
        assert block.count('width = 607;') == 1
        text = text[:start] + block.replace('width = 607;', 'width = 580.7;') + text[end:]
    source = build.Source(style)
    font = TTFont(path.with_suffix('.ttf')) if static else None
    for master in expected['fontMaster']:
        design = 540 if static else master['axesValues'][0]
        pairs = expected['kerningLTR'][master['id']]
        original = before['kerningLTR'][master['id']]
        for left in policy['lefts'][style]:
            for right in policy['rights']:
                if static:
                    a, b = (build.output_name(source, n, font) for n in (left, right))
                    value = pair_advance(font, a, b)
                else:
                    a, b = left, right
                    value = glyphs_effective(original, glyphs, a, b) + adjustment(policy, right, design)
                pairs.setdefault(a, {})[b] = value
    start = re.search(r'^kerningLTR = \{', text, re.M).end() - 1
    text = text[:start] + openstep_plist.dumps(expected['kerningLTR'], indent=0, sort_keys=False) + text[balanced_end(text, start):]
    assert openstep_plist.loads(text, use_numbers=True) == expected
    path.write_text(text)


def patch_vfj(style, policy):
    path = ROOT / f'sources/Lato3{style}2M.vfj'
    text = path.read_text()
    parsed = json.loads(text)
    expected = copy.deepcopy(parsed)
    for wrapped in expected['font']['masters']:
        master = wrapped['fontMaster']
        design = 1000 if master['name'].startswith('Black') else 0
        kerning = master['kerning']
        original = copy.deepcopy(kerning)
        for left in policy['lefts'][style]:
            for right in policy['rights']:
                value = refine.effective(original['pairs'], original['kerningClasses'], left, right)
                kerning['pairs'].setdefault(left, {})[right] = str(value + adjustment(policy, right, design))
        text = refine.patch_json_block(text, original, kerning, 10)
    assert json.loads(text) == expected
    path.write_text(text)


def save_layout_only(font, path, tables):
    """Preserve the bytecode, all outlines/metrics and other raw SFNT tables."""
    before = {tag: font.reader[tag] for tag in font.reader.keys()}
    changed = {tag: font.getTableData(tag) for tag in tables}
    raw = TTFont(recalcTimestamp=False)
    raw.sfntVersion = font.sfntVersion
    for tag, data in (before | changed).items():
        raw[tag] = DefaultTable(tag)
        raw[tag].data = changed.get(tag, data)
    raw.save(path)
    after = TTFont(path)
    for tag, data in before.items():
        if tag in tables:
            continue
        current = after.reader[tag]
        if tag == 'head':
            data, current = data[:8] + data[12:], current[:8] + current[12:]
        assert current == data, (path, tag)


def migrate(snapshot):
    config = json.loads(CONFIG.read_text())
    assert 'punctuation_allowance' not in config, 'Migration already applied; use normal build tools.'
    assert (snapshot / CONFIG.relative_to(ROOT)).exists(), 'Make a complete before snapshot first.'
    policy = make_policy(config)
    config['punctuation_allowance'] = policy
    CONFIG.write_text(json.dumps(config, indent=2) + '\n')
    for style, suffix in (('Upr', 'Upright'), ('Ita', 'Italic')):
        patch_glyphs(ROOT / f'sources/Lato26-{suffix}.glyphs', style, policy)
        patch_vfj(style, policy)
    sources = {s: build.Source(s) for s in ('Upr', 'Ita')}
    for name in config['fonts']:
        path = ROOT / name
        style = 'Ita' if 'Lato3Ita2M' in name else 'Upr'
        label = path.stem.removeprefix('Lato26-').removesuffix('Italic') or 'Regular'
        font = TTFont(path, recalcTimestamp=False, recalcBBoxes=False)
        apply_spacing(font, path, sources[style], build.WEIGHTS[label], build.output_name)
        save_layout_only(font, path, ['GPOS'])
    patch_glyphs(build.REGULAR, 'Upr', policy, static=True)
    for style, suffix in (('Upr', ''), ('Ita', 'Italic')):
        path = ROOT / f'build/Lato26-Variable/Lato26-Variable{suffix}.ttf'
        font = TTFont(path, recalcTimestamp=False)
        append_variable_adjustments(font, style, policy)
        save_layout_only(font, path, ['GPOS', 'GDEF'])
    info = ROOT / 'build/Lato26-Variable/build-info.json'
    records = json.loads(info.read_text())
    for record in records:
        record['punctuation_spacing'] = 'Fira Sans positive l/punctuation kerns, scaled to 2000 UPM at all nine named weights; other pairs and outlines preserved.'
    info.write_text(json.dumps(records, indent=2) + '\n')
    importlib.import_module('23_restore_l_bowl_spacing').package()
    importlib.import_module('32_build_variable_fonts').package(ROOT / 'build/Lato26-Variable')
    print('Punctuation policy applied to sources, 40 static/master fonts and both variable fonts.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    migrate(parser.parse_args().snapshot)
