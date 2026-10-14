#!/usr/bin/env python3
"""Compare ly/Iy and the complete IoloIolo rhythm without modifying fonts."""
import argparse
import hashlib
import importlib
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from reportlab.pdfgen import canvas

BASE = importlib.import_module('21_compare_fira_spacing')
ROOT = BASE.ROOT
REPORT = ROOT/'build/proofs/fira-rhythm-comparison.json'
PDF = ROOT/'output/pdf/Lato26-FiraSans-Rhythm.pdf'


def worker(info):
    path = ROOT/info['path']
    values, current = BASE.measure(path, chars='Il', left='o')
    assert info['sha256'] == current['sha256']
    f = BASE.face(str(path)); shaped = f.shaped('IoloIolo')
    assert ''.join(f.order[g[0]] for g in shaped) == 'IoloIolo'
    bounds = []
    cursor = 0
    for gid, advance, _, ox, oy in shaped:
        pen = BoundsPen(f.glyphs); f.glyphs[f.order[gid]].draw(pen)
        bounds.append((cursor+ox+pen.bounds[0], cursor+ox+pen.bounds[2]))
        assert oy == 0
        cursor += advance
    gaps = [round((b[0]-a[1])/info['xheight']*100,4) for a,b in zip(bounds,bounds[1:])]
    edges = importlib.import_module('10_refine_ae_and_l_spacing').edges
    middle = {char:edges(f.glyphs,char,np.array([info['xheight']/2])) for char in 'Iolhij'}
    mid_gaps = {pair:round(float((f.tt['hmtx'][pair[0]][0]+BASE.pair_advance(f.tt,*pair)
                  +middle[pair[1]][0][0]-middle[pair[0]][1][0])/info['xheight']*100),4)
                for pair in ('Io','ol','lo','oI','lj','Ij','li','Ii','lh','Ih')}
    return info, values, gaps, mid_gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-snapshot', type=Path, help='Snapshot with before-build and the previous rhythm report')
    args = parser.parse_args()
    narrowed = (ROOT/'sources/data/smaller-l.json').exists()
    prior = json.loads((ROOT/'build/proofs/fira-capital-i-comparison.json').read_text())
    fonts = [f for f in prior['fonts'] if f['lato_weight'] in ('Regular','Bold')]
    for info in fonts:
        assert hashlib.sha256((ROOT/info['path']).read_bytes()).hexdigest() == info['sha256']
    records = {(r['style'],r['weight'],r['char']):r for r in prior['rows']}
    report = {'fonts':fonts, 'sequence':'IoloIolo', 'gap_units':'percent of x-height',
              'interaction':'Geometric mean of three unhinted Gaussian-overlap ratios; same le reference for all four pairs within each font.',
              'rows':[]}
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context('spawn')) as pool:
        for info, returns, gaps, mid_gaps in pool.map(worker,fonts):
            key = info['style'],info['lato_weight']; family = info['family']
            o = records[*key,'o'][family]; y = records[*key,'y'][family]
            pairs = {'Io':o['capital'],'lo':o['lower'],**returns}
            for pair,value in pairs.items():
                value['interaction_relative_to_le'] = value.get('blur_index_relative_to_le',value['blur_index'])
            expected = [pairs[p]['gap_percent_xheight'] for p in ('Io','ol','lo','oI','Io','ol','lo')]
            # Earlier reports round contour bounds to 0.001 native units
            # before normalizing, whereas the whole-word check uses floats.
            assert max(abs(a-b) for a,b in zip(gaps,expected)) < .0002, (key,family,gaps,expected)
            row = {'style':key[0],'weight':key[1],'family':family,'pairs':pairs,'sequence_gaps':gaps,
                   'mid_xheight_gaps':mid_gaps,
                   'ly_Iy_interaction_ratio':y['lower']['blur_index']/y['capital']['blur_index_relative_to_le'],
                   'lo_Io_interaction_ratio':pairs['lo']['interaction_relative_to_le']/pairs['Io']['interaction_relative_to_le'],
                   'ol_oI_interaction_ratio':pairs['ol']['interaction_relative_to_le']/pairs['oI']['interaction_relative_to_le']}
            row['vertical_stem_interaction_ratios'] = {
                char:records[*key,char][family]['lower']['blur_index']/records[*key,char][family]['capital']['blur_index_relative_to_le']
                for char in 'hij'}
            report['rows'].append(row)
            print(key,family,'gaps',gaps[:4],'ly/Iy',round(row['ly_Iy_interaction_ratio'],3),
                  'lo/Io',round(row['lo_Io_interaction_ratio'],3),'ol/oI',round(row['ol_oI_interaction_ratio'],3),flush=True)
    previous = None
    if args.before_snapshot:
        previous = json.loads((args.before_snapshot/'build/proofs/fira-rhythm-comparison.json').read_text())
        for info in previous['fonts']:
            if info['family'] != 'Lato26': continue
            path = args.before_snapshot/'before-build'/Path(info['path']).relative_to('build')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == info['sha256']
        report['previous'] = {'snapshot':str(args.before_snapshot.resolve()), 'fonts':previous['fonts'], 'rows':previous['rows']}
    report['status'] = 'passed'
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    c = canvas.Canvas(str(PDF),pagesize=(612,792),pageCompression=1)
    c.setTitle('Lato26 / Fira Sans - ly, Iy and IoloIolo rhythm')
    label,specimen = BASE.label,BASE.specimen
    label(c,34,756,'ly / Iy and IoloIolo',21,'#182435',True)
    label(c,34,734,'Current fonts, native kerning, equal x-height.',10)
    paths = {(f['style'],f['lato_weight'],f['family']):ROOT/f['path'] for f in fonts}
    for index,(style,weight) in enumerate((('Upr','Regular'),('Upr','Bold'),('Ita','Regular'),('Ita','Bold'))):
        top = 706-index*150
        label(c,34,top,weight+(' upright' if style=='Upr' else ' italic'),12,'#182435',True)
        for x,family in ((34,'Lato26'),(318,'Fira Sans')):
            row = next(r for r in report['rows'] if (r['style'],r['weight'],r['family']) == (style,weight,family))
            path = paths[style,weight,family]
            label(c,x,top-19,family,9,'#2466a3',True)
            specimen(c,path,'IoloIolo',x,top-52,20,'#182435')
            specimen(c,path,'ly Iy',x,top-83,13,'#182435')
            gaps=' / '.join(f'{row["mid_xheight_gaps"][pair]:.1f}' for pair in ('Io','ol','lo','oI'))
            label(c,x,top-102,'Mid-height Io / ol / lo / oI: '+gaps,8.3)
            label(c,x,top-116,f"Interaction ly/Iy {row['ly_Iy_interaction_ratio']:.2f}; lo/Io {row['lo_Io_interaction_ratio']:.2f}; ol/oI {row['ol_oI_interaction_ratio']:.2f}",8.3)
        c.setStrokeColorRGB(.85,.88,.91);c.line(34,top-131,578,top-131)
    label(c,34,99,'Gaps: sampled halfway up x-height, as % of x-height. The four-gap cycle repeats.',9)
    label(c,34,83,'Interaction: 1 means equal blurred-ink overlap; below 1 means weaker interaction.',9)
    label(c,34,67,'Three blur radii: 6%, 12%, 24% of x-height. This is a diagnostic, not a target.',9)
    label(c,34,43,'Data: build/proofs/fira-rhythm-comparison.json. References: Fira Sans 4.301.',8)
    c.showPage()
    if previous:
        label(c,34,756,('Effect of the smaller l' if narrowed else 'Effect of the rhythm refinement'),21,'#182435',True)
        label(c,34,734,('Previous and current Lato26 at equal x-height; revised l bowl and advance width.' if narrowed else
                       'Previous and current Lato26 at equal x-height; original outlines and hints preserved.'),9)
        for index,(style,weight) in enumerate((('Upr','Regular'),('Upr','Bold'),('Ita','Regular'),('Ita','Bold'))):
            top = 706-index*150
            label(c,34,top,weight+(' upright' if style=='Upr' else ' italic'),12,'#182435',True)
            path = paths[style,weight,'Lato26']
            old_path = args.before_snapshot/'before-build'/path.relative_to(ROOT/'build')
            for x,caption,proof_path,records in ((34,'Before',old_path,previous['rows']), (318,'After',path,report['rows'])):
                row = next(r for r in records if (r['style'],r['weight'],r['family']) == (style,weight,'Lato26'))
                label(c,x,top-19,caption,9,'#2466a3',True)
                specimen(c,proof_path,'IoloIolo',x,top-52,20,'#182435')
                specimen(c,proof_path,'ly Iy   la lc le lo lw',x,top-82,11,'#182435')
                body_ratio = row['mid_xheight_gaps']['lo']/row['mid_xheight_gaps']['Io']
                label(c,x,top-102,f"Body gap lo/Io {body_ratio:.2f}; interaction lo/Io {row['lo_Io_interaction_ratio']:.2f}",8.3)
                label(c,x,top-116,f"Interaction ly/Iy {row['ly_Iy_interaction_ratio']:.2f}",8.3)
            c.setStrokeColorRGB(.85,.88,.91);c.line(34,top-131,578,top-131)
        label(c,34,91,('Special pairs keep their edge clearances; ordinary pairs follow the narrower l advance.' if narrowed else
                      'Capital-I pairs and incoming ol spacing stay fixed. lc and lo retain the le outline-edge gap.'),9)
        label(c,34,75,'Accented forms follow their bases; individual hook and mark clearance exceptions remain.',9)
        label(c,34,43,'These measurements guide the design; they are not validated perceptual targets.',8)
        c.showPage()
    label(c,34,756,'lj / Ij and vertical-stem rhythm',21,'#182435',True)
    label(c,34,734,('Current fonts at equal x-height. lj, li and lh use the narrower l; capital-I pairs stay fixed.' if narrowed else
                   'Current fonts at equal x-height. lj, li, lh and their capital-I pairs are unchanged.'),9)
    for index,(style,weight) in enumerate((('Upr','Regular'),('Upr','Bold'),('Ita','Regular'),('Ita','Bold'))):
        top = 706-index*150
        label(c,34,top,weight+(' upright' if style=='Upr' else ' italic'),12,'#182435',True)
        for x,family in ((34,'Lato26'),(318,'Fira Sans')):
            row = next(r for r in report['rows'] if (r['style'],r['weight'],r['family']) == (style,weight,family))
            label(c,x,top-19,family,9,'#2466a3',True)
            specimen(c,paths[style,weight,family],'lj Ij   li Ii',x,top-59,16,'#182435')
            gaps=row['mid_xheight_gaps']; ratios=row['vertical_stem_interaction_ratios']
            label(c,x,top-84,f"Stem gaps lj / Ij: {gaps['lj']:.1f} / {gaps['Ij']:.1f}% x-height",8.5)
            label(c,x,top-100,f"Stem gaps li / Ii: {gaps['li']:.1f} / {gaps['Ii']:.1f}% x-height",8.5)
            label(c,x,top-116,f"Interaction lj/Ij {ratios['j']:.2f}; li/Ii {ratios['i']:.2f}; lh/Ih {ratios['h']:.2f}",8.3)
        c.setStrokeColorRGB(.85,.88,.91);c.line(34,top-131,578,top-131)
    label(c,34,99,'lj follows li: their upright stem gaps and lower-bowl clearances are identical in Lato26.',9)
    label(c,34,83,'Italic stem gaps are also almost identical. The j descender makes bounding-box gaps misleading.',9)
    label(c,34,67,('Default l spacing changes together across vertical stems; no separate lj correction is applied.' if narrowed else
                  'The broader Regular l/I relationship is shared by h and i; j is not a separate spacing outlier.'),9)
    label(c,34,43,'Stem gaps are sampled at half x-height. Interaction uses the three-scale ink diagnostic.',8)
    c.showPage()
    c.save()
    print(PDF,flush=True)


if __name__ == '__main__': main()
