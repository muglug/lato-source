#!/usr/bin/env python3
"""Refresh changed Carlito outlines using the existing font as metric reference.

Unlike a full 04_build_carlito_light.py build, this does not need the original
Calibri installation: existing advances, layout and vertical metrics are kept.
Recover the original interpolation weight from the per-glyph build report and
the unchanged Lato master advances. Reuse the original fitter and emboldener.
"""
import argparse
import copy
import csv
import importlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from modified_font_names import rename_font

build = importlib.import_module('04_build_carlito_light')
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT/'sources/data/lowercase-revision.json'


def recover_weight(style, rows, affected):
    a, b = (TTFont(p) for p in style['masters'])
    lower, upper = 0., 1000.
    for name, row in rows.items():
        if name in affected:
            continue
        ha, hb = a['hmtx'][name][0], b['hmtx'][name][0]
        if ha == hb:
            continue
        old = float(row['lato_adv'])
        ends = sorted((1000*(old-.5-ha)/(hb-ha), 1000*(old+.5-ha)/(hb-ha)))
        lower, upper = max(lower, ends[0]), min(upper, ends[1])
    assert lower <= upper, (lower, upper)
    return (lower+upper)/2, (lower, upper)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only-smaller-l',action='store_true')
    parser.add_argument('--only-e-shape',action='store_true')
    args=parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    for key, short in (('upright', 'Upr'), ('italic', 'Ita')):
        if args.only_e_shape and short!='Upr':continue
        style = build.STYLES[key]
        path = Path(style['out'])
        report_path = path.with_name('report-'+path.stem+'.tsv')
        with report_path.open() as f:
            reader = csv.DictReader(f, delimiter='\t')
            columns = reader.fieldnames
            rows = {r['glyph']: r for r in reader}
        all_affected = set(manifest['styles'][short]['glyphs'])
        affected = (set(json.loads((ROOT/'sources/data/smaller-l.json').read_text())['styles'][short]['glyphs'])
                    if args.only_smaller_l else all_affected)
        if args.only_e_shape:affected=set(json.loads((ROOT/'sources/data/e-shape-revision.json').read_text())['glyphs'])
        design, interval = recover_weight(style, rows, all_affected)
        lato = build.interpolate_lato(style, design)
        e_record=ROOT/'sources/data/e-shape-revision.json'
        e_forms=(set(json.loads(e_record.read_text())['glyphs']) & affected
                 if short=='Upr' and e_record.exists() else set())
        if e_forms:
            # Honor the authored intermediate e masters at Carlito's weight.
            revision_build=importlib.import_module('07_build_revised_lato')
            from fontTools.pens.ttGlyphPen import TTGlyphPen
            from fontTools.pens.cu2quPen import Cu2QuPen
            source=revision_build.Source(short)
            for name in e_forms:
                rec=source.recording(name,design);pen=TTGlyphPen(None)
                rec.replay(Cu2QuPen(pen,max_err=.75,reverse_direction=True))
                lato['glyf'][name]=pen.glyph()
                revision_build.update_metrics(lato,name,source.width(name,design),rec)
        original = TTFont(path, recalcTimestamp=False)
        out = copy.deepcopy(original)
        advances = {n: m[0] for n, m in original['hmtx'].metrics.items()}
        stems = build.measure_stems(lato)
        classify = build.make_classifier(lato)

        def target_of(name):
            return advances[name], 'cmap'

        fitter = build.GlyphBuilder(lato, original, style, stems, classify,
                                   target_of, {n: n for n in advances})
        # The new l has a wider bowl than the former single stem. Condense its
        # body horizontally, with the normal stem-weight restoration, rather
        # than shortening its ascender to fit the unchanged metric slot.
        build.F_MIN = .30
        build.F_MIN_ALT = .30
        for name in sorted(affected):
            glyph, advance, lsb = fitter.build(name)
            assert advance == advances[name], (name, advance, advances[name])
            out['glyf'][name] = glyph
            out['hmtx'][name] = advance, lsb
            if name in fitter.factors:
                mode, factor, bold, cls, how, target, source_adv, adv = fitter.factors[name]
                rows[name] = dict(zip(columns, (name, cls, mode, 'existing',
                    f'{factor:.3f}', f'{bold:.1f}', str(target), str(source_adv), str(adv))))
        removeOverlaps(out, glyphNames=sorted(affected), ignoreErrors=False)
        for name in affected:
            glyph = out['glyf'][name]
            glyph.recalcBounds(out['glyf'])
            out['hmtx'][name] = advances[name], getattr(glyph, 'xMin', 0)
        assert all(out['hmtx'][n][0] == w for n, w in advances.items())
        rename_font(out)
        from truetype_hinting import hint_font
        hint_font(out, sorted(affected))
        out.save(path)
        with report_path.open('w') as f:
            writer = csv.DictWriter(f, fieldnames=columns, delimiter='\t', lineterminator='\n')
            writer.writeheader(); writer.writerows(rows.values())
        manifest['styles'][short]['carlito_design_weight'] = design
        manifest['styles'][short]['carlito_weight_interval'] = list(interval)
        print(path.relative_to(ROOT), f'weight {design:.4f}, all advances preserved', flush=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
