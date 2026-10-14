#!/usr/bin/env python3
"""Refresh the shipped fonts from the revised active VFJ outlines.

Only glyphs listed in lowercase-revision.json are rebuilt. Existing character
coverage, layout tables, and unrelated outlines remain in their original
font containers; family names become Lato26. Interpolatable TTFs are converted together, so Carlito26 and
future variable-font builds retain compatible masters. Static Regular keeps
the saved a quadratics and uses the later four-master cubic e revision,
including through component references.

Requires fonttools, glyphsLib, numpy, openstep-plist, ttfautohint 1.3 (and skia-pathops for the
separate Carlito26 build). Run 08_refresh_carlito_outlines.py afterwards for Carlito26.
"""
import argparse
import copy
import importlib
import json
from pathlib import Path

import numpy as np
import openstep_plist
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuMultiPen, Cu2QuPen
from fontTools.pens.pointPen import PointToSegmentPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from glyphsLib.glyphdata import get_glyph
from modified_font_names import rename_font
from lowercase_kerning import apply_spacing, CONFIG as SPACING_CONFIG, pair_advance
from truetype_hinting import hint_font, configure_glyphs_instances

revision = importlib.import_module('06_update_lato_outlines')
ROOT, MANIFEST = revision.ROOT, revision.MANIFEST
REGULAR = ROOT / 'build/Lato3Upr2M/ds-ufo/masters/Lato26-Regular.glyphs'
WEIGHTS = dict(Hairline=0, Thin=100, Light=250, Regular=540, Medium=600,
               Semibold=666, Bold=780, Heavy=880, Black=1000)
E_SHAPE = ROOT/'sources/data/e-shape-revision.json'


def layer_pair(glyph, design, intermediates=None):
    """Bracket a design with the source endpoints and optional authored masters."""
    layers={0:revision.master(glyph,False),1000:revision.master(glyph,True)}
    layers.update({int(d):layer for d,layer in (intermediates or {}).items()})
    stops=sorted(layers)
    for lo,hi in zip(stops,stops[1:]):
        if lo<=design<=hi:
            return layers[lo],layers[hi],(design-lo)/(hi-lo)
    raise ValueError(design)


def transform(element):
    t = element.get('transform', {})
    assert not set(t)-{'xScale', 'yScale', 'xOffset', 'yOffset'}, t
    return (t.get('xScale', 1), 0, 0, t.get('yScale', 1),
            t.get('xOffset', 0), t.get('yOffset', 0))


def glyphs_recording(shapes):
    """Read Glyphs 4's quadratic/cubic point paths without rewriting the file."""
    recording = RecordingPen()
    pp = PointToSegmentPen(ReverseContourPen(recording))
    for shape in shapes:
        if 'nodes' not in shape:
            raise ValueError('Expected outline reference glyph')
        pp.beginPath()
        for x, y, kind, *rest in shape['nodes']:
            segment = {'o': None, 'l': 'line', 'c': 'curve', 'q': 'qcurve'}[kind[0]]
            pp.addPoint((float(x), float(y)), segmentType=segment, smooth='s' in kind)
        pp.endPath()
    return recording


def regular_overrides():
    data = openstep_plist.load(REGULAR.open())
    gs = {g['glyphname']: g for g in data['glyphs']}
    return {n: glyphs_recording(gs[n]['layers'][0]['shapes']) for n in ('a', 'e')}


class Source:
    def __init__(self, style):
        self.style = style
        data = json.loads((ROOT/f'sources/Lato3{style}2M.vfj').read_text())['font']
        self.glyphs = {g['name']: g for g in data['glyphs']}
        # FontLab sometimes nests a component in elementData rather than element.
        for g in self.glyphs.values():
            for layer in g['layers']:
                for element in layer.get('elements', []):
                    data = element.get('elementData', {})
                    if isinstance(data, dict) and 'component' in data:
                        child = self.glyphs[data['component']['glyphName']]
                        child_layer = next(l for l in child['layers'] if l['name'] == layer['name'])
                        if len(child_layer['elements']) != 1 or 'elementData' not in child_layer['elements'][0]:
                            continue
                        element['elementData'] = copy.deepcopy(child_layer['elements'][0]['elementData'])
        self.affected = json.loads(MANIFEST.read_text())['styles'][style]['glyphs']
        self.overrides = regular_overrides() if style == 'Upr' else {}
        if self.overrides:
            self.overrides['a-cy'] = self.overrides['a']
            self.overrides['ie-cy'] = self.overrides['e']
        self.intermediate_layers = (json.loads(E_SHAPE.read_text())['intermediate_layers']
                                    if style=='Upr' and E_SHAPE.exists() else {})
        if self.intermediate_layers:
            # The new four-master cubic e supersedes the older Regular
            # quadratic override; keep the authored a override intact.
            self.overrides.pop('e',None);self.overrides.pop('ie-cy',None)
        self.cache = {}

    def width(self, name, design):
        g = self.glyphs[name]
        h, b = revision.master(g, False), revision.master(g, True)
        return otRound(h['advanceWidth'] + (b['advanceWidth']-h['advanceWidth'])*design/1000)

    def draw(self, name, design, pen, exact=True):
        if exact and design == 540 and name in self.overrides:
            # Saved Glyphs paths were reversed to the VFJ/CFF direction.
            self.overrides[name].replay(pen)
            return
        g = self.glyphs[name]
        a, b, t = layer_pair(g,design,self.intermediate_layers.get(name))
        assert len(a.get('elements', [])) == len(b.get('elements', [])), name
        for ea, eb in zip(a.get('elements', []), b.get('elements', [])):
            tr = tuple(x+(y-x)*t for x, y in zip(transform(ea), transform(eb)))
            ep = TransformPen(pen, tr)
            if 'component' in ea:
                child = ea['component']['glyphName']
                assert child == eb['component']['glyphName'], name
                self.draw(child, design, ep, exact)
            else:
                da, db = ea.get('elementData', {}), eb.get('elementData', {})
                assert isinstance(da, dict) and isinstance(db, dict), (name, da, db)
                ca, cb = da.get('contours', []), db.get('contours', [])
                assert len(ca) == len(cb), name
                for c1, c2 in zip(ca, cb):
                    assert len(c1['nodes']) == len(c2['nodes']), name
                    p1, p2 = RecordingPen(), RecordingPen()
                    revision.draw_contour(c1, p1); revision.draw_contour(c2, p2)
                    assert len(p1.value) == len(p2.value), name
                    for (op1, xy1), (op2, xy2) in zip(p1.value, p2.value):
                        assert op1 == op2 and len(xy1) == len(xy2), name
                        pts = [tuple(x+(y-x)*t for x, y in zip(pt1, pt2))
                               for pt1, pt2 in zip(xy1, xy2)]
                        getattr(ep, op1)(*pts)

    def recording(self, name, design, exact=True):
        key = name, design, exact
        if key not in self.cache:
            p = RecordingPen(); self.draw(name, design, p, exact)
            self.cache[key] = p
        return self.cache[key]


def output_name(source, name, font):
    order = font.getGlyphOrder()
    if name in order:
        return name
    glyph = source.glyphs[name]
    if glyph.get('unicode'):
        match = font.getBestCmap().get(int(glyph['unicode'], 16))
        if match:
            return match
    production = get_glyph(name).production_name
    if production in order:
        return production
    aliases = {'eSign-myanmar.case': 'eSignMyanmar.case', 'f_l': 'fl',
               'f_i': 'fi', 'idotless': 'dotlessi', 'f_lcommaaccent': 'f_uni013C'}
    if aliases.get(name) in order:
        return aliases[name]
    if 'glyf' in font and len(order) == len(source.glyphs):
        # FontLab's TTF export preserves glyph order but uses some historical
        # production names absent from current glyphsLib. Verify the entire
        # encoded order before using that order for an unencoded component.
        cmap = font.getBestCmap()
        for index, g in enumerate(source.glyphs.values()):
            if g.get('unicode'):
                encoded = cmap.get(int(g['unicode'], 16))
                assert encoded is None or encoded == order[index], (g['name'], encoded, order[index])
        return order[list(source.glyphs).index(name)]
    raise ValueError(f'Cannot map {name} in {font.reader.file.name}')


def update_metrics(font, name, width, rec):
    p = BoundsPen(None); rec.replay(p)
    lsb = otRound(p.bounds[0]) if p.bounds else 0
    font['hmtx'][name] = width, lsb


def build_masters(source, directory):
    suffix = 'Italic' if source.style == 'Ita' else ''
    paths = [directory/'Lato26.~VF/master_ttf_interpolatable'/f'Lato26-{w}{suffix}.ttf'
             for w in ('Hairline', 'Black')]
    fonts = [TTFont(p, recalcTimestamp=False) for p in paths]
    for name in source.affected:
        records = [source.recording(name, design, exact=False) for design in (0, 1000)]
        pens = [TTGlyphPen(None), TTGlyphPen(None)]
        multi = Cu2QuMultiPen(pens, max_err=.75, reverse_direction=True)
        assert len(records[0].value) == len(records[1].value), name
        for (op0, p0), (op1, p1) in zip(records[0].value, records[1].value):
            assert op0 == op1 and len(p0) == len(p1), name
            if op0 == 'closePath':
                multi.closePath()
            else:
                getattr(multi, op0)([p0, p1])
        glyphs = [p.glyph() for p in pens]
        assert glyphs[0].endPtsOfContours == glyphs[1].endPtsOfContours, name
        assert glyphs[0].flags == glyphs[1].flags, name
        for font, glyph, design, rec in zip(fonts, glyphs, (0, 1000), records):
            out = output_name(source, name, font)
            font['glyf'][out] = glyph
            update_metrics(font, out, source.width(name, design), rec)
    for f, p, design in zip(fonts, paths, (0, 1000)):
        apply_spacing(f, p, source, design, output_name)
        rename_font(f)
        f.save(p); print(p.relative_to(ROOT), flush=True)


def build_static(source, directory, weight, design, extension):
    suffix = 'Italic' if source.style == 'Ita' else ''
    label = 'Italic' if weight == 'Regular' and suffix else weight+suffix
    path = directory/f'Lato26-{label}.{extension}'
    font = TTFont(path, recalcTimestamp=False)
    for name in source.affected:
        out = output_name(source, name, font)
        rec = source.recording(name, design)
        width = source.width(name, design)
        if extension == 'ttf':
            pen = TTGlyphPen(None)
            rec.replay(Cu2QuPen(pen, max_err=.75, reverse_direction=True))
            font['glyf'][out] = pen.glyph()
        else:
            top = font['CFF '].cff.topDictIndex[0]
            pen = T2CharStringPen(width, None)
            rec.replay(Qu2CuPen(pen, max_err=.1, all_cubic=True))
            charstring = pen.getCharString(private=top.Private,
                                           globalSubrs=font['CFF '].cff.GlobalSubrs)
            top.CharStrings[out] = charstring
        update_metrics(font, out, width, rec)
    apply_spacing(font, path, source, design, output_name)
    rename_font(font)
    if extension == 'ttf':
        hint_font(font, [output_name(source, n, font) for n in source.affected])
    font.save(path)
    print(path.relative_to(ROOT), flush=True)


def update_glyphs(source, directory):
    """Patch only affected glyph bodies, retaining the author's a/e paths."""
    text = REGULAR.read_text()
    parsed = openstep_plist.loads(text)
    saved = {g['glyphname']: g for g in parsed['glyphs']}
    font = TTFont(directory/'Lato26-Regular.ttf')
    # Imported Glyphs uses the static font's production names.
    for source_name in source.affected:
        name = output_name(source, source_name, font)
        if name not in saved:
            raise ValueError(name)
        start = text.index('\nglyphname = '+name+';') - 1
        end = text.find('\n{\nglyphname = ', start+3)
        if end < 0:
            raise ValueError('No following glyph for '+name)
        block = text[start:end]
        layer = saved[name]['layers'][0]
        if source_name not in ('a', 'e'):
            g = font['glyf'][name]
            shapes = []
            previous = 0
            for last in g.endPtsOfContours:
                coords = list(g.coordinates[previous:last+1])
                flags = list(g.flags[previous:last+1])
                # Glyphs winding is opposite the TTF winding. The q/l type is
                # attached to the endpoint of the incoming segment.
                coords.reverse(); flags.reverse()
                nodes = []
                for i, ((x, y), flag) in enumerate(zip(coords, flags)):
                    kind = 'o' if not flag & 1 else ('q' if not flags[i-1] & 1 else 'l')
                    nodes.append(f'({x},{y},{kind}),')
                shapes.append('{\nclosed = 1;\nnodes = (\n'+'\n'.join(nodes)+'\n);\n},')
                previous = last+1
            source_layers = [revision.master(source.glyphs[source_name], b) for b in (False, True)]
            if all('component' in e for l in source_layers for e in l['elements']):
                shapes = []
                for ea, eb in zip(source_layers[0]['elements'], source_layers[1]['elements']):
                    child = output_name(source, ea['component']['glyphName'], font)
                    tr = [a*.46+b*.54 for a, b in zip(transform(ea), transform(eb))]
                    shapes.append('{\nalignment = -1;\npos = ('+
                                  f'{tr[4]:g},{tr[5]:g}'+');\nref = '+child+';\nscale = ('+
                                  f'{tr[0]:g},{tr[3]:g}'+');\n},')
            a = block.index('shapes = (')
            b = block.index('\n);', a)
            # nodes arrays also end with ); -- find the shapes closing line
            # by counting balanced parentheses outside quoted strings.
            depth = 0; quoted = False; escaped = False
            for i in range(block.index('(', a), len(block)):
                ch = block[i]
                if ch == '"' and not escaped: quoted = not quoted
                if not quoted:
                    if ch == '(': depth += 1
                    elif ch == ')':
                        depth -= 1
                        if depth == 0:
                            b = i+2; break
                escaped = ch == '\\' and not escaped
            block = block[:a] + 'shapes = (\n'+'\n'.join(shapes)+'\n);' + block[b:]
        # Point-number bytecode from the imported TTF is stale after editing.
        import re
        block = re.sub(r'\nuserData = \{\nassembly = "(?:[^"\\]|\\.)*";\n\};', '', block)
        width = source.width(source_name, 540)
        block = re.sub(r'\nwidth = [\d.]+;', f'\nwidth = {width};', block)
        text = text[:start] + block + text[end:]
    if SPACING_CONFIG.exists():
        spec = json.loads(SPACING_CONFIG.read_text())['styles']['Upr']
        kerning = copy.deepcopy(parsed['kerningLTR'])
        assert len(kerning) == 1
        pairs = next(iter(kerning.values()))
        for source_name in spec['left']:
            left = output_name(source, source_name, font)
            row = pairs.setdefault(left, {})
            for right_name in {n for members in spec['right'].values() for n in members}:
                right = output_name(source, right_name, font)
                row[right] = pair_advance(font, left, right)
        start = text.index('kerningLTR = {')+len('kerningLTR = ')
        depth = 0
        for end in range(start, len(text)):
            if text[end] == '{': depth += 1
            elif text[end] == '}':
                depth -= 1
                if not depth: break
        text = text[:start]+openstep_plist.dumps(kerning, indent=0, sort_keys=False)+text[end+1:]
    text = configure_glyphs_instances(text)
    openstep_plist.loads(text)  # Parse the complete result before replacing it.
    REGULAR.write_text(text)
    print(REGULAR.relative_to(ROOT), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--style', choices=['Upr', 'Ita', 'all'], default='all')
    parser.add_argument('--skip-glyphs', action='store_true')
    args = parser.parse_args()
    for style in ('Upr', 'Ita') if args.style == 'all' else (args.style,):
        source = Source(style)
        directory = ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
        build_masters(source, directory)
        for weight, design in WEIGHTS.items():
            for extension in ('ttf', 'otf'):
                build_static(source, directory, weight, design, extension)
        if style == 'Upr' and not args.skip_glyphs:
            update_glyphs(source, directory)


if __name__ == '__main__':
    main()
