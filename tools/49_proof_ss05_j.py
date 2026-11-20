#!/usr/bin/env python3
"""Compare original ss05 spacing with the built +60 lJ / +40 lI units."""
import argparse
import io
import json
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch
from matplotlib.transforms import Affine2D
import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'output/ss05-j'
BASELINE = '3cb00ee1b'
EXTRA_SPACING = {'lJ': 60, 'lI': 40}
WEIGHTS = ('Hairline', 'Thin', 'Light', 'Regular', 'Medium', 'Semibold', 'Bold', 'Heavy', 'Black')
COLORS = ('#26374a', '#087f74')


class OutlinePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []
        self.codes = []

    def _moveTo(self, point):
        self.points.append(point)
        self.codes.append(PlotPath.MOVETO)

    def _lineTo(self, point):
        self.points.append(point)
        self.codes.append(PlotPath.LINETO)

    def _curveToOne(self, control_one, control_two, endpoint):
        self.points.extend((control_one, control_two, endpoint))
        self.codes.extend((PlotPath.CURVE4,)*3)

    def _closePath(self):
        self.points.append((0, 0))
        self.codes.append(PlotPath.CLOSEPOLY)


class Font:
    def __init__(self, data):
        self.face = hb.Face(data)
        self.tt = TTFont(io.BytesIO(data))
        self.upm = self.tt['head'].unitsPerEm
        self.outlines = {}

    def shape(self, text, weight, extra=0):
        font = hb.Font(self.face)
        font.set_variations({'wght': weight})
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(font, buffer, {'ss05': True})
        shaped = []
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            addition = extra if text[info.cluster:info.cluster+2] in ('lJ', 'lI') else 0
            shaped.append((self.tt.getGlyphName(info.codepoint),
                           position.x_advance+addition, position.x_offset, position.y_offset))
        return shaped

    def outline(self, name, weight):
        key = name, weight
        if key not in self.outlines:
            glyph_set = self.tt.getGlyphSet(location={'wght': weight})
            pen = OutlinePen(glyph_set)
            glyph_set[name].draw(pen)
            self.outlines[key] = PlotPath(pen.points, pen.codes) if pen.points else None
        return self.outlines[key]

    def draw(self, axes, text, weight, size, horizontal, baseline, extra=0, color='#172332'):
        cursor = horizontal
        scale = size/self.upm
        for name, advance, offset_x, offset_y in self.shape(text, weight, extra):
            outline = self.outline(name, weight)
            if outline is not None:
                transform = Affine2D().scale(scale, -scale).translate(
                    cursor+offset_x*scale, baseline-offset_y*scale)
                axes.add_patch(PathPatch(outline, transform=transform+axes.transData,
                                         facecolor=color, edgecolor='none'))
            cursor += advance*scale
        return cursor-horizontal


def label(axes, horizontal, vertical, text, size=14, color='#536477', weight='normal'):
    axes.text(horizontal, vertical, text, fontsize=size, color=color, weight=weight,
              va='top', fontfamily='DejaVu Sans')


def sheet(height, subtitle):
    figure = plt.figure(figsize=(15.6, height/100), dpi=100, facecolor='#ffffff')
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(0, 1560)
    axes.set_ylim(height, 0)
    axes.set_axis_off()
    label(axes, 48, 28, 'Lato26 · ss05 capital spacing', 26, '#172332', 'bold')
    label(axes, 48, 79, subtitle, 13)
    for index, (title, description) in enumerate((
        ('Before', 'Original J · original spacing'),
        ('Current build', 'Original J · +60 units in lJ, +40 in barred lI'),
    )):
        horizontal = 48+index*762
        label(axes, horizontal, 120, title, 20, COLORS[index], 'bold')
        label(axes, horizontal, 155, description, 11)
    return figure, axes


def save(figure, name):
    for extension in ('png', 'svg'):
        path = OUTPUT/f'{name}.{extension}'
        figure.savefig(path, dpi=100, facecolor=figure.get_facecolor())
        print(path)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default=BASELINE)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fonts = {}
    measurements = []
    for style, suffix in (('Upright', ''), ('Italic', 'Italic')):
        relative = f'build/Lato26-Variable/Lato26-Variable{suffix}.ttf'
        before = Font(subprocess.check_output(['git', 'show', f'{args.baseline_ref}:{relative}'], cwd=ROOT))
        after = Font((ROOT/relative).read_bytes())
        fonts[style] = before, after
        for weight in range(100, 901, 50):
            for text in ('lJ', 'lI'):
                original = before.shape(text, weight)
                spaced = after.shape(text, weight)
                expected = before.shape(text, weight, EXTRA_SPACING[text])
                assert [glyph[0] for glyph in original] == ['l.ss05', 'J' if text == 'lJ' else 'I.ss05']
                assert spaced == expected, (style, weight, text, spaced, expected)
                assert sum(glyph[1] for glyph in spaced)-sum(glyph[1] for glyph in original) == EXTRA_SPACING[text]
                measurements.append({'style': style, 'weight': weight, 'pair': text,
                                     'before_advance': sum(glyph[1] for glyph in original),
                                     'current_advance': sum(glyph[1] for glyph in spaced)})
    figure, axes = sheet(1270, 'Built fonts · ss05 enabled throughout · lJ +0.03 em / barred lI +0.02 em')
    for row, (style, weight) in enumerate((('Upright', 400), ('Upright', 700), ('Italic', 400), ('Italic', 700))):
        top = 205+row*245
        before, after = fonts[style]
        for column, font in enumerate((before, after)):
            horizontal = 48+column*762
            axes.plot([horizontal, horizontal+698], [top-12, top-12], color='#e4e9ed', linewidth=.8)
            label(axes, horizontal, top, f'{WEIGHTS[weight//100-1]} {style}', 12, COLORS[column])
            font.draw(axes, 'lJ  lI', weight, 144, horizontal, top+142)
            font.draw(axes, 'lJlJ  lIlI  lJames  lIsaac  FillJitter', weight, 32, horizontal, top+193)
            font.draw(axes, 'lJlJ  lIlI  lJames  lIsaac  FillJitter', weight, 20, horizontal, top+227)
    label(axes, 48, 1205, 'Large samples: 144 px · text samples: 32 and 20 px · unhinted variable outlines', 12)
    label(axes, 48, 1233, 'At 20 px: lJ gains 0.6 px; barred lI gains 0.4 px. J remains uncapped.', 12)
    save(figure, 'comparison')
    figure, axes = sheet(1880, 'Every named weight, upright and italic · 72 px · ss05 enabled throughout')
    for row, (style, weight) in enumerate((style, weight) for weight in range(100, 901, 100) for style in fonts):
        top = 205+row*89
        before, after = fonts[style]
        for column, font in enumerate((before, after)):
            horizontal = 48+column*762
            label(axes, horizontal, top, f'{WEIGHTS[weight//100-1]} {style}', 10, COLORS[column])
            font.draw(axes, 'lJ  lI  JlJ  FillJitter', weight, 72, horizontal, top+74)
    label(axes, 48, 1840, f'Baseline: muglug/lato-source master {args.baseline_ref} · +60 lJ / +40 lI spacing is applied to the current fonts.', 11)
    save(figure, 'all-weights')
    (OUTPUT/'measurements.json').write_text(json.dumps(
        {'baseline': args.baseline_ref, 'status': 'passed', 'pairs': measurements}, indent=2)+'\n')


if __name__ == '__main__':
    main()
