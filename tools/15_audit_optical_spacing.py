#!/usr/bin/env python3
"""Measure l/a-z spacing with a repeatable multiscale blur-overlap heuristic.

This audit measures interaction between ink fields, not reading performance
or an objectively correct kerning value. It does not choose pair adjustments.
"""
import argparse
import csv
import json
import importlib
import hashlib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.fft import rfft, irfft, next_fast_len
from scipy.ndimage import gaussian_filter, shift
from PIL import Image, ImageDraw, ImageFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from lowercase_kerning import pair_advance

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ['Hairline','Thin','Light','Regular','Medium','Semibold','Bold','Heavy','Black']
SIGMAS = (.06, .12, .24)


class Audit:
    def __init__(self, path, ppem=500):
        self.font = TTFont(path)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font['head'].unitsPerEm
        self.xheight = self.font['OS/2'].sxHeight
        self.scale = ppem/self.upm
        self.pil = ImageFont.truetype(str(path), ppem)
        factor = ppem/500
        self.width, self.height = round(896*factor), round(832*factor)
        self.x0, self.y0 = round(128*factor), round(576*factor)
        yy = (self.y0-np.arange(self.height))/self.scale
        self.band = (yy >= 0) & (yy <= self.xheight)
        self.lower = (yy >= 0) & (yy <= self.xheight/3)
        self.masks = {}; self.curves = {}; self.bounds = {}
        self.fft_size = next_fast_len(2*self.width-1)
        self.left_fft = [rfft(self.blur('l', sigma)[self.band], self.fft_size, axis=1)
                         for sigma in SIGMAS]

    def mask(self, char):
        if char not in self.masks:
            im = Image.new('L', (self.width, self.height))
            ImageDraw.Draw(im).text((self.x0,self.y0),char,font=self.pil,anchor='ls',fill=255)
            self.masks[char] = np.asarray(im,dtype=np.float32)/255
        return self.masks[char]

    def blur(self, char, sigma):
        return gaussian_filter(self.mask(char),sigma*self.xheight*self.scale,mode='constant')

    def outline_bounds(self, char):
        if char not in self.bounds:
            pen = BoundsPen(self.glyphs)
            self.glyphs[self.cmap[ord(char)]].draw(pen)
            self.bounds[char] = pen.bounds
        return self.bounds[char]

    def overlap(self, char, kern):
        if char not in self.curves:
            self.curves[char] = [irfft(np.sum(left*np.conj(rfft(
                self.blur(char,sigma)[self.band],self.fft_size,axis=1)),axis=0),self.fft_size)
                for left,sigma in zip(self.left_fft,SIGMAS)]
        position = (self.font['hmtx']['l'][0]+kern)*self.scale
        index = int(np.floor(position)); fraction = position-index
        return np.array([curve[index]*(1-fraction)+curve[index+1]*fraction
                         for curve in self.curves[char]],dtype=float)

    def metrics(self, char, kern, reference):
        ratios = self.overlap(char,kern)/reference
        assert np.all(ratios>0), (char,kern,ratios)
        score = float(np.exp(np.mean(np.log(ratios))))
        gap = self.font['hmtx']['l'][0]+kern+self.outline_bounds(char)[0]-self.outline_bounds('l')[2]
        return {'kern':kern,'horizontal_outline_gap':round(gap,3),
                'blur_index':round(score,5),'per_scale_ratios':[round(float(v),5) for v in ratios]}

    def lower_right_density(self, char):
        lo,_,hi,_ = self.outline_bounds(char)
        a = round(self.x0+(lo+hi)/2*self.scale)
        b = round(self.x0+hi*self.scale)
        return round(float(self.mask(char)[self.lower,a:b].mean()*100),2)

    def preview(self, char, kern, path):
        position = (self.font['hmtx']['l'][0]+kern)*self.scale
        ink = np.clip(self.mask('l')+shift(self.mask(char),(0,position),order=1,mode='constant'),0,1)
        ink = gaussian_filter(ink,.12*self.xheight*self.scale,mode='constant')
        left = self.outline_bounds('l'); right = self.outline_bounds(char)
        pad = .30*self.xheight
        x0 = round(self.x0+(min(left[0],right[0]+position/self.scale)-pad)*self.scale)
        x1 = round(self.x0+(max(left[2],right[2]+position/self.scale)+pad)*self.scale)
        y0 = round(self.y0-(max(left[3],right[3])+pad)*self.scale)
        y1 = round(self.y0-(min(left[1],right[1])-pad)*self.scale)
        crop = ink[max(0,y0):min(self.height,y1),max(0,x0):min(self.width,x1)]
        # Identical contrast for each before/after pair; no individual renormalization.
        Image.fromarray(np.uint8(np.clip(255*(1-crop),0,255))).save(path)


def measure_font(job):
    style,weight,before_build,reference_dir=job
    assets=ROOT/'build/proofs/optical-blur'
    report={'rows':[],'fonts':[],'resolution_checks':[]}
    unhinted=importlib.import_module('21_compare_fira_spacing').UnhintedAudit
    edges=importlib.import_module('10_refine_ae_and_l_spacing').edges
    name=('Italic' if weight=='Regular' else weight+'Italic') if style=='Ita' else weight
    rel=Path(f'Lato3{style}2M/ds-ufo/masters/Lato26-{name}.ttf')
    audit=unhinted(before_build/rel); current=TTFont(ROOT/'build'/rel)
    geometry_changed=audit.font.getTableData('glyf')!=current.getTableData('glyf')
    after_audit=unhinted(ROOT/'build'/rel) if geometry_changed else audit
    assert audit.xheight==after_audit.xheight
    reference=after_audit.overlap('e',pair_advance(current,'l','e'))
    original=unhinted(reference_dir/f'Lato-{name}.ttf') if reference_dir else None
    original_ref=original.overlap('e',pair_advance(original.font,'l','e')) if original else None
    ys=np.arange(.25,audit.xheight/3,2)
    left_edges=edges(audit.glyphs,'l',ys)[1]
    report['fonts'].append({'path':str(rel),'sha256':hashlib.sha256((ROOT/'build'/rel).read_bytes()).hexdigest()})
    rows=[]
    for char in 'abcdefghijklmnopqrstuvwxyz':
        glyph=audit.cmap[ord(char)]
        old_kern=pair_advance(audit.font,'l',glyph);new_kern=pair_advance(current,'l',glyph)
        row={'style':style,'weight':weight,'pair':'l'+char,
             'before':audit.metrics(char,old_kern,reference),
             'after':after_audit.metrics(char,new_kern,reference),
             'added_units':new_kern-old_kern,
             'outline_changed':geometry_changed,
             'advance_change_units':current['hmtx']['l'][0]-audit.font['hmtx']['l'][0],
             'lower_right_ink_percent':audit.lower_right_density(char)}
        if not geometry_changed and row['added_units']>0:
            assert row['after']['blur_index']<row['before']['blur_index']
        elif not geometry_changed and row['added_units']<0:
            assert row['after']['blur_index']>row['before']['blur_index']
        right_edges=edges(audit.glyphs,glyph,ys)[0]
        for variant,kern in [('before',old_kern),('after',new_kern)]:
            measure=after_audit if variant=='after' else audit
            gap=(measure.font['hmtx']['l'][0]+kern+edges(measure.glyphs,glyph,ys)[0]
                 -edges(measure.glyphs,'l',ys)[1])
            row[variant]['lower_bowl_clearance']=round(float(np.nanmin(gap)),3)
            row[variant]['gap_percent_xheight']=round(row[variant]['horizontal_outline_gap']/audit.xheight*100,4)
        assert row['after']['lower_bowl_clearance'] >= min(row['before']['lower_bowl_clearance'],40)-1.1, row
        if original:
            original_glyph=original.cmap[ord(char)]
            row['original']=original.metrics(char,pair_advance(original.font,'l',original_glyph),original_ref)
            row['original']['gap_percent_xheight']=round(row['original']['horizontal_outline_gap']/original.xheight*100,4)
        if char in 'co':
            e_gap=after_audit.metrics('e',pair_advance(current,'l','e'),reference)['horizontal_outline_gap']
            assert abs(row['after']['horizontal_outline_gap']-e_gap)<=1.1
        if weight=='Regular' and char in 'acewy':
            for variant,kern in [('before',old_kern),('after',new_kern)]:
                filename=f'{style}-{char}-{variant}.png'
                (after_audit if variant=='after' else audit).preview(char,kern,assets/filename)
        rows.append(row)
    report['rows'].extend(rows)
    if weight=='Regular':
        fine=unhinted(ROOT/'build'/rel,xheight_pixels=512)
        fine_reference=fine.overlap('e',pair_advance(current,'l','e'))
        for row in rows:
            if row['pair'][1] not in 'acewy':continue
            high=fine.metrics(row['pair'][1],row['after']['kern'],fine_reference)['blur_index']
            relative=abs(high/row['after']['blur_index']-1)
            report['resolution_checks'].append({'style':style,'pair':row['pair'],
                'xheight_256':row['after']['blur_index'],'xheight_512':high,
                'relative_difference':round(relative,5)})
            assert relative<.08,(style,row['pair'],relative)
    print(style,weight,'26 pairs measured',flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-build',required=True,type=Path)
    parser.add_argument('--reference-dir',type=Path,help='Optional original Lato 2.015 TTFs')
    args=parser.parse_args()
    out=ROOT/'build/proofs'; assets=out/'optical-blur';assets.mkdir(parents=True,exist_ok=True)
    report={'method':'Geometric mean of Gaussian ink-overlap ratios against le in the same font.',
            'limitations':'A repeatable interaction proxy, not a validated perceptual optimum. Diagonals need not equal le.',
            'inspiration_url':'https://github.com/behdad/halfkern',
            'blur_sigma_xheight':SIGMAS,'vertical_measurement_band':'baseline to x-height',
            'render_xheight_pixels':256,'upm':2000,'designer_additions':{'a':20,'w':8,'y':14},
            'before_build':str(args.before_build.resolve()),
            'reference_dir':str(args.reference_dir.resolve()) if args.reference_dir else None,
            'rows':[],'resolution_checks':[],'fonts':[]}
    jobs=[(style,weight,args.before_build,args.reference_dir)
          for style in ('Upr','Ita') for weight in WEIGHTS]
    with ProcessPoolExecutor(max_workers=3,mp_context=multiprocessing.get_context('spawn')) as pool:
        for result in pool.map(measure_font,jobs):
            for key in ('rows','fonts','resolution_checks'):
                report[key].extend(result[key])
    assert len(report['rows'])==468
    report['status']='passed'
    (out/'optical-spacing.json').write_text(json.dumps(report,indent=2)+'\n')
    with (out/'optical-spacing.csv').open('w') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(['style','weight','pair','added_units','before_gap','after_gap',
                                            'before_blur_index','after_blur_index','lower_right_ink_percent'])
        for row in report['rows']:
            writer.writerow([row['style'],row['weight'],row['pair'],row['added_units'],
                row['before']['horizontal_outline_gap'],row['after']['horizontal_outline_gap'],
                row['before']['blur_index'],row['after']['blur_index'],row['lower_right_ink_percent']])
    print('468 pairs audited; 10 resolution checks passed',flush=True)


if __name__=='__main__':main()
