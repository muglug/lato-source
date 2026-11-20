#!/usr/bin/env python3
"""Pin Glyphs exports and variable line boxes to published Lato 2.015 metrics.

Only hhea and OS/2 are patched in existing variable binaries; all other
tables remain byte-identical apart from head.checkSumAdjustment.
"""
import argparse
import copy
import hashlib
import importlib
import json
import re
import shutil
from pathlib import Path

import openstep_plist
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from glyphsLib import GSFont, to_designspace
from lato_vertical_metrics import (FIELDS, GLYPHS_PARAMETERS, metrics,
                                   assert_published_metrics, assert_designspace_metrics)

ROOT = Path(__file__).resolve().parents[1]
balanced_end = importlib.import_module('27_propagate_smaller_l').balanced_end


def backup(path, snapshot):
    saved = snapshot / path.relative_to(ROOT)
    if not saved.exists():
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)


def patch_source(path):
    text = path.read_text()
    original = openstep_plist.loads(text, use_numbers=True)
    expected = copy.deepcopy(original)
    parameters = expected.setdefault('customParameters', [])
    for name, value in GLYPHS_PARAMETERS.items():
        existing = next((p for p in parameters if p['name'] == name), None)
        if existing is None:
            parameters.append({'name': name, 'value': value})
        else:
            existing['value'] = value
    replacement = openstep_plist.dumps(parameters, indent=0, sort_keys=False)
    if 'customParameters' in original:
        start = re.search(r'^customParameters = \(', text, re.M).end() - 1
        text = text[:start] + replacement + text[balanced_end(text, start):]
    else:
        start = text.rfind('}')
        text = text[:start] + 'customParameters = ' + replacement + ';\n' + text[start:]
    assert openstep_plist.loads(text, use_numbers=True) == expected
    path.write_text(text)


def patch_font(path):
    before = TTFont(path, recalcTimestamp=False)
    previous = metrics(before)
    original_tables = {tag: before.reader[tag] for tag in before.reader.keys()}
    # Keep untouched table bytes instead of recompiling glyphs/layout/variation data.
    raw = TTFont(recalcTimestamp=False)
    raw.sfntVersion = before.sfntVersion
    for tag in original_tables:
        table = DefaultTable(tag)
        table.data = original_tables[tag]
        raw[tag] = table
    for tag in ('hhea', 'OS/2'):
        changed = copy.deepcopy(before[tag])
        for table, field, value in FIELDS.values():
            if table == tag:
                setattr(changed, field, value)
        if tag == 'OS/2':
            changed.fsSelection &= ~0x80
        raw[tag].data = changed.compile(before)
    raw.save(path)
    after = TTFont(path, recalcTimestamp=False)
    assert_published_metrics(after)
    for tag in original_tables:
        if tag in ('hhea', 'OS/2'):
            continue
        a, b = original_tables[tag], after.reader[tag]
        if tag == 'head':
            a, b = a[:8] + a[12:], b[:8] + b[12:]
        assert a == b, (path.name, tag)
    return {'path': str(path.relative_to(ROOT)), 'before': previous, 'after': metrics(after),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'only_changed_tables': ['hhea', 'OS/2', 'head.checkSumAdjustment']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--reference-dir', type=Path, default=Path('/Library/Fonts'))
    args = ap.parse_args()
    build = importlib.import_module('07_build_revised_lato')
    report = {'status': 'running', 'reference_version': '2.015', 'references': [],
              'static_fonts_checked': 0, 'sources': [], 'variable_fonts': []}
    for style in ('Upr', 'Ita'):
        for label in build.WEIGHTS:
            label = label if style == 'Upr' else ('Italic' if label == 'Regular' else label + 'Italic')
            reference = args.reference_dir / f'Lato-{label}.ttf'
            font = TTFont(reference)
            assert '2.015' in font['name'].getDebugName(5)
            assert_published_metrics(font)
            report['references'].append({'file': reference.name, 'sha256': hashlib.sha256(reference.read_bytes()).hexdigest()})
            for ext in ('ttf', 'otf'):
                assert_published_metrics(TTFont(ROOT / f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{label}.{ext}'))
                report['static_fonts_checked'] += 1
    sources = [ROOT / f'sources/Lato26-{s}.glyphs' for s in ('Upright', 'Italic')] + [build.REGULAR]
    for path in sources:
        backup(path, args.snapshot)
        patch_source(path)
        if path != build.REGULAR:
            designspace = to_designspace(GSFont(path))
            assert_designspace_metrics(designspace)
        report['sources'].append(str(path.relative_to(ROOT)))
    for path in sorted((ROOT / 'build/Lato26-Variable').glob('*.ttf')):
        backup(path, args.snapshot)
        report['variable_fonts'].append(patch_font(path))
    info = ROOT / 'build/Lato26-Variable/build-info.json'
    backup(info, args.snapshot)
    records = json.loads(info.read_text())
    for item in records:
        item['vertical_metrics'] = metrics(TTFont(ROOT / item['path']))
    info.write_text(json.dumps(records, indent=2) + '\n')
    archive = ROOT / 'build/Lato26-Variable.zip'
    backup(archive, args.snapshot)
    importlib.import_module('32_build_variable_fonts').package(archive.with_suffix(''))
    report['status'] = 'passed'
    (ROOT / 'build/proofs/vertical-metrics-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Published metrics verified in all 36 static exports and both variable fonts; Glyphs/UFO export settings pinned.', flush=True)


if __name__ == '__main__':
    main()
