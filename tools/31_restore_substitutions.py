#!/usr/bin/env python3
"""Repair missing GSUB tables and verify every other font table is preserved."""
import argparse
import copy
import hashlib
import importlib
import json
import re
import shutil
from io import StringIO
from pathlib import Path

import openstep_plist
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib import ast
from fontTools.feaLib.parser import Parser
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from opentype_substitutions import restore_substitutions

build = importlib.import_module('07_build_revised_lato')
merge = importlib.import_module('27_propagate_smaller_l')
ROOT = build.ROOT


def static_glyphs(snapshot):
    path = build.REGULAR
    text = path.read_text()
    data = openstep_plist.loads(text, use_numbers=True)
    if any(f['tag'] == 'liga' for f in data['features']):
        return
    backup = snapshot / path.relative_to(ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    source = build.Source('Upr')
    ttf = TTFont(path.with_suffix('.ttf'))
    mapping = {name: build.output_name(source, name, ttf) for name in source.glyphs}
    native = json.loads((ROOT / 'sources/Lato3Upr2M.vfj').read_text())['font']
    prefix = native['openTypeFeatures'][0]['feature']
    classes = '\n'.join('@' + c['name'] + ' = [' + ' '.join(c['names']) + '];'
                        for c in native['classes']
                        if not re.search(r'@' + re.escape(c['name']) + r'\s*=', prefix))
    tree = Parser(StringIO(classes + '\n' + '\n'.join(f['feature'] for f in native['openTypeFeatures'])), glyphNames=source.glyphs).parse()
    visited = set()
    def rename(node):
        if id(node) in visited:
            return
        visited.add(id(node))
        if isinstance(node, ast.GlyphName):
            node.glyph = mapping[node.glyph]
        elif isinstance(node, ast.GlyphClass):
            node.glyphs = [mapping[g] if isinstance(g, str) else g for g in node.glyphs]
            node.original = []
            node.curr = 0
            for g in node.glyphs:
                rename(g)
        elif isinstance(node, ast.Element):
            if isinstance(node, ast.LigatureSubstStatement):
                node.replacement = mapping[node.replacement]
            for value in vars(node).values():
                rename(value)
        elif isinstance(node, (tuple, list)):
            for value in node:
                rename(value)
        elif isinstance(node, dict):
            for value in node.values():
                rename(value)
    rename(tree)
    new_prefix = {'name': 'Restored source substitutions', 'code': '\n'.join(s.asFea() for s in tree.statements if not isinstance(s, ast.FeatureBlock))}
    features = [{'tag': s.name, 'code': '\n'.join(x.asFea() for x in s.statements)}
                for s in tree.statements if isinstance(s, ast.FeatureBlock)]
    check = TTFont()
    check.setGlyphOrder(ttf.getGlyphOrder())
    addOpenTypeFeaturesFromString(check, new_prefix['code'] + '\n' + '\n'.join(
        'feature ' + f['tag'] + ' {\n' + f['code'] + '\n} ' + f['tag'] + ';' for f in features))
    expected = copy.deepcopy(data)
    expected['features'] += features
    expected.setdefault('featurePrefixes', []).append(new_prefix)
    start = re.search(r'^features = \(', text, re.M).end() - 1
    end = merge.balanced_end(text, start)
    additions = openstep_plist.dumps(features, indent=0, sort_keys=False).strip()[1:-1]
    text = text[:end-1] + additions + text[end-1:]
    assert 'featurePrefixes' not in data
    text = text[:text.rfind('}')] + 'featurePrefixes = ' + openstep_plist.dumps(expected['featurePrefixes'], indent=0, sort_keys=False) + ';\n' + text[text.rfind('}'):]
    assert openstep_plist.loads(text, use_numbers=True) == expected
    path.write_text(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot', type=Path, required=True)
    args = ap.parse_args()
    report = {'status': 'running', 'fonts': [], 'changed': 0, 'already_working': 0}
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        folder = ROOT / f'build/Lato3{style}2M/ds-ufo/masters'
        paths = sorted(folder.glob('Lato26-*.ttf')) + sorted(folder.glob('Lato26-*.otf'))
        paths += sorted((folder / 'Lato26.~VF/master_ttf_interpolatable').glob('*.ttf'))
        for path in paths:
            before = args.snapshot / path.relative_to(ROOT)
            before.parent.mkdir(parents=True, exist_ok=True)
            if not before.exists():
                shutil.copy2(path, before)
            font = TTFont(before, recalcTimestamp=False)
            changed = restore_substitutions(font, source, build.output_name)
            if changed:
                # Some legacy master cmaps normalize during a TTFont save.
                # Copy raw tables so this repair changes only GSUB/checksum.
                raw = TTFont(recalcBBoxes=False, recalcTimestamp=False)
                raw.sfntVersion = font.sfntVersion
                for tag in set(font.reader.keys()) | {'GSUB'}:
                    table = DefaultTable(tag)
                    table.data = font.getTableData('GSUB') if tag == 'GSUB' else font.reader[tag]
                    raw[tag] = table
                raw.save(path)
            old, new = TTFont(before), TTFont(path)
            for tag in set(old.keys()) - {'GlyphOrder', 'GSUB', 'head'}:
                assert old.getTableData(tag) == new.getTableData(tag), (path, tag)
            for key, value in vars(old['head']).items():
                if key != 'checkSumAdjustment':
                    assert vars(new['head'])[key] == value, (path, 'head', key)
            report['changed' if changed else 'already_working'] += 1
            report['fonts'].append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'features': sorted({r.FeatureTag for r in new['GSUB'].table.FeatureList.FeatureRecord})})
            print(path.name, 'substitutions restored' if changed else 'existing substitutions retained', flush=True)
    static_glyphs(args.snapshot)
    report['status'] = 'passed'
    report['all_other_tables_preserved'] = True
    (ROOT / 'build/proofs/substitution-validation.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
