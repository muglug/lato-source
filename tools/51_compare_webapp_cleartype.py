#!/usr/bin/env python3
"""Compare webapp v3 and Lato26 with the repository's FreeType LCD renderer."""
import ctypes
import hashlib
import importlib
import json
import math
from pathlib import Path

import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont

from lcd_font_proofs import RasterFace, GAMMA, FILTER, bind, library

comparison = importlib.import_module('50_compare_webapp_lato')
ROOT = comparison.ROOT
OUTPUT = ROOT/'output/webapp-cleartype'
CACHE = ROOT/'.cache/webapp-cleartype'
SIZES = (12, 14, 16, 18, 20, 24)
SCALES = (100, 125, 150, 200)
SAMPLE = 'FillJitter  Il1 lJ lI  a e l  fl ffi ffl'
CONTROL = 'Hnmox'
UI = '/System/Library/Fonts/Supplemental/Arial.ttf'


class ScreenShape:
    def __init__(self, path):
        self.tt = TTFont(path)
        self.upm = self.tt['head'].unitsPerEm
        self.order = self.tt.getGlyphOrder()
        self.font = hb.Font(hb.Face(path.read_bytes()))
        self.font.scale = self.upm, self.upm

    def shaped(self, text):
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self.font, buffer, {'ss05': True})
        result = [(info.codepoint, position.x_advance, position.y_advance,
                   position.x_offset, position.y_offset)
                  for info, position in zip(buffer.glyph_infos, buffer.glyph_positions)]
        assert all(item[0] for item in result), text
        return result


def raster(path):
    result = RasterFace(path)
    result.shape = ScreenShape(path)
    for text, expected in (('lI', ['l.ss05', 'I.ss05']), ('fl', ['f', 'l.ss05'])):
        names = [result.shape.order[item[0]] for item in result.shape.shaped(text)]
        assert names == expected, (path, text, names)
    return result


def label(image, point, text, size=14, color='#536477'):
    ImageDraw.Draw(image).text(point, text, font=ImageFont.truetype(UI, size), fill=color)


def pixels(alpha):
    foreground = np.array([23, 35, 50])/255
    result = ((1-alpha)+foreground**GAMMA*alpha)**(1/GAMMA)
    return Image.fromarray(np.round(result*255).clip(0, 255).astype('uint8'))


def render_tile(face, text, size, hinting=True):
    alpha, margin, baseline, advance = face.coverage(text, size, hinting=hinting)
    return pixels(alpha), margin, baseline, advance


def draw(image, point, face, text, size, render=render_tile):
    tile, margin, baseline, advance = render(face, text, size)
    left, top = round(point[0])-margin, round(point[1])-baseline
    assert left >= 0 and top >= 0
    assert left+tile.width <= image.width and top+tile.height <= image.height
    bounds = ImageChops.difference(tile, Image.new('RGB', tile.size, 'white')).getbbox()
    if bounds:
        image.paste(tile.crop(bounds), (left+bounds[0], top+bounds[1]))
    return advance


def native_sheet(fonts, percent, render=render_tile, output=OUTPUT):
    scale = percent/100
    image = Image.new('RGB', (round(1320*scale), round(1880*scale)), 'white')
    def caption(horizontal, vertical, text, size=14, color='#536477'):
        label(image, (round(horizontal*scale), round(vertical*scale)),
              text, round(size*scale), color)
    caption(32, 18, f'Webapp v3 vs Lato26 | {percent}% display scale', 25, '#172332')
    caption(32, 58, 'Native hint instructions + RGB filtering; ss05 ON. FreeType approximation, NOT Windows DirectWrite.', 13)
    caption(100, 94, 'Webapp v3', 18)
    caption(750, 94, 'Ours | lJ +60 / lI +40; separate fl / ffl', 18, '#087f74')
    for row, (style, pair) in enumerate(fonts.items()):
        top = 138+row*211
        caption(32, top, style, 14, '#172332')
        for index, size in enumerate(SIZES):
            baseline = top+44+index*28
            caption(32, baseline-13, f'{size}px', 11)
            for column, face in enumerate(pair):
                width = draw(image, ((100+column*650)*scale, baseline*scale),
                             face, SAMPLE, size*scale, render)
                assert width < 535*scale, (style, size, width)
    caption(32, 1842, 'Inspect at 1 image pixel = 1 display pixel. Font outlines and spacing differ too; this is not a hint-only comparison.', 12)
    name = f'screen-{percent}.png'
    image.save(output/name)
    return name


def detail_sheet(style, pair, render=render_tile, output=OUTPUT):
    image = Image.new('RGB', (1940, 1140), 'white')
    label(image, (30, 18), f'{style} | native pixels enlarged 3x (nearest-neighbor)', 26, '#172332')
    label(image, (30, 62), 'Within each font, hint ON/OFF uses identical outlines and spacing. Cross-font differences also include design changes.', 16)
    for column, title in enumerate(('Webapp hints ON', 'Webapp hints OFF', 'Ours hints ON', 'Ours hints OFF')):
        label(image, (30+column*480, 106), title, 19)
    for row, size in enumerate(SIZES):
        top = 150+row*155
        label(image, (30, top), f'{size}px', 14)
        for column in range(4):
            face = pair[column//2]
            tile, margin, baseline, advance = render(
                face, 'FillJitter a e l', size, hinting=column % 2 == 0)
            tile = tile.crop((margin-2, baseline-math.ceil(size*1.2),
                              margin+math.ceil(advance)+2, baseline+math.ceil(size*.4)))
            tile = tile.resize((tile.width*3, tile.height*3), Image.Resampling.NEAREST)
            assert tile.width < 475 and tile.height < 124, (style, size, tile.size)
            image.paste(tile, (30+column*480, top+28))
    label(image, (30, 1104), 'Same native TrueType interpreter, RGB filter and gamma on both sides. Not a DirectWrite capture.', 15)
    name = f'hint-controls-{style}.png'
    image.save(output/name)
    return name


def ink_difference(before, after):
    height = max(before.shape[0], after.shape[0])
    width = max(before.shape[1], after.shape[1])
    padded = []
    for alpha in (before, after):
        result = np.zeros((height, width, 3))
        result[:alpha.shape[0], :alpha.shape[1]] = alpha
        padded.append(result)
    return float(np.abs(padded[0]-padded[1]).sum()/max(padded[0].sum(), 1))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    version = [ctypes.c_int() for _ in range(3)]
    bind('FT_Library_Version', None, [ctypes.c_void_p]+[ctypes.POINTER(ctypes.c_int)]*3)(
        library, *(ctypes.byref(part) for part in version))
    interpreter = ctypes.c_uint()
    status = bind('FT_Property_Get', ctypes.c_int,
                  [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p])(
        library, b'truetype', b'interpreter-version', ctypes.byref(interpreter))
    report = {
        'renderer': 'Repository lcd_font_proofs: FreeType approximation, NOT Windows DirectWrite',
        'freetype': '.'.join(str(part.value) for part in version),
        'truetype_interpreter': interpreter.value if status == 0 else None,
        'ss05': True, 'native_hints': True, 'autohinter': False,
        'gamma': GAMMA, 'rgb_filter': FILTER.tolist(), 'scales': SCALES, 'sizes_css_px': SIZES,
        'sample': SAMPLE, 'control_sample': CONTROL,
        'metric_note': 'Coverage differences and ink ratios measure raster differences, not quality. Controls minimize, but do not eliminate, outline differences.',
        'fonts': {}, 'controls': [],
    }
    fonts = {}
    for web_name, style, orientation, weight in comparison.STYLES:
        web_path = comparison.WEBAPP/f'fonts/lato-3-hinted/lato-{web_name}.woff2'
        temporary = CACHE/f'webapp-{style}.ttf'
        web = TTFont(web_path)
        web.flavor = None
        web.save(temporary)
        decoded = TTFont(temporary)
        for tag in ('glyf', 'hmtx', 'fpgm', 'prep', 'cvt ', 'GSUB', 'GPOS'):
            assert web[tag].compile(web) == decoded[tag].compile(decoded), (style, tag)
        ours_path = ROOT/f'build/Lato3{orientation}2M/ds-ufo/masters/Lato26-{style}.ttf'
        pair = raster(temporary), raster(ours_path)
        fonts[style] = pair
        report['fonts'][style] = [
            {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in (web_path, ours_path)]
        effects = [0, 0]
        for size in sorted({size*scale/100 for size in SIZES for scale in SCALES}):
            hinted = [face.coverage(CONTROL, size)[0] for face in pair]
            unhinted = [face.coverage(CONTROL, size, hinting=False)[0] for face in pair]
            for index, face in enumerate(pair):
                effects[index] += not np.array_equal(hinted[index], unhinted[index])
                rgb, _, _, advance = face.coverage(SAMPLE, size)
                gray, _, _, gray_advance = face.coverage(SAMPLE, size, 'gray')
                expected = sum(item[1] for item in face.shape.shaped(SAMPLE))*size/face.shape.upm
                assert advance == gray_advance and abs(advance-expected) < 1e-8
                assert np.any(rgb[:, :, 0] != rgb[:, :, 1])
                assert np.array_equal(gray[:, :, 0], gray[:, :, 1])
            report['controls'].append({
                'style': style, 'ppem': size,
                'hinted_difference_relative_to_webapp_ink': ink_difference(*hinted),
                'unhinted_difference_relative_to_webapp_ink': ink_difference(*unhinted),
                'hinted_ink_ratio_ours_over_webapp': float(hinted[1].sum()/hinted[0].sum()),
                'unhinted_ink_ratio_ours_over_webapp': float(unhinted[1].sum()/unhinted[0].sum()),
                'hint_effect_webapp': ink_difference(unhinted[0], hinted[0]),
                'hint_effect_ours': ink_difference(unhinted[1], hinted[1]),
            })
        assert all(effects), (style, effects)
        print(style, 'native hints active; shaping and RGB/grayscale checks passed', flush=True)
    images = [native_sheet(fonts, percent) for percent in SCALES]
    images += [detail_sheet(style, fonts[style]) for style in ('Regular', 'Bold', 'Italic', 'BoldItalic')]
    report['status'] = 'passed'
    (OUTPUT/'rendering-settings.json').write_text(json.dumps(report, indent=2)+'\n')
    links = '\n'.join(f'<li><a href="{name}">{name}</a></li>' for name in images)
    (OUTPUT/'index.html').write_text(f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Webapp v3 vs Lato26 screen test</title>
<style>body{{font:16px system-ui;margin:24px;color:#172332}}img{{max-width:none}}a{{color:#087f74}}</style>
<h1>Webapp v3 vs Lato26: screen test</h1>
<p>Existing repository FreeType RGB simulation, NOT a Windows DirectWrite capture. ss05 enabled on both sides.</p>
<p>PNG images are native pixels. View at 100% browser zoom; high-DPI displays may still map CSS pixels differently.
Hint-control images use explicit 3x nearest-neighbor enlargement.</p>
<ul>{links}<li><a href="rendering-settings.json">Settings, font hashes and checks</a></li></ul>
<p>Cross-font samples include design and spacing differences. Hint ON/OFF pairs isolate hinting within each font.</p>
<img src="screen-100.png" alt="Eight styles at six screen sizes, webapp v3 versus Lato26">
</html>
''')
    print(OUTPUT/'index.html', flush=True)


if __name__ == '__main__':
    main()
