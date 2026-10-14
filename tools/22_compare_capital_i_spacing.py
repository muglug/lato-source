#!/usr/bin/env python3
"""Compare Ia-Iz with la-lz in Lato26 and the pinned Fira Sans reference.

Requires the unchanged fonts and lowercase report from 21_compare_fira_spacing.
The audit reads fonts and writes a separate report and vector proof.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('fira_audit', ROOT/'tools/21_compare_fira_spacing.py')
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
REPORT = ROOT/'build/proofs/fira-capital-i-comparison.json'
PDF = ROOT/'output/pdf/Lato26-FiraSans-Capital-I-Spacing.pdf'


def worker(info):
    path = ROOT/info['path']
    measurements, current = BASE.measure(path, left='I')
    assert current['sha256'] == info['sha256']
    checks = []
    if info['style']=='Upr' and info['lato_weight'] in ('Regular','Bold'):
        fine, _ = BASE.measure(path, chars='aehly', xheight_pixels=512, left='I')
        for pair, values in fine.items():
            for metric in ('blur_index','blur_index_relative_to_le'):
                difference = abs(values[metric]/measurements[pair][metric]-1)
                assert difference < .04, (info,pair,metric,difference)
                checks.append({'family':info['family'],'weight':info['lato_weight'],
                    'pair':pair,'metric':metric,'relative_difference':difference})
    return info, measurements, checks


def proof(report):
    label, specimen = BASE.label, BASE.specimen
    rows = {(r['style'],r['weight'],r['char']):r for r in report['rows']}
    paths = {(r['style'],r['lato_weight'],r['family']):ROOT/r['path'] for r in report['fonts']}
    c = canvas.Canvas(str(PDF), pagesize=(612,792), pageCompression=1)
    c.setTitle('Lato26 and Fira Sans - capital I versus lowercase l spacing')
    c.setAuthor('Lato26 spacing comparison')
    def header(title, subtitle, page):
        label(c,34,755,title,20,'#182435',True)
        label(c,34,733,subtitle,9)
        c.setStrokeColor(HexColor('#dce2e8'));c.line(34,718,578,718)
        label(c,34,24,'Lato26 / Fira Sans 4.301 - capital I and lowercase l, native kerning',8)
        label(c,553,24,str(page),8)
    def columns(y):
        for x,text in [(34,'Following letter'),(177,'Lato26: lower l'),(277,'Lato26: capital I'),
                       (377,'Fira: lower l'),(477,'Fira: capital I')]:
            label(c,x,y,text,9,'#182435',True)
    header('Capital I versus lowercase l', 'Ia-Iz and la-lz: 9 nominal weights, upright and italic, at equal x-height.',1)
    label(c,34,693,'Regular upright: horizontal edge gap as % of x-height',12,'#182435',True)
    columns(666)
    for i,char in enumerate('acehklowy'):
        y = 639-i*26
        row = rows['Upr','Regular',char]
        label(c,34,y,char,11,'#182435',True)
        for x,family,case in [(177,'Lato26','lower'),(277,'Lato26','capital'),
                              (377,'Fira Sans','lower'),(477,'Fira Sans','capital')]:
            label(c,x,y,f"{row[family][case]['gap_percent_xheight']:.1f}%",11,'#182435')
    label(c,34,392,'Same x-height, same baseline',12,'#182435',True)
    label(c,34,367,'Lato26 Regular',9,'#182435',True)
    label(c,324,367,'Fira Sans Regular',9,'#2466a3',True)
    for i,char in enumerate('ehl'):
        y=331-i*45
        for x,family in [(34,'Lato26'),(324,'Fira Sans')]:
            path=paths['Upr','Regular',family]
            specimen(c,path,'l'+char,x,y,18,'#182435')
            specimen(c,path,'I'+char,x+105,y,18,'#182435')
    lines = [
        'Regular capital-I gaps are wider than lowercase-l gaps in both uprights.',
        'Capital-I pairs help separate each font\'s general spacing rhythm from its l bowl.',
        'Bold changes the comparison: Lato26 Ie is slightly wider than Fira Ie.',
        'Fira has zero capital-I kerning across all 26 pairs and 18 styles in this audit.',
        'Lato26 upright uses modest I-pair kerning; its italic I-pair kerning is zero.',
        'An edge gap is not a minimum contour distance, especially in italic and diagonals.',
    ]
    for i,line in enumerate(lines):label(c,34,203-i*18,line,9,'#182435')
    label(c,34,70,'The detailed pages show l and I side by side within each family.',9)
    label(c,34,54,'K = kerning per 1,000 em. G = horizontal edge gap as % of x-height.',9)
    c.showPage()
    page=1
    for style in ('Upr','Ita'):
        for weight,fira_weight in BASE.WEIGHTS:
            page+=1
            title=weight+(' Italic' if style=='Ita' else ' Upright')
            header(title,f'Lato26 {weight} / Fira Sans {fira_weight}. Within each family: lowercase l, then capital I.',page)
            c.bookmarkPage(f'{style}-{weight}');c.addOutlineEntry(title,f'{style}-{weight}')
            for x in (34,318):
                label(c,x+18,698,'Lato26',9,'#182435',True)
                label(c,x+146,698,'Fira Sans',9,'#2466a3',True)
                for dx,text in [(18,'lowercase l'),(76,'capital I'),(146,'lowercase l'),(204,'capital I')]:
                    label(c,x+dx,683,text,7)
            for i,char in enumerate(BASE.CHARS):
                col,line=divmod(i,13);x=34+284*col;y=650-45*line
                row=rows[style,weight,char]
                label(c,x,y+3,char,8)
                for dx,family,left in [(18,'Lato26','l'),(76,'Lato26','I'),
                                       (146,'Fira Sans','l'),(204,'Fira Sans','I')]:
                    specimen(c,paths[style,weight,family],left+char,x+dx,y,14,'#182435')
                for dx,family in [(0,'Lato26'),(128,'Fira Sans')]:
                    a,b=(row[family][case] for case in ('lower','capital'))
                    value=(f"K {a['kern_per_1000_em']:g}/{b['kern_per_1000_em']:g}  "
                           f"G {a['gap_percent_xheight']:.1f}/{b['gap_percent_xheight']:.1f}")
                    label(c,x+dx,y-14,value,7)
                c.line(x,y-22,x+260,y-22)
            label(c,34,61,'Each value is lowercase l / capital I. K: adjustment per 1,000 em. G: gap as % of x-height.',8)
            label(c,34,46,'All specimens have the same x-height. Negative G means overlapping x extents, not a collision.',8)
            c.showPage()
    header('Blur comparison and method','Regular upright: compare each left letter\'s rhythm relative to its own e pair.',20)
    columns(691)
    for i,char in enumerate('aehklwy'):
        y=665-i*26;row=rows['Upr','Regular',char]
        label(c,34,y,char,11,'#182435',True)
        for x,family,case in [(177,'Lato26','lower'),(277,'Lato26','capital'),
                              (377,'Fira Sans','lower'),(477,'Fira Sans','capital')]:
            label(c,x,y,f"{row[family][case]['blur_index']:.2f}",11,'#182435')
    lines=[
        'Each lowercase-l column uses le = 1; each capital-I column uses Ie = 1.',
        'Higher values mean stronger blurred ink interaction, not better spacing.',
        'These ratios compare the pattern across pairs, not absolute I-versus-l closeness.',
        'The JSON also records capital-I overlap relative to le in the same font.',
        'Unhinted FreeType masks at about 256 pixels per x-height; equal-sized specimens.',
        'Gaussian blur radii: 6%, 12%, 24% of x-height. Band: baseline to x-height.',
        'HarfBuzz kerning checked against GPOS and independent Pillow/RAQM shaping.',
        '936 new capital-I measurements; 936 lowercase-l measurements reused by font hash.',
        'Selected Regular/Bold upright measurements repeated at 512 pixels per x-height.',
        'Nominal weight matching is unchanged; it does not imply equal stroke thickness.',
        'Hairline/Thin map to Fira Thin/UltraLight; Heavy/Black map to ExtraBold/Heavy.',
        'No font outlines, metrics, kerning, or hinting were modified.',
    ]
    for i,line in enumerate(lines):label(c,34,455-i*21,line,9)
    error=max(r['relative_difference'] for r in report['resolution_checks'])*100
    label(c,34,183,f'Maximum change in checked blur indices at double resolution: {error:.2f}%.',9)
    label(c,34,160,'Data: build/proofs/fira-capital-i-comparison.json and .csv',9)
    label(c,34,145,'Zero interaction is possible where the truncated blur fields do not meet.',8)
    label(c,34,130,'Official Fira Sans 4.301 reference: '+BASE.UPSTREAM,8.5,'#2466a3')
    c.linkURL(BASE.UPSTREAM,(34,124,578,142))
    label(c,34,109,'Pinned commit: '+BASE.COMMIT,8.5)
    c.showPage();c.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-report',action='store_true')
    parser.add_argument('--reuse-unchanged',action='store_true',help='Reuse measurements only for byte-identical fonts')
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    lower_path=ROOT/'build/proofs/fira-spacing-comparison.json'
    lower=json.loads(lower_path.read_text())
    for info in lower['fonts']:
        assert hashlib.sha256((ROOT/info['path']).read_bytes()).hexdigest()==info['sha256']
    if args.reuse_report:
        report=json.loads(REPORT.read_text())
        assert report['lowercase_report_sha256']==hashlib.sha256(lower_path.read_bytes()).hexdigest()
    else:
        report={'upstream':BASE.UPSTREAM,'upstream_commit':BASE.COMMIT,'fonts':lower['fonts'],
                'lowercase_report_sha256':hashlib.sha256(lower_path.read_bytes()).hexdigest(),
                'normalization':'I pairs relative to Ie; l pairs relative to le; plus I against le.',
                'rows':[],'resolution_checks':[]}
        caps={}
        if args.reuse_unchanged and REPORT.exists():
            saved=json.loads(REPORT.read_text())
            assert saved['status']=='passed' and saved['upstream_commit']==BASE.COMMIT
            hashes={r['path']:r['sha256'] for r in saved['fonts']}
            for info in lower['fonts']:
                if hashes.get(info['path'])!=info['sha256']:continue
                key=info['style'],info['lato_weight'],info['family']
                caps[key]={'I'+r['char']:r[key[2]]['capital'] for r in saved['rows'] if (r['style'],r['weight'])==key[:2]}
                assert len(caps[key])==26
                report['resolution_checks'].extend(r for r in saved['resolution_checks']
                    if key[0]=='Upr' and (r['family'],r['weight'])==(key[2],key[1]))
        with ProcessPoolExecutor(max_workers=args.workers,
                                 mp_context=multiprocessing.get_context('spawn')) as pool:
            jobs=[pool.submit(worker,info) for info in lower['fonts']
                  if (info['style'],info['lato_weight'],info['family']) not in caps]
            for job in as_completed(jobs):
                info,values,checks=job.result()
                caps[info['style'],info['lato_weight'],info['family']]=values
                report['resolution_checks'].extend(checks)
                print(info['family'],info['style'],info['lato_weight'],'checked',flush=True)
        for row in lower['rows']:
            char=row['pair'][1]
            item={'style':row['style'],'weight':row['weight'],'fira_weight':row['fira_weight'],'char':char}
            for family in ('Lato26','Fira Sans'):
                upper=caps[row['style'],row['weight'],family]['I'+char]
                if family=='Fira Sans' or row['style']=='Ita':assert upper['kern']==0
                item[family]={'lower':row[family],'capital':upper}
            report['rows'].append(item)
        assert len(report['rows'])==468
        report['status']='passed'
        REPORT.write_text(json.dumps(report,indent=2)+'\n')
        with REPORT.with_suffix('.csv').open('w') as stream:
            writer=csv.writer(stream,lineterminator='\n')
            writer.writerow(['style','weight','family','pair','kern_per_1000_em','gap_percent_xheight',
                             'blur_index_own_e','blur_index_relative_to_le'])
            for row in report['rows']:
                for family in ('Lato26','Fira Sans'):
                    for case,left in [('lower','l'),('capital','I')]:
                        m=row[family][case]
                        writer.writerow([row['style'],row['weight'],family,left+row['char'],
                            m['kern_per_1000_em'],m['gap_percent_xheight'],m['blur_index'],
                            m.get('blur_index_relative_to_le',m['blur_index'])])
    proof(report)
    print('Capital-I audit and 20-page I/l comparison proof complete.',flush=True)


if __name__=='__main__':main()
