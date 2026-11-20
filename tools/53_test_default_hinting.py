#!/usr/bin/env python3
"""Compare webapp v3 with the shipping build using both FreeType renderers."""
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

proof = importlib.import_module('51_compare_webapp_cleartype')
ROOT = proof.ROOT
CACHE = ROOT/'.cache/hint-defaults'
OUTPUT = ROOT/'output/hint-defaults'
TITLES = ('Webapp v3 reference', 'Ours: current build recipe')
KEYS = ('webapp', 'current')
TEXTS = (proof.SAMPLE, proof.CONTROL, 'FillJitter Hnmox')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sheet(fonts, render, directory, style=None):
    titles = TITLES
    heading = 'Shipping build: webapp v3 vs Lato26'
    subtitle = 'Current build: qsq hinting + Latin fallback. ss05 ON. Outlines and spacing also differ.'
    image = Image.new('RGB', (100+540*len(titles), 1180 if style else 1880), 'white')
    proof.label(image, (32, 18), heading+(f' | {style} | 3x pixels' if style else ''), 26)
    proof.label(image, (32, 58), subtitle, 16)
    for column, title in enumerate(titles):
        proof.label(image, (100+column*540, 98), title, 17)
    if style:
        for row, size in enumerate(proof.SIZES):
            top = 150+row*162
            proof.label(image, (32, top), f'{size}px', 14)
            for column, path in enumerate(fonts[style]):
                tile, margin, baseline, advance = render(path, TEXTS[2], size)
                bounds = (margin-2, baseline-math.ceil(size*1.2),
                          margin+math.ceil(advance)+2, baseline+math.ceil(size*.4))
                tile = tile.crop(bounds)
                tile = tile.resize((tile.width*3, tile.height*3), Image.Resampling.NEAREST)
                assert tile.width < 535 and tile.height < 135, (style, size, tile.size)
                image.paste(tile, (100+column*540, top+22))
        name = f'detail-{style}.png'
    else:
        for row, (name, paths) in enumerate(fonts.items()):
            top = 138+row*211
            proof.label(image, (32, top), name, 14)
            for index, size in enumerate(proof.SIZES):
                baseline = top+44+index*28
                proof.label(image, (32, baseline-13), f'{size}px', 11)
                for column, path in enumerate(paths):
                    advance = proof.draw(image, (100+column*540, baseline),
                                         path, proof.SAMPLE, size, render)
                    assert advance < 515
        name = 'screen-100.png'
    proof.label(image, (32, image.height-34),
                'FreeType RGB approximation, not Windows DirectWrite. Gamma 1.8; no rescaling except explicit 3x details.', 14)
    image.save(directory/name)
    return name


def viewer(directory, images, engine):
    links = ''.join(f'<li><a href="{name}">{name}</a></li>' for name in images)
    title = 'Shipping build comparison'
    description = (
        'Webapp v3 versus our current build recipe: ttfautohint 1.8.4.16, '
        'qsq stem fitting with Latin fallback. No experimental font variants. '
        'Our lJ +60 / lI +40 spacing and ss05 forms are preserved. '
        'Both fonts retain tt, fi, and ffi ligatures; our ss05 fl and ffl use a separate l.')
    (directory/'index.html').write_text(f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;margin:24px;color:#172332}}img{{max-width:none}}</style>
<h1>{title}: {engine}</h1>
<p>{description}
Webapp v3 is a reference, not a same-outline control. No shipped files were changed.</p>
<p>FreeType simulation, NOT Windows DirectWrite. ss05 ON; gamma 1.8.
Native sheets use 1 image pixel per sample pixel; details use 3x nearest-neighbor enlargement.</p>
<ul>{links}<li><a href="../report.json">Measurements and validation</a></li></ul>
<img src="screen-100.png" alt="{title}: webapp v3 and Lato26 at six screen sizes">
</html>
''')


def wasm_render(fonts, rasters, source):
    directory = CACHE/'smeartype'
    directory.mkdir(parents=True, exist_ok=True)
    jobs, lookup = [], {}
    for paths in fonts.values():
        for path in paths:
            face = rasters[path]
            for text in TEXTS:
                shaped = face.shape.shaped(text)
                assert all(vertical == offset_x == offset_y == 0
                           for _, _, vertical, offset_x, offset_y in shaped)
                glyphs = [{'index': glyph, 'advanceWidth': advance,
                           'unicode': 32 if face.shape.order[glyph] == 'space' else 0}
                          for glyph, advance, _, _, _ in shaped]
                for size in proof.SIZES:
                    for hinting in (True, False):
                        advance = sum(item[1] for item in shaped)*size/face.shape.upm
                        job = {
                            'font': str(path), 'upm': face.shape.upm, 'text': text,
                            'glyphs': glyphs, 'size': size, 'hinting': hinting,
                            'width': math.ceil(advance)+32, 'height': math.ceil(size*2)+32,
                            'margin': 12, 'baseline': math.ceil(size*1.4)+8,
                            'advance': advance, 'output': str(directory/f'{len(jobs)}.rgba'),
                        }
                        jobs.append(job)
                        lookup[path, text, size, hinting] = job
    manifest = directory/'jobs.json'
    capabilities = directory/'capabilities.json'
    manifest.write_text(json.dumps({'gamma': proof.GAMMA, 'jobs': jobs,
                                   'capabilities_path': str(capabilities)}))
    subprocess.run(['node', str(ROOT/'tools/52_render_smeartype.mjs'),
                    str(source), str(manifest)], check=True)

    def render(path, text, size, hinting=True):
        job = lookup[path, text, size, hinting]
        image = Image.frombytes('RGBA', (job['width'], job['height']),
                                Path(job['output']).read_bytes()).convert('RGB')
        return image, job['margin'], job['baseline'], job['advance']

    return render, json.loads(capabilities.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smeartype-dir', type=Path, default=ROOT/'.cache/smeartype')
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {
        'status': 'running', 'columns': TITLES,
        'note': 'Existing shipping fonts rendered without rehinting or experimental variants.',
        'metric_note': 'Relative absolute coverage difference, not quality. Cross-font comparisons include outline and spacing differences.',
        'gamma': proof.GAMMA, 'filter': proof.FILTER.tolist(), 'sizes': proof.SIZES,
        'cross_renderer_note': 'Hnmox checks isolated glyphs within 3/255. Full strings can differ at touching glyphs: Smeartype filters and composites each glyph separately; native proof composites coverage before filtering.',
        'fonts': {}, 'metrics': [], 'cross_renderer': [],
    }
    fonts, rasters, original_hashes = {}, {}, {}
    for web_name, style, orientation, weight in proof.comparison.STYLES:
        web_path = proof.comparison.WEBAPP/f'fonts/lato-3-hinted/lato-{web_name}.woff2'
        current_path = ROOT/f'build/Lato3{orientation}2M/ds-ufo/masters/Lato26-{style}.ttf'
        for path in (web_path, current_path):
            original_hashes[path] = digest(path)
        web = TTFont(web_path)
        web.flavor = None
        reference = CACHE/f'webapp-{style}.ttf'
        web.save(reference)
        report['fonts'][style] = {
            'webapp': {'path': str(web_path), 'sha256': digest(web_path)},
            'current': {'path': str(current_path), 'sha256': digest(current_path),
                        'ttfa': TTFont(current_path)['TTFA'].data.decode()},
        }
        paths = reference, current_path
        fonts[style] = paths
        rasters.update({path: proof.raster(path) for path in paths})
        for text in TEXTS:
            for size in proof.SIZES:
                hinted = [rasters[path].coverage(text, size)[0] for path in paths]
                metrics = {
                    'style': style, 'text': text, 'ppem': size,
                    'relative_difference_to_webapp': {
                        key: proof.ink_difference(hinted[0], tile) for key, tile in zip(KEYS[1:], hinted[1:])},
                    'ink_ratio_to_webapp': {
                        key: float(tile.sum()/hinted[0].sum()) for key, tile in zip(KEYS[1:], hinted[1:])},
                }
                report['metrics'].append(metrics)
        print(style, 'shipping font comparison measured', flush=True)

    def native_render(path, text, size, hinting=True):
        return proof.render_tile(rasters[path], text, size, hinting)

    smeartype, capabilities = wasm_render(fonts, rasters, args.smeartype_dir.resolve())
    report['smeartype_capabilities'] = capabilities
    report['smeartype_revision'] = subprocess.check_output(
        ['git', '-C', str(args.smeartype_dir), 'rev-parse', 'HEAD'], text=True).strip()
    for style, paths in fonts.items():
        for text in TEXTS:
            for size in proof.SIZES:
                for hinting in (True, False):
                    for key, path in zip(KEYS, paths):
                        actual = np.asarray(smeartype(path, text, size, hinting)[0])
                        expected = np.asarray(native_render(path, text, size, hinting)[0])
                        difference = np.abs(actual.astype(int)-expected.astype(int))
                        if text == proof.CONTROL:
                            assert difference.max() <= 3, (style, size, key, difference.max())
                        report['cross_renderer'].append({
                            'style': style, 'font': key, 'text': text, 'ppem': size,
                            'hinting': hinting, 'max_channel_difference': int(difference.max()),
                            'mean_channel_difference': float(difference.mean()),
                        })
    for name, render in (('native', native_render), ('smeartype', smeartype)):
        directory = OUTPUT/name
        directory.mkdir(parents=True, exist_ok=True)
        images = [sheet(fonts, render, directory)]
        images += [sheet(fonts, render, directory, style)
                   for style in ('Regular', 'Bold', 'Italic', 'BoldItalic')]
        viewer(directory, images, name)
    assert all(digest(path) == expected for path, expected in original_hashes.items())
    report['source_files_unchanged'] = True
    report['status'] = 'passed'
    (OUTPUT/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(OUTPUT/'smeartype/index.html', flush=True)


if __name__ == '__main__':
    main()
