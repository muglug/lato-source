#!/usr/bin/env python3
"""Cross-check the local screen proof with Smeartype's unchanged WASM renderer."""
import argparse
import hashlib
import importlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

proof = importlib.import_module('51_compare_webapp_cleartype')
ROOT = proof.ROOT
OUTPUT = ROOT/'output/webapp-cleartype/smeartype'
CACHE = ROOT/'.cache/webapp-cleartype/smeartype'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smeartype-dir', type=Path, default=ROOT/'.cache/smeartype')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    fonts = {}
    jobs = []
    lookup = {}
    rasters = {}
    for web_name, style, orientation, weight in proof.comparison.STYLES:
        paths = (proof.CACHE/f'webapp-{style}.ttf',
                 ROOT/f'build/Lato3{orientation}2M/ds-ufo/masters/Lato26-{style}.ttf')
        fonts[style] = paths
        for path in paths:
            assert path.exists(), 'Run tools/51_compare_webapp_cleartype.py first.'
            face = proof.raster(path)
            rasters[path] = face
            for text in (proof.SAMPLE, proof.CONTROL, 'FillJitter a e l'):
                shaped = face.shape.shaped(text)
                assert all(advance_y == offset_x == offset_y == 0
                           for _, _, advance_y, offset_x, offset_y in shaped), (path, text)
                glyphs = [{'index': glyph, 'advanceWidth': advance,
                           'unicode': 32 if face.shape.order[glyph] == 'space' else 0}
                          for glyph, advance, _, _, _ in shaped]
                for size in proof.SIZES:
                    for hinting in (True, False):
                        advance = sum(item[1] for item in shaped)*size/face.shape.upm
                        job = {
                            'font': str(path), 'upm': face.shape.upm,
                            'text': text, 'glyphs': glyphs, 'size': size, 'hinting': hinting,
                            'width': math.ceil(advance)+32, 'height': math.ceil(size*2)+32,
                            'margin': 12, 'baseline': math.ceil(size*1.4)+8,
                            'advance': advance, 'output': str(CACHE/f'{len(jobs)}.rgba'),
                        }
                        jobs.append(job)
                        lookup[path, text, size, hinting] = job
    capabilities_path = CACHE/'capabilities.json'
    manifest = CACHE/'jobs.json'
    manifest.write_text(json.dumps({'gamma': proof.GAMMA, 'jobs': jobs,
                                   'capabilities_path': str(capabilities_path)}))
    subprocess.run(['node', str(ROOT/'tools/52_render_smeartype.mjs'),
                    str(args.smeartype_dir.resolve()), str(manifest)], check=True)

    def render(path, text, size, hinting=True):
        job = lookup[path, text, size, hinting]
        data = Path(job['output']).read_bytes()
        image = Image.frombytes('RGBA', (job['width'], job['height']), data).convert('RGB')
        return image, job['margin'], job['baseline'], job['advance']

    images = [proof.native_sheet(fonts, 100, render, OUTPUT)]
    images += [proof.detail_sheet(style, fonts[style], render, OUTPUT)
               for style in ('Regular', 'Bold', 'Italic', 'BoldItalic')]
    report = {
        'renderer': 'Smeartype unchanged LCD WASM renderer; not Microsoft DirectWrite',
        'revision': subprocess.check_output(['git', '-C', str(args.smeartype_dir),
                                              'rev-parse', 'HEAD'], text=True).strip(),
        'layout': 'HarfBuzz ss05 glyph IDs and advances; zero offsets verified; Smeartype OpenType layout bypassed',
        'capabilities': json.loads(capabilities_path.read_text()),
        'gamma': proof.GAMMA, 'filter': proof.FILTER.tolist(),
        'foreground': '#172332', 'background': '#ffffff',
        'sizes_px': proof.SIZES, 'jobs': len(jobs), 'fonts': {},
        'cross_renderer_controls': [], 'font_comparison_controls': [],
    }
    for style, paths in fonts.items():
        report['fonts'][style] = [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                                  for path in paths]
        for size in proof.SIZES:
            for hinting in (True, False):
                tiles = []
                for path in paths:
                    image = render(path, proof.CONTROL, size, hinting)[0]
                    local = proof.render_tile(rasters[path], proof.CONTROL, size, hinting)[0]
                    actual, expected = np.asarray(image), np.asarray(local)
                    difference = np.abs(actual.astype(int)-expected.astype(int))
                    report['cross_renderer_controls'].append({
                        'style': style, 'font': path.name, 'ppem': size, 'hinting': hinting,
                        'mean_absolute_channel_difference_0_255': float(difference.mean()),
                        'max_channel_difference_0_255': int(difference.max()),
                        'identical': bool(np.array_equal(actual, expected)),
                    })
                    tiles.append(actual)
                foreground = np.array([23, 35, 50])/255
                coverage = [(1-(tile/255)**proof.GAMMA)/(1-foreground**proof.GAMMA) for tile in tiles]
                report['font_comparison_controls'].append({
                    'style': style, 'ppem': size, 'hinting': hinting,
                    'difference_relative_to_webapp_ink': proof.ink_difference(*coverage),
                    'ink_ratio_ours_over_webapp': float(coverage[1].sum()/coverage[0].sum()),
                })
            for path in paths:
                before = np.asarray(render(path, proof.CONTROL, size, False)[0])
                after = np.asarray(render(path, proof.CONTROL, size, True)[0])
                assert not np.array_equal(before, after), (style, path, size)
    report['status'] = 'passed'
    (OUTPUT/'rendering-settings.json').write_text(json.dumps(report, indent=2)+'\n')
    links = '\n'.join(f'<li><a href="{name}">{name}</a></li>' for name in images)
    (OUTPUT/'index.html').write_text(f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Smeartype: webapp v3 vs Lato26</title>
<style>body{{font:16px system-ui;margin:24px;color:#172332}}img{{max-width:none}}</style>
<h1>Smeartype: webapp v3 vs Lato26</h1>
<p>Unchanged Smeartype WASM renderer, FreeType v40, ss05 HarfBuzz layout adapter.
RGB filter [8,77,86,77,8]/256; gamma 1.8 (matched to the repository proof, not Smeartype's 2.2 default).</p>
<p>Not a Windows DirectWrite capture. View native PNGs without scaling.
Hint-control images use 3x nearest-neighbor enlargement.</p>
<ul>{links}<li><a href="rendering-settings.json">Settings and cross-renderer checks</a></li></ul>
<p><a href="../index.html">Repository renderer comparison</a></p>
<img src="screen-100.png" alt="Smeartype rendering of both fonts at six sizes">
</html>
''')
    print(OUTPUT/'index.html', flush=True)


if __name__ == '__main__':
    main()
