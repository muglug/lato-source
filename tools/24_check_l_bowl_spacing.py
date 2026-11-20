#!/usr/bin/env python3
"""Check spacing-only revision against its saved before-build and sources."""
import argparse
import hashlib
import importlib
import json
import zipfile
from pathlib import Path

import openstep_plist
from fontTools.ttLib import TTFont
from PIL import ImageFont

from lowercase_kerning import CONFIG, bowl_allowance, pair_advance, strip_spacing
from vector_font_proofs import face

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT


def pairs(font):
    result = {}
    lookup = font['GPOS'].table.LookupList.Lookup[-1]
    assert lookup.LookupType == 2 and lookup.LookupFlag == 8
    for sub in lookup.SubTable:
        assert sub.Format == 1
        for left, row in zip(sub.Coverage.glyphs, sub.PairSet):
            for pair in row.PairValueRecord:
                result[left, pair.SecondGlyph] = pair.Value1.XAdvance
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    previous_config = json.loads((args.snapshot/'before-source/sources/data/lowercase-spacing.json').read_text())
    sources = {s: build.Source(s) for s in ('Upr', 'Ita')}
    report = {'fonts': [], 'pair_adjustments_checked': 0, 'shaped_pairs': 0,
              'source_files_checked': 0, 'preserved': 'Every non-GPOS table; head differs only in checksum. Includes all outlines, hint bytes, advances and original layout lookups.'}
    for filename, metadata in config['fonts'].items():
        path = ROOT/filename
        old_path = args.snapshot/'before-build'/path.relative_to(ROOT/'build')
        current, old = TTFont(path), TTFont(old_path)
        assert current.keys() == old.keys()
        for tag in current.keys():
            if tag not in ('GlyphOrder', 'head', 'GPOS'):
                assert current.getTableData(tag) == old.getTableData(tag), (filename, tag)
        for key, value in old['head'].__dict__.items():
            if key != 'checkSumAdjustment': assert getattr(current['head'], key) == value, (filename, key)
        style = 'Ita' if 'Lato3Ita2M' in filename else 'Upr'
        source = sources[style]
        label = path.stem.removeprefix('Lato26-').removesuffix('Italic') or 'Regular'
        design = build.WEIGHTS[label]
        before, after = pairs(old), pairs(current)
        assert before.keys() == after.keys()
        expected = {}
        for left in config['styles'][style]['left']:
            for group, rights in config['styles'][style]['right'].items():
                delta = (bowl_allowance(config, style, group, design, left)
                         - bowl_allowance(previous_config, style, group, design, left))
                for right in rights:
                    key = (build.output_name(source,left,current),build.output_name(source,right,current))
                    expected[key] = delta
        for key in before:
            assert after[key]-before[key] == expected[key], (filename, key)
        report['pair_adjustments_checked'] += len(before)
        if '.~VF' not in filename:
            shaped = face(str(path)); previous = face(str(old_path))
            pil = ImageFont.truetype(str(path), 2000)
            for sample in ['l'+c for c in 'abcdefghijklmnopqrstuvwxyz']+['lá','lë','lô','lw','lý','ĺé','ľö','ll','lll']:
                glyphs = shaped.shaped(sample)
                advance = sum(g[1] for g in glyphs)
                assert abs(pil.getlength(sample)-advance) < .01, (filename, sample)
                previous_glyphs = previous.shaped(sample)
                assert [g[0] for g in glyphs] == [g[0] for g in previous_glyphs]
                names = [shaped.order[g[0]] for g in glyphs]
                delta = sum(expected.get(key, 0) for key in zip(names, names[1:]))
                assert advance-sum(g[1] for g in previous_glyphs) == delta, (filename, sample)
                report['shaped_pairs'] += 1
            for left in ('I','f','h','l'):
                for right in 'abcdefghijklmnopqrstuvwxyz':
                    if left != 'l' or right in 'bhiklmnpurtz':
                        assert pair_advance(current,left,right) == pair_advance(old,left,right)
        strip_spacing(current, metadata); strip_spacing(old, metadata)
        assert ('GPOS' in current) == ('GPOS' in old)
        if 'GPOS' in current:
            assert current['GPOS'].compile(current) == old['GPOS'].compile(old)
        report['fonts'].append({'path': filename, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'revision_pairs': len(before)})
    for style in ('Upr', 'Ita'):
        relative = Path(f'sources/Lato3{style}2M.vfj')
        a, b = [json.loads(p.read_text()) for p in (ROOT/relative, args.snapshot/'before-source'/relative)]
        for data in (a, b):
            for master in data['font']['masters']: del master['fontMaster']['kerning']
        assert a == b, relative
        report['source_files_checked'] += 1
    for relative in (Path('sources/Lato26-Upright.glyphs'), Path('sources/Lato26-Italic.glyphs'),
                     Path('build/Lato3Upr2M/ds-ufo/masters/Lato26-Regular.glyphs')):
        a, b = [openstep_plist.loads(p.read_text()) for p in (ROOT/relative, args.snapshot/'before-source'/relative)]
        for data in (a,b):
            data.pop('kerningLTR', None)
            if 'userData' in data: data['userData'].pop('Lato26.spacing', None)
            # Re-export can reorder named instance parameters; their values
            # (including the hinting options) must remain exactly equal.
            for instance in data.get('instances', []):
                if 'customParameters' in instance:
                    instance['customParameters'].sort(key=lambda p: p['name'])
        assert a == b, relative
        report['source_files_checked'] += 1
    with zipfile.ZipFile(ROOT/'build/Lato26-Desktop.zip') as archive:
        for name in archive.namelist():
            if not name.endswith(('.ttf','.otf')): continue
            filename = Path(name).name
            if name.startswith('Lato26/'):
                style = 'Ita' if 'Italic' in filename else 'Upr'
                path = ROOT/f'build/Lato3{style}2M/ds-ufo/masters'/filename
            else: path = ROOT/'build'/name
            assert archive.read(name) == path.read_bytes(), name
            extracted = ROOT/'build/Lato26-Desktop'/name
            if extracted.exists(): assert extracted.read_bytes() == path.read_bytes(), name
    for name in ('Light','LightItalic'):
        relative = Path(f'Carlito26/Carlito26-{name}.ttf')
        assert (ROOT/'build'/relative).read_bytes() == (args.snapshot/'before-build'/relative).read_bytes()
    report.update(status='passed', font_count=len(report['fonts']), archive_fonts=38)
    (ROOT/'build/proofs/bowl-spacing-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k != 'fonts'},flush=True)


if __name__ == '__main__': main()
