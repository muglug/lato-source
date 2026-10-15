#!/usr/bin/env python3
"""Validate punctuation-only changes against a saved pre-change font set."""
import argparse
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path

from fontTools.misc.xmlWriter import XMLWriter
from fontTools.ttLib import TTFont

from lowercase_kerning import CONFIG, apply_spacing, pair_advance
from punctuation_kerning import adjustment
from variable_font_support import PairValues, ProofFace
from lato_vertical_metrics import assert_published_metrics

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT


def xml(table, font):
    output = io.StringIO()
    table.toXML(XMLWriter(output), font)
    return output.getvalue()


def raw_unchanged(before, after, allowed):
    assert set(before.reader.keys()) == set(after.reader.keys())
    for tag in before.reader.keys():
        if tag in allowed:
            continue
        a, b = before.reader[tag], after.reader[tag]
        if tag == 'head':
            a, b = a[:8] + a[12:], b[:8] + b[12:]
        assert a == b, (after.reader.file.name, tag)


def flat_pairs(lookup):
    assert lookup.LookupType == 2 and lookup.LookupFlag == 8
    pairs = {}
    for sub in lookup.SubTable:
        assert sub.Format == 1 and sub.ValueFormat1 == 4 and sub.ValueFormat2 == 0
        for left, row in zip(sub.Coverage.glyphs, sub.PairSet):
            for pair in row.PairValueRecord:
                pairs.setdefault((left, pair.SecondGlyph), pair.Value1.XAdvance)
    return pairs


def check(snapshot):
    config = json.loads(CONFIG.read_text())
    policy = config['punctuation_allowance']
    report = {'status': 'running', 'static_fonts': [], 'variable_fonts': [],
              'punctuation_checks': 0, 'unchanged_letter_pairs': 0, 'native_shaping_checks': 0}
    sources = {s: build.Source(s) for s in ('Upr', 'Ita')}
    for name in config['fonts']:
        path = ROOT / name
        style = 'Ita' if 'Lato3Ita2M' in name else 'Upr'
        label = path.stem.removeprefix('Lato26-').removesuffix('Italic') or 'Regular'
        design = build.WEIGHTS[label]
        old = TTFont(snapshot / name)
        new = TTFont(path)
        raw_unchanged(old, new, {'GPOS'})
        before = old['GPOS'].table
        after = copy.deepcopy(new['GPOS'].table)
        assert len(before.LookupList.Lookup) == len(after.LookupList.Lookup)
        old_pairs, new_pairs = (flat_pairs(t.LookupList.Lookup[-1]) for t in (before, after))
        expected = dict(old_pairs)
        for left in policy['lefts'][style]:
            for right in policy['rights']:
                a, b = (build.output_name(sources[style], n, new) for n in (left, right))
                delta = adjustment(policy, right, design)
                assert (a, b) not in old_pairs
                expected[a, b] = delta
                assert pair_advance(new, a, b) - pair_advance(old, a, b) == delta
                report['punctuation_checks'] += 1
        assert new_pairs == expected, path
        report['unchanged_letter_pairs'] += len(old_pairs)
        after.LookupList.Lookup[-1] = before.LookupList.Lookup[-1]
        assert xml(after, new) == xml(before, old), path
        original_gpos = new.getTableData('GPOS')
        apply_spacing(new, path, sources[style], design, build.output_name)
        assert new.getTableData('GPOS') == original_gpos, ('non-idempotent rebuild', path)
        if 'master_ttf_interpolatable' not in name:
            assert_published_metrics(new)
            a, b = ProofFace(snapshot / name), ProofFace(path)
            for char in '.,\u2026:;!]}' + '\u201a\u201e\u037e':
                text = 'l' + char
                old_advance = sum(g[1] for g in a.shaped(text))
                new_advance = sum(g[1] for g in b.shaped(text))
                right = next(n for n, c in importlib.import_module('38_space_l_punctuation').RIGHTS.items() if c == char)
                assert new_advance - old_advance == adjustment(policy, right, design), (path, text)
                report['native_shaping_checks'] += 1
            for text in ('la le lo ly lj ll lk lh', 'fl. ffi. office', 'IoloIolo', 'l- l? l) l\u2019', '\u013a. \u013e, \u0142;'):
                if text.startswith('\u013a'):
                    assert sum(g[1] for g in b.shaped(text)) - sum(g[1] for g in a.shaped(text)) == 2 * adjustment(policy, 'period', design) + 20
                else:
                    assert b.shaped(text) == a.shaped(text), (path, text)
                report['native_shaping_checks'] += 1
        report['static_fonts'].append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'only_changed_tables': ['GPOS', 'head.checkSumAdjustment']})
    designs = list(build.WEIGHTS.values())
    for style, suffix in (('Upr', ''), ('Ita', 'Italic')):
        name = f'build/Lato26-Variable/Lato26-Variable{suffix}.ttf'
        path = ROOT / name
        old, new = TTFont(snapshot / name), TTFont(path)
        raw_unchanged(old, new, {'GPOS', 'GDEF'})
        assert_published_metrics(new)
        before, after = old['GPOS'].table, copy.deepcopy(new['GPOS'].table)
        index = len(before.LookupList.Lookup)
        assert len(after.LookupList.Lookup) == index + 1
        after.LookupList.Lookup.pop()
        after.LookupList.LookupCount -= 1
        for record in after.FeatureList.FeatureRecord:
            if record.FeatureTag == 'kern':
                assert record.Feature.LookupListIndex[-1] == index
                record.Feature.LookupListIndex.pop()
                record.Feature.LookupCount -= 1
        assert xml(before, old) == xml(after, new)
        gd = copy.deepcopy(new['GDEF'].table)
        store = old['GDEF'].table.VarStore
        gd.VarStore.VarData = gd.VarStore.VarData[:len(store.VarData)]
        gd.VarStore.VarDataCount = len(store.VarData)
        gd.VarStore.VarRegionList.Region = gd.VarStore.VarRegionList.Region[:len(store.VarRegionList.Region)]
        gd.VarStore.VarRegionList.RegionCount = len(store.VarRegionList.Region)
        assert xml(old['GDEF'].table, old) == xml(gd, new)
        for weight in range(100, 901, 25):
            segment = min((weight - 100) // 100, 7)
            t = (weight - (100 + segment * 100)) / 100
            design = designs[segment] * (1-t) + designs[segment+1] * t
            a, b = PairValues(old, weight), PairValues(new, weight)
            for left in policy['lefts'][style]:
                for right, group in policy['rights'].items():
                    stops = policy['curves'][group]
                    expected = stops[segment][1] * (1-t) + stops[segment+1][1] * t
                    delta = b(left, right) - a(left, right)
                    assert abs(delta - expected) < .002, (style, weight, left, right, delta, expected)
                    report['punctuation_checks'] += 1
            for right in 'abcdefghijklmnopqrstuvwxyz':
                assert b('l', right) == a('l', right)
                report['unchanged_letter_pairs'] += 1
            fa, fb = ProofFace(snapshot / name, weight), ProofFace(path, weight)
            for text in ('la le lo ly lj ll lk lh', 'fl. ffi. office', 'IoloIolo', 'l- l? l) l\u2019'):
                assert fb.shaped(text) == fa.shaped(text), (path, weight, text)
                report['native_shaping_checks'] += 1
            for right, char in importlib.import_module('38_space_l_punctuation').RIGHTS.items():
                delta = sum(g[1] for g in fb.shaped('l' + char)) - sum(g[1] for g in fa.shaped('l' + char))
                assert abs(delta - adjustment(policy, right, design)) <= 1, (path, weight, char)
                report['native_shaping_checks'] += 1
        report['variable_fonts'].append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'weights_checked': list(range(100, 901, 25)), 'only_changed_tables': ['GPOS', 'GDEF', 'head.checkSumAdjustment']})
    report['status'] = 'passed'
    (ROOT / 'build/proofs/l-punctuation-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print({k: len(v) if isinstance(v, list) else v for k, v in report.items()}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    check(parser.parse_args().snapshot)
