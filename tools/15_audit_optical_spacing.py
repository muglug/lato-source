#!/usr/bin/env python3
"""Measure l/a-z spacing with a repeatable multiscale blur-overlap heuristic.

This audit measures interaction between ink fields, not reading performance
or an objectively correct kerning value. It does not choose pair adjustments.
"""
import argparse
import csv
import json
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-build',required=True,type=Path)
    args=parser.parse_args()
    out=ROOT/'build/proofs'; assets=out/'optical-blur';assets.mkdir(parents=True,exist_ok=True)
    report={'method':'Geometric mean of Gaussian ink-overlap ratios against le in the same font.',
            'limitations':'A repeatable interaction proxy, not a validated perceptual optimum. Diagonals need not equal le.',
            'inspiration_url':'https://github.com/behdad/halfkern',
            'blur_sigma_xheight':SIGMAS,'vertical_measurement_band':'baseline to x-height',
            'render_ppem':500,'upm':2000,'designer_additions':{'a':20,'w':8,'y':14},
            'rows':[],'resolution_checks':[]}
    for style in ('Upr','Ita'):
        for weight in WEIGHTS:
            name=('Italic' if weight=='Regular' else weight+'Italic') if style=='Ita' else weight
            rel=Path(f'Lato3{style}2M/ds-ufo/masters/Lato26-{name}.ttf')
            audit=Audit(args.before_build/rel); current=TTFont(ROOT/'build'/rel)
            assert audit.font.getTableData('glyf')==current.getTableData('glyf')
            assert audit.font.getTableData('hmtx')==current.getTableData('hmtx')
            reference=audit.overlap('e',pair_advance(current,'l','e'))
            rows=[]
            for char in 'abcdefghijklmnopqrstuvwxyz':
                glyph=audit.cmap[ord(char)]
                old_kern=pair_advance(audit.font,'l',glyph);new_kern=pair_advance(current,'l',glyph)
                row={'style':style,'weight':weight,'pair':'l'+char,
                     'before':audit.metrics(char,old_kern,reference),
                     'after':audit.metrics(char,new_kern,reference),
                     'added_units':new_kern-old_kern,
                     'lower_right_ink_percent':audit.lower_right_density(char)}
                if char in 'awy':
                    assert row['added_units']==report['designer_additions'][char]
                    assert row['after']['blur_index']<row['before']['blur_index']
                if char in 'co':
                    e_gap=audit.metrics('e',pair_advance(current,'l','e'),reference)['horizontal_outline_gap']
                    assert abs(row['after']['horizontal_outline_gap']-e_gap)<=1.1
                if weight=='Regular' and char in 'acewy':
                    for variant,kern in [('before',old_kern),('after',new_kern)]:
                        filename=f'{style}-{char}-{variant}.png'
                        audit.preview(char,kern,assets/filename)
                rows.append(row)
            report['rows'].extend(rows)
            if weight=='Regular':
                fine=Audit(args.before_build/rel,ppem=1000)
                fine_reference=fine.overlap('e',pair_advance(current,'l','e'))
                for row in rows:
                    if row['pair'][1] not in 'acewy':continue
                    high=fine.metrics(row['pair'][1],row['after']['kern'],fine_reference)['blur_index']
                    relative=abs(high/row['after']['blur_index']-1)
                    report['resolution_checks'].append({'style':style,'pair':row['pair'],
                        'ppem_500':row['after']['blur_index'],'ppem_1000':high,
                        'relative_difference':round(relative,5)})
                    assert relative<.08,(style,row['pair'],relative)
            print(style,weight,'26 pairs measured',flush=True)
    assert len(report['rows'])==468
    report['status']='passed'
    (out/'optical-spacing.json').write_text(json.dumps(report,indent=2)+'\n')
    with (out/'optical-spacing.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['style','weight','pair','added_units','before_gap','after_gap',
                                            'before_blur_index','after_blur_index','lower_right_ink_percent'])
        for row in report['rows']:
            writer.writerow([row['style'],row['weight'],row['pair'],row['added_units'],
                row['before']['horizontal_outline_gap'],row['after']['horizontal_outline_gap'],
                row['before']['blur_index'],row['after']['blur_index'],row['lower_right_ink_percent']])
    print('468 pairs audited; 10 resolution checks passed',flush=True)


if __name__=='__main__':main()
