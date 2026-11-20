#!/usr/bin/env python3
"""Audit the webapp's hinted Lato v3 fonts against the current Lato26 build."""
import importlib
import io
import json
from pathlib import Path

from fontTools.ttLib import TTFont

proof = importlib.import_module('49_proof_ss05_j')
ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT.parent/'webapp'
OUTPUT = ROOT/'output/webapp-comparison'
STYLES = (
    ('light', 'Light', 'Upr', 300),
    ('regular', 'Regular', 'Upr', 400),
    ('bold', 'Bold', 'Upr', 700),
    ('black', 'Black', 'Upr', 900),
    ('italic-light', 'LightItalic', 'Ita', 300),
    ('italic', 'Italic', 'Ita', 400),
    ('italic-bold', 'BoldItalic', 'Ita', 700),
    ('italic-black', 'BlackItalic', 'Ita', 900),
)


def sfnt(font):
    output = io.BytesIO()
    font.flavor = None
    font.save(output)
    return output.getvalue()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {}
    render_fonts = {}
    for web_name, label, style, weight in STYLES:
        web_path = WEBAPP/f'fonts/lato-3-hinted/lato-{web_name}.woff2'
        ours_path = ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{label}.ttf'
        web, ours = TTFont(web_path), TTFont(ours_path)
        web_cmap, ours_cmap = web.getBestCmap(), ours.getBestCmap()
        shared = sorted(set(web_cmap)&set(ours_cmap))
        advances = []
        for codepoint in shared:
            web_glyph, ours_name = web_cmap[codepoint], ours_cmap[codepoint]
            web_width, ours_width = web['hmtx'][web_glyph][0], ours['hmtx'][ours_name][0]
            if web_width != ours_width:
                advances.append({'codepoint': codepoint, 'glyph': ours_name,
                                 'webapp': web_width, 'ours': ours_width})
        web_face, ours_face = proof.Font(sfnt(web)), proof.Font(sfnt(ours))
        render_fonts[label] = web_face, ours_face, weight
        pairs = {}
        for text in ('a', 'e', 'l', 'I', 'J', 'la', 'le', 'lo', 'lJ', 'lI', 'fl', 'ffl', 'ffi', 'FillJitter',
                     'The quick brown fox jumps over the lazy dog.',
                     'A little elegant letter. Il1 lJ lI'):
            before, after = web_face.shape(text, weight), ours_face.shape(text, weight)
            pairs[text] = {'webapp_glyphs': [item[0] for item in before],
                           'ours_glyphs': [item[0] for item in after],
                           'webapp_advance': sum(item[1] for item in before),
                           'ours_advance': sum(item[1] for item in after)}
        metrics = {}
        for tag, fields in (
            ('hhea', ('ascent', 'descent', 'lineGap')),
            ('OS/2', ('sTypoAscender', 'sTypoDescender', 'sTypoLineGap', 'usWinAscent', 'usWinDescent')),
        ):
            for field in fields:
                metrics[f'{tag}.{field}'] = [getattr(web[tag], field), getattr(ours[tag], field)]
        compressed = io.BytesIO()
        ours.flavor = 'woff2'
        ours.save(compressed)
        report[label] = {
            'webapp_path': str(web_path),
            'ours_path': str(ours_path),
            'glyph_counts': [len(web.getGlyphOrder()), len(ours.getGlyphOrder())],
            'encoded_characters': [len(web_cmap), len(ours_cmap)],
            'added_codepoints': sorted(set(ours_cmap)-set(web_cmap)),
            'removed_codepoints': sorted(set(web_cmap)-set(ours_cmap)),
            'line_metrics': metrics,
            'changed_default_advances': advances,
            'ss05_samples': pairs,
            'hint_tables_identical': {tag: web.getTableData(tag) == ours.getTableData(tag)
                                      for tag in ('fpgm', 'prep', 'cvt ')},
            'woff2_bytes': [web_path.stat().st_size, len(compressed.getvalue())],
        }
        print(label, 'ASCII width changes', [item for item in advances if 32 <= item['codepoint'] < 127],
              'WOFF2 bytes', report[label]['woff2_bytes'], flush=True)
    (OUTPUT/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    figure = proof.plt.figure(figsize=(15.6, 19), dpi=100, facecolor='white')
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(0, 1560)
    axes.set_ylim(1900, 0)
    axes.set_axis_off()
    proof.label(axes, 48, 28, 'Webapp Lato v3 vs Lato26', 26, '#172332', 'bold')
    proof.label(axes, 48, 80, 'ss05 enabled on both sides, matching the webapp’s v3 experiment · current font builds', 13)
    for horizontal, title, color in ((48, 'Webapp · hinted Lato v3', '#536477'), (810, 'Ours · Lato26', '#087f74')):
        proof.label(axes, horizontal, 126, title, 20, color, 'bold')
    ordered = ('Regular', 'Italic', 'Light', 'LightItalic', 'Bold', 'BoldItalic', 'Black', 'BlackItalic')
    for row, label in enumerate(ordered):
        web, ours, weight = render_fonts[label]
        top = 190+row*207
        for column, font in enumerate((web, ours)):
            horizontal = 48+762*column
            axes.plot([horizontal, horizontal+698], [top-10, top-10], color='#e4e9ed', linewidth=.8)
            proof.label(axes, horizontal, top, label, 12, '#087f74' if column else '#536477')
            font.draw(axes, 'a e l I J   lJ lI', weight, 100, horizontal, top+104)
            font.draw(axes, 'la le lo ll  fl ffi ffl  FillJitter', weight, 36, horizontal, top+151)
            font.draw(axes, 'A little elegant letter. James likes a lovely file.', weight, 22, horizontal, top+185)
    proof.label(axes, 48, 1860, 'Unhinted outlines, not platform-specific hinting. Ours: uncapped J, +60 lJ / +40 lI spacing, separate fl/ffl shaping.', 11)
    for extension in ('png', 'svg'):
        path = OUTPUT/f'comparison.{extension}'
        figure.savefig(path, dpi=100, facecolor='white')
        print(path, flush=True)
    proof.plt.close(figure)
    figure = proof.plt.figure(figsize=(12, 10), dpi=100, facecolor='white')
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(0, 1200)
    axes.set_ylim(1000, 0)
    axes.set_axis_off()
    proof.label(axes, 48, 28, 'Default outlines · O Q !', 24, '#172332', 'bold')
    proof.label(axes, 48, 76, 'These characters are unchanged by ss05. Unhinted outline rendering.', 12)
    for row, label in enumerate(('Italic', 'BoldItalic', 'BlackItalic', 'Black')):
        web, ours, weight = render_fonts[label]
        top = 120+row*210
        for column, font in enumerate((web, ours)):
            horizontal = 48+column*600
            proof.label(axes, horizontal, top, ('Webapp · ' if column == 0 else 'Ours · ')+label, 14)
            font.draw(axes, 'O Q !', weight, 170, horizontal, top+175)
    for extension in ('png', 'svg'):
        path = OUTPUT/f'default-details.{extension}'
        figure.savefig(path, dpi=100, facecolor='white')
        print(path, flush=True)
    proof.plt.close(figure)


if __name__ == '__main__':
    main()
