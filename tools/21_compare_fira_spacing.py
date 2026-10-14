#!/usr/bin/env python3
"""Read-only la-lz comparison against the official Fira Sans 4.301 TTFs.

Download reference files listed in the report from the pinned upstream commit
into --reference-dir first. No font is edited by this tool.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import ImageFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

import lcd_font_proofs as lcd
from lcd_font_proofs import RasterFace
from lowercase_kerning import pair_advance
from vector_font_proofs import face

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('optical_audit', ROOT/'tools/15_audit_optical_spacing.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
UPSTREAM = 'https://github.com/bBoxType/FiraSans'
COMMIT = 'f54eeb3124c63fe9b5bcd36d09d1cd46788cd15e'
WEIGHTS = [('Hairline', 'Thin'), ('Thin', 'UltraLight'), ('Light', 'Light'),
           ('Regular', 'Regular'), ('Medium', 'Medium'), ('Semibold', 'SemiBold'),
           ('Bold', 'Bold'), ('Heavy', 'ExtraBold'), ('Black', 'Heavy')]
CHARS = 'abcdefghijklmnopqrstuvwxyz'


class UnhintedAudit(AUDIT.Audit):
    def __init__(self, path, xheight_pixels=256, left='l'):
        self.left = left
        self.raster = RasterFace(path)
        font = self.raster.shape.tt
        ppem = round(xheight_pixels*font['head'].unitsPerEm/font['OS/2'].sxHeight)
        super().__init__(path, ppem=ppem)
        if left != 'l':
            self.le_reference = AUDIT.Audit.overlap(self, 'e', pair_advance(self.font, 'l', 'e'))
            self.overlaps = {}
            self.left_blurs = [self.blur(left, sigma)[self.band].astype(np.float64)
                               for sigma in AUDIT.SIGMAS]

    def overlap(self, char, kern):
        if self.left == 'l':
            return super().overlap(char, kern)
        key = (char,kern)
        if key not in self.overlaps:
            position = (self.font['hmtx'][self.left][0]+kern)*self.scale
            index = int(np.floor(position)); fraction = position-index
            assert 0 < index < self.width-1
            values = []
            for left,sigma in zip(self.left_blurs,AUDIT.SIGMAS):
                right = self.blur(char,sigma)[self.band]
                # Evaluate the needed correlation directly: FFT cancellation can
                # swamp the tiny narrow-blur interaction of widely spaced I pairs.
                a = np.sum(left[:,index:]*right[:,:-index],dtype=np.float64)
                b = np.sum(left[:,index+1:]*right[:,:-index-1],dtype=np.float64)
                values.append(a*(1-fraction)+b*fraction)
            self.overlaps[key] = np.array(values)
        return self.overlaps[key]

    def metrics(self, char, kern, reference):
        if self.left == 'l':
            return super().metrics(char, kern, reference)
        ratios = self.overlap(char,kern)/reference
        assert np.all(ratios >= 0)
        def geometric(values):
            return 0.0 if np.any(values == 0) else float(np.exp(np.mean(np.log(values))))
        gap = (self.font['hmtx'][self.left][0]+kern+self.outline_bounds(char)[0]
               -self.outline_bounds(self.left)[2])
        return {'kern':kern,'horizontal_outline_gap':round(gap,3),
                'blur_index':round(geometric(ratios),5),
                'per_scale_ratios':[round(float(v),5) for v in ratios],
                'blur_index_relative_to_le':geometric(self.overlap(char,kern)/self.le_reference)}

    def mask(self, char):
        if char not in self.masks:
            assert lcd.set_size(self.raster.handle, 0, self.pil.size*64, 72, 72) == 0
            matrix, delta = lcd.Matrix(65536, 0, 0, 65536), lcd.Vector(0, 0)
            lcd.transform(self.raster.handle, lcd.C.byref(matrix), lcd.C.byref(delta))
            gid = self.font.getGlyphID(self.cmap[ord(char)])
            assert lcd.load(self.raster.handle, gid, (1 << 1) | (1 << 3) | (1 << 15)) == 0
            slot = self.raster.handle.contents.glyph
            assert lcd.render(slot, 0) == 0
            bitmap = slot.contents.bitmap
            assert bitmap.pixel_mode == 2 and bitmap.pitch > 0
            raw = lcd.C.string_at(bitmap.buffer, bitmap.pitch*bitmap.rows)
            ink = np.frombuffer(raw, dtype=np.uint8).reshape(bitmap.rows, bitmap.pitch)
            ink = ink[:, :bitmap.width].astype(np.float32)/255
            mask = np.zeros((self.height, self.width), dtype=np.float32)
            x, y = self.x0+slot.contents.bitmap_left, self.y0-slot.contents.bitmap_top
            assert x >= 0 and y >= 0
            assert x+ink.shape[1] <= self.width and y+ink.shape[0] <= self.height
            mask[y:y+ink.shape[0], x:x+ink.shape[1]] = ink
            self.masks[char] = mask
        return self.masks[char]


def measure(path, chars=CHARS, xheight_pixels=256, left='l'):
    input_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    audit = UnhintedAudit(path, xheight_pixels, left)
    font = audit.font
    shaped = audit.raster.shape
    pil = ImageFont.truetype(str(path), audit.upm)
    kerns = {}
    for char in chars+'e':
        glyph = audit.cmap[ord(char)]
        on = shaped.shaped(left+char)
        assert [shaped.order[g[0]] for g in on] == [left, glyph]
        nominal = font['hmtx'][left][0]+font['hmtx'][glyph][0]
        kern = sum(g[1] for g in on)-nominal
        assert kern == pair_advance(font, left, glyph)
        assert abs(pil.getlength(left+char, features=['-kern'])-nominal) < .01
        assert abs(pil.getlength(left+char)-sum(g[1] for g in on)) < .01
        assert on[0][3:] == (0, 0) and on[1][3:] == (0, 0)
        assert on[0][1] == font['hmtx'][left][0]+kern
        kerns[char] = kern
    reference = audit.overlap('e', kerns['e'])
    result = {}
    for char in chars:
        row = audit.metrics(char, kerns[char], reference)
        row['kern_per_1000_em'] = kerns[char]*1000/audit.upm
        row['gap_percent_xheight'] = round(row['horizontal_outline_gap']/audit.xheight*100, 4)
        row['gap_per_1000_em'] = round(row['horizontal_outline_gap']/audit.upm*1000, 4)
        result[left+char] = row
    assert hashlib.sha256(path.read_bytes()).hexdigest() == input_digest, ('Font changed during measurement',path)
    info = {'path': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            'sha256': input_digest,
            'version': font['name'].getDebugName(5), 'units_per_em': audit.upm,
            'xheight': audit.xheight, 'weight_class': font['OS/2'].usWeightClass,
            'render_ppem': audit.pil.size, 'render_xheight_pixels': audit.xheight*audit.scale}
    return result, info


def cached_metrics_match(path, values, left='l'):
    """Reject old reports whose font changed while an earlier audit ran."""
    font=TTFont(path);glyphs=font.getGlyphSet();cmap=font.getBestCmap()
    def bounds(name):
        pen=BoundsPen(glyphs);glyphs[name].draw(pen);return pen.bounds
    edge=bounds(left)[2]
    for pair,metrics in values.items():
        right=cmap[ord(pair[1])];kern=pair_advance(font,left,right)
        gap=font['hmtx'][left][0]+kern+bounds(right)[0]-edge
        if metrics['kern']!=kern or abs(metrics['horizontal_outline_gap']-gap)>.00051:
            return False
    return True


def label(c, x, y, text, size=9, color='#566173', bold=False):
    c.setFillColor(HexColor(color))
    c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
    c.drawString(x, y, text)


def specimen(c, path, text, x, y, xheight, color):
    f = face(str(path))
    scale = xheight/f.tt['OS/2'].sxHeight
    c.saveState()
    c.setFillColor(HexColor(color))
    c.translate(x, y)
    c.scale(scale, scale)
    cursor = 0
    for gid, ax, ay, ox, oy in f.shaped(text):
        assert ay == 0
        c.saveState()
        c.translate(cursor+ox, oy)
        c.drawPath(f.outline(gid, c), stroke=0, fill=1, fillMode=1)
        c.restoreState()
        cursor += ax
    c.restoreState()
    assert x+cursor*scale <= 580, (text, x, cursor*scale)


def proof(report, paths, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(612, 792), pageCompression=1)
    c.setTitle('Lato26 and Fira Sans - lowercase l spacing')
    c.setAuthor('Lato26 spacing comparison')
    rows = {(r['style'], r['weight'], r['pair']): r for r in report['rows']}
    def header(title, subtitle, page):
        label(c, 34, 755, title, 20, '#182435', True)
        label(c, 34, 733, subtitle, 9)
        c.setStrokeColor(HexColor('#dce2e8'))
        c.line(34, 718, 578, 718)
        label(c, 34, 24, 'Lato26 / Fira Sans 4.301 - outline spacing, with native kerning', 8)
        label(c, 553, 24, str(page), 8)

    header('Lowercase l spacing', 'All 26 pairs, 9 nominal weights, upright and italic. Equal x-height.', 1)
    label(c, 34, 692, 'Regular upright: horizontal edge gaps', 13, '#182435', True)
    label(c, 34, 673, 'Percent of x-height; lower values mean less horizontal separation.', 9)
    label(c, 34, 648, 'Pair', 9, bold=True)
    label(c, 96, 648, 'Lato26', 9, '#182435', True)
    label(c, 202, 648, 'Fira Sans', 9, '#2466a3', True)
    label(c, 328, 648, 'Lato26', 9, '#182435', True)
    label(c, 446, 648, 'Fira Sans', 9, '#2466a3', True)
    for i, pair in enumerate(['la','lc','le','lh','lk','ll','lo','lw','ly']):
        y = 614-i*35
        row = rows['Upr', 'Regular', pair]
        label(c, 34, y, pair, 11, '#182435', True)
        for x, family in [(96, 'Lato26'), (202, 'Fira Sans')]:
            label(c, x, y, f"{row[family]['gap_percent_xheight']:.1f}%", 11, '#182435')
        specimen(c, paths['Upr','Regular','Lato26'], pair, 328, y-2, 15, '#182435')
        specimen(c, paths['Upr','Regular','Fira Sans'], pair, 446, y-2, 15, '#182435')
    lines = [
        'Interpretation',
        'Compare each shape against the vertical-left lh anchor, as well as the absolute gap.',
        f"Against le = 1, lh/ll indices: Lato26 {rows['Upr','Regular','lh']['Lato26']['blur_index']:.2f}/{rows['Upr','Regular','ll']['Lato26']['blur_index']:.2f}; "
        f"Fira {rows['Upr','Regular','lh']['Fira Sans']['blur_index']:.2f}/{rows['Upr','Regular','ll']['Fira Sans']['blur_index']:.2f}.",
        'The index describes the spacing pattern; equality is not a target.',
        'Both Regular uprights give lh and lk identical spacing; Lato26 tightens ll.',
        'Weight matters: Fira Bold has tighter lh and ll gaps than Lato26 Bold.',
        'Negative diagonal gaps mean overlapping x extents, not intersecting outlines.',
    ]
    for i, line in enumerate(lines):
        label(c, 34, 270-i*18, line, 10 if i==0 else 9, '#182435', i==0)
    label(c, 34, 145, 'Reading the detailed pages', 11, '#182435', True)
    for i, line in enumerate([
        'K = pair adjustment per 1,000 em (negative tightens). G = gap as % of x-height.',
        'B = geometric mean of ink-overlap ratios at blur radii 6%, 12%, 24% of x-height.',
        'B is normalized to le = 1 in each font. Higher B means more ink interaction.',
        'B is a shape-sensitive diagnostic, not a perceptual score or a target to copy.',
        'All numbers are Lato26 / Fira Sans. Unhinted raster audit; vector specimens.',
    ]): label(c, 34, 126-i*15, line, 8.6)
    c.showPage()
    for page, ((style, weight), mapping) in enumerate(paths_by_style(paths), 2):
        fira_weight = dict(WEIGHTS)[weight]
        title = weight+(' Italic' if style=='Ita' else ' Upright')
        header(title, f'Lato26 {weight} / Fira Sans {fira_weight} - matched nominal weight, equal x-height', page)
        c.bookmarkPage(f'{style}-{weight}')
        c.addOutlineEntry(title, f'{style}-{weight}')
        for x in (34, 318):
            label(c, x+27, 695, 'Lato26', 9, '#182435', True)
            label(c, x+145, 695, 'Fira Sans', 9, '#2466a3', True)
        for i, char in enumerate(CHARS):
            col, line = divmod(i, 13)
            x = 34+284*col
            y = 657-45*line
            pair = 'l'+char
            row = rows[style,weight,pair]
            a, b = row['Lato26'], row['Fira Sans']
            label(c, x, y+4, pair, 8, '#566173')
            specimen(c, mapping['Lato26'], pair, x+27, y, 15, '#182435')
            specimen(c, mapping['Fira Sans'], pair, x+145, y, 15, '#182435')
            text = (f"K {a['kern_per_1000_em']:g}/{b['kern_per_1000_em']:g}   "
                    f"G {a['gap_percent_xheight']:.1f}/{b['gap_percent_xheight']:.1f}   "
                    f"B {a['blur_index']:.2f}/{b['blur_index']:.2f}")
            label(c, x, y-14, text, 7.8)
            c.line(x, y-22, x+260, y-22)
        label(c, 34, 68, 'K: adjustment / 1,000 em. G: horizontal edge gap / x-height %. B: blur index (le = 1).', 8.4)
        label(c, 34, 52, 'Values: Lato26 / Fira Sans. Specimens: equal 15 pt x-height; no fl ligatures.', 8.4)
        c.showPage()
    header('Method and reference files', 'Reproducible measurements; no outlines, spacing, or hints were changed.', 20)
    lines = [
        'Scope: 936 pairs = 26 letters x 18 styles x 2 families.',
        'HarfBuzz default Latin shaping; validated against Pillow/RAQM and GPOS.',
        'K is the difference between the shaped pair advance and unkerned advances.',
        'G = origin of second glyph + its xMin - rightmost xMax of l.',
        'G compares horizontal extents; curves and diagonals can approach at other heights.',
        'Blur uses unhinted FreeType coverage at about 256 pixels per x-height.',
        'It measures ink-field overlap from baseline to x-height at three blur radii.',
        'Resolution checks repeat selected Regular/Bold upright pairs at 512 pixels.',
        'Equal nominal weight does not guarantee equal darkness or stroke thickness.',
        'Hairline is paired with Fira Thin (100); Thin with UltraLight (200).',
        'Heavy is paired with Fira ExtraBold (800); Black with Heavy (900).',
        'Other weights match their nominal 300-700 classes directly.',
        'The comparison uses default glyph forms and excludes fl ligatures.',
    ]
    for i, line in enumerate(lines): label(c, 34, 690-i*24, line, 10, '#182435')
    label(c, 34, 332, 'Reference: official bBox Type Fira Sans 4.301, normal width TTFs.', 10, '#182435', True)
    label(c, 34, 310, UPSTREAM, 9, '#2466a3')
    c.linkURL(UPSTREAM, (34,305,360,322), relative=0)
    label(c, 34, 288, 'Pinned upstream commit: '+COMMIT, 8.5)
    label(c, 34, 266, 'Font hashes, weight mapping and all measurements: fira-spacing-comparison.json', 9)
    max_error = max(r['relative_difference'] for r in report['resolution_checks'])*100
    label(c, 34, 244, f'Maximum blur-index change when doubling raster resolution: {max_error:.2f}%.', 9)
    label(c, 34, 222, 'Reference fonts are cached separately under their original OFL license.', 9)
    c.showPage()
    c.save()


def paths_by_style(paths):
    for style in ('Upr','Ita'):
        for weight, _ in WEIGHTS:
            yield (style,weight), {family:paths[style,weight,family] for family in ('Lato26','Fira Sans')}


def measure_font(key, path):
    style, weight, family = key
    measurements, info = measure(path)
    info.update(family=family, style=style, lato_weight=weight)
    checks = []
    if style == 'Upr' and weight in ('Regular', 'Bold'):
        fine, _ = measure(path, chars='acehlowy', xheight_pixels=512)
        for pair, values in fine.items():
            low = measurements[pair]['blur_index']
            difference = abs(values['blur_index']/low-1)
            assert difference < .04, (family,weight,pair,difference)
            checks.append({'family':family,'weight':weight,'pair':pair,
                           'base':low,'fine':values['blur_index'],'relative_difference':difference})
    return key, measurements, info, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dir', type=Path, default=ROOT/'.cache/fira-sans-4.301')
    parser.add_argument('--reuse-report', action='store_true')
    parser.add_argument('--reuse-unchanged', action='store_true', help='Reuse measurements only for byte-identical fonts')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    paths = {}
    for style in ('Upr','Ita'):
        for weight, fira_weight in WEIGHTS:
            def name(w): return ('Italic' if w=='Regular' else w+'Italic') if style=='Ita' else w
            paths[style,weight,'Lato26'] = ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{name(weight)}.ttf'
            paths[style,weight,'Fira Sans'] = args.reference_dir/f'FiraSans-{name(fira_weight)}.ttf'
    out = ROOT/'build/proofs/fira-spacing-comparison.json'
    if args.reuse_report:
        report = json.loads(out.read_text())
        for info in report['fonts']:
            assert hashlib.sha256((ROOT/info['path']).read_bytes()).hexdigest() == info['sha256']
    else:
        report = {'upstream':UPSTREAM, 'upstream_commit':COMMIT, 'method':__doc__,
                  'blur_sigma_xheight':AUDIT.SIGMAS, 'normalization':'le = 1 within each font',
                  'fonts':[], 'rows':[], 'resolution_checks':[]}
        completed = {}
        if args.reuse_unchanged and out.exists():
            saved = json.loads(out.read_text())
            assert saved['status'] == 'passed' and saved['upstream_commit'] == COMMIT
            for info in saved['fonts']:
                key = info['style'],info['lato_weight'],info['family']
                if key not in paths or hashlib.sha256(paths[key].read_bytes()).hexdigest() != info['sha256']:
                    continue
                values = {r['pair']:r[key[2]] for r in saved['rows'] if (r['style'],r['weight']) == key[:2]}
                if not cached_metrics_match(paths[key], values):continue
                checks = [r for r in saved['resolution_checks'] if key[0]=='Upr' and (r['family'],r['weight']) == (key[2],key[1])]
                assert len(values) == 26
                completed[key] = values,info,checks
        with ProcessPoolExecutor(max_workers=args.workers,
                                 mp_context=multiprocessing.get_context('spawn')) as pool:
            jobs = [pool.submit(measure_font, key, path) for key, path in paths.items() if key not in completed]
            for job in as_completed(jobs):
                key, measurements, info, checks = job.result()
                completed[key] = measurements, info, checks
                print(*key, 'measured', flush=True)
        for (style,weight), mapping in paths_by_style(paths):
            measurements = {}; infos = []
            for family in mapping:
                measurements[family], info, checks = completed[style,weight,family]
                report['fonts'].append(info); infos.append(info)
                report['resolution_checks'].extend(checks)
            assert infos[0]['weight_class'] == infos[1]['weight_class'], infos
            for char in CHARS:
                report['rows'].append({'style':style,'weight':weight,'fira_weight':dict(WEIGHTS)[weight],
                    'pair':'l'+char,**{family:values['l'+char] for family,values in measurements.items()}})
            print(style,weight,'compared',flush=True)
        assert len(report['rows']) == 468 and len(report['fonts']) == 36
        report['status'] = 'passed'
        out.write_text(json.dumps(report,indent=2)+'\n')
        with out.with_suffix('.csv').open('w') as stream:
            writer=csv.writer(stream,lineterminator='\n')
            writer.writerow(['style','weight','fira_weight','pair','family','kern_per_1000_em',
                             'gap_percent_xheight','blur_index'])
            for row in report['rows']:
                for family in ('Lato26','Fira Sans'):
                    writer.writerow([row['style'],row['weight'],row['fira_weight'],row['pair'],family,
                        *[row[family][k] for k in ('kern_per_1000_em','gap_percent_xheight','blur_index')]])
    proof(report, paths, ROOT/'output/pdf/Lato26-FiraSans-Spacing.pdf')
    print('936 pair measurements; 20-page comparison PDF generated.',flush=True)


if __name__ == '__main__':
    main()
