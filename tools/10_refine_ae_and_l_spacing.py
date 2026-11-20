#!/usr/bin/env python3
"""One-time follow-up: align ae joins and plan l spacing against original Lato.

Run after 06 and before rebuilding with 07/08. Native VFJ kerning is updated;
lowercase-spacing.json supplies the same corrections to existing exports.
"""
import copy
import importlib
import json
import math
from pathlib import Path

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont

from lowercase_kerning import CONFIG, original_layout_metadata, pair_advance, spacing_strength
build = importlib.import_module('07_build_revised_lato')
rev = build.revision
ROOT = build.ROOT


class FlatPen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set); self.lines = []
    def _moveTo(self, point):
        self.start = self.p = np.array(point, float)
    def _lineTo(self, point):
        point = np.array(point, float); self.lines.append((self.p, point)); self.p = point
    def _curveToOne(self, p1, p2, p3):
        p0 = self.p.copy(); a, b, c = map(np.array, (p1, p2, p3))
        for t in np.linspace(0, 1, 65)[1:]:
            self._lineTo((1-t)**3*p0+3*t*(1-t)**2*a+3*t*t*(1-t)*b+t**3*c)
    def _closePath(self):
        self._lineTo(self.start)
    def _endPath(self):
        pass


def edges(glyph_set, name, ys):
    pen = FlatPen(glyph_set); glyph_set[name].draw(pen)
    a, b = np.array(pen.lines).transpose(1, 0, 2)
    low, high = [], []
    for y in ys:
        mask = ((a[:, 1] <= y) & (b[:, 1] > y)) | ((a[:, 1] > y) & (b[:, 1] <= y))
        aa, bb = a[mask], b[mask]
        xs = aa[:, 0]+(bb[:, 0]-aa[:, 0])*(y-aa[:, 1])/(bb[:, 1]-aa[:, 1])
        low.append(xs.min() if len(xs) else np.nan)
        high.append(xs.max() if len(xs) else np.nan)
    return np.array(low), np.array(high)


def align_ae(layer, italic):
    e, _, a = rev.contours(layer)
    assert len(a['nodes']) == 23
    upper, lower = (16, 17) if len(e['nodes']) == 25 else (10, 11)
    # The two a-bowl edges meet the corresponding e-bar edges. Blend the
    # adjustment into the existing left-side curves without moving the base.
    targets = (rev.points(e['nodes'][lower])[-1, 1], rev.points(e['nodes'][upper])[-1, 1])
    for indices, endpoint, leftpoint, target in (
            (range(9, 13), 12, 8, targets[0]),
            (range(13, 18), 13, 17, targets[1])):
        end = rev.points(a['nodes'][endpoint])[-1]
        start = rev.points(a['nodes'][leftpoint])[-1]
        dy = target-end[1]
        for index in indices:
            old = a['nodes'][index]; points = rev.points(old)
            t = np.clip((points[:, 0]-start[0])/(end[0]-start[0]), 0, 1)
            shift = dy*t*t*(3-2*t)
            points[:, 1] += shift
            if italic:
                points[:, 0] += .1228*shift
            a['nodes'][index] = rev.node_text(points, ' s' if ' s' in old else '')
    rev.clear_hints(layer)


def patch_json_block(text, old, new, indent):
    def serialize(value):
        return '\n'.join(' '*indent+line for line in json.dumps(
            value, indent=2, separators=(',', ':'), ensure_ascii=False).splitlines())
    a, b = serialize(old), serialize(new)
    # Object opening braces are on the key's line, not indented separately.
    a, b = a[indent:], b[indent:]
    assert text.count(a) == 1
    return text.replace(a, b, 1)


def effective(pairs, classes, left, right):
    lc = next(('@'+c['name'] for c in classes if c.get('1st') and left in c['names']), None)
    rc = next(('@'+c['name'] for c in classes if c.get('2nd') and right in c['names']), None)
    for l, r in ((left, right), (left, rc), (lc, right), (lc, rc)):
        if r in pairs.get(l, {}):
            return int(pairs[l][r])
    return 0


def add_l_pairs(source, spec, fonts, report):
    """Tighten doubled l modestly, protecting hooked and accented forms."""
    right_names = sorted({n for n in spec['left'] if n.startswith('l')} | {'lj', 'lj.ss05'})
    ys = np.arange(-400, 1800, 2)+.25
    caches = [{n: edges(font.getGlyphSet(), build.output_name(source, n, font), ys)
               for n in set(spec['left']) | set(right_names)} for font in fonts]
    for right in right_names:
        spec['right'][right] = [right]
        for left, item in spec['left'].items():
            extras = []
            for i, (font, cache) in enumerate(zip(fonts, caches)):
                width = source.width(left, i*1000)
                added = width-item['original_widths'][i]
                reference = build.output_name(source, item['reference'], font)
                rn = build.output_name(source, right, font)
                gap = width+pair_advance(font, reference, rn)+cache[right][0]-cache[left][1]
                allowed = max(0, math.floor(float(np.nanmin(gap))-42))
                tightening = min(otRound(added*report['l_pair_tightening']), allowed)
                extras.append(added-tightening)
            item['clearance'][right] = extras
    report['l_rights'] = right_names


def main():
    if CONFIG.exists():
        raise SystemExit('Follow-up already applied; rebuild with 07/08.')
    report = {'minimum_clearance': 40, 'styles': {}, 'fonts': {},
              'e_spacing_strength': [[0, .75], [540, .75], [780, .5], [1000, .5]],
              'e_rights': [], 'l_pair_tightening': .25}
    manifest = json.loads(rev.MANIFEST.read_text())
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        path = ROOT/f'sources/Lato3{style}2M.vfj'
        data = json.loads(path.read_text())['font']
        old_glyphs = {g['name']: copy.deepcopy(g) for g in data['glyphs']}
        glyphs = {g['name']: g for g in data['glyphs']}
        for name in ('ae', 'aeTurned', 'aeTurnedmod'):
            for black in (False, True):
                align_ae(rev.master(glyphs[name], black), style == 'Ita')
        rev.save_changed_glyphs(path, old_glyphs, glyphs, ('ae', 'aeTurned', 'aeTurnedmod'))
        classes = data['masters'][0]['fontMaster']['kerning']['kerningClasses']
        groups = ('_KERN_a_2ND', '_KERN_d_2ND', '_KERN_g', '_KERN_g.alt',
                  '_KERN_o_2ND', '_KERN_s_2ND', '_KERN_schwa_2ND',
                  '_KERN_v', '_KERN_w', '_KERN_x', '_KERN_y')
        rights = {c['name']: c['names'] for c in classes if c['name'] in groups}
        for name in ('eth', 'eopen', 'ereversed', 'eturned'):
            rights[name] = [name]
        # Some accents/hooks extend farther left near the tail than their
        # kerning-class base. Give them exceptions instead of loosening le/lo.
        rights = {name: [name] for name in sorted({n for members in rights.values() for n in members})}
        report['e_rights'] = sorted(set(report['e_rights']) | {
            n for n in rights if n.startswith('e') and n not in ('eth', 'eopen', 'ereversed', 'eturned')})
        width_changes = manifest['styles'][style]['width_changes']
        lefts = [n for n in width_changes if n not in ('l.sups', 'lmod', 'lj')]
        lefts += [n for n in source.affected if n.endswith('.ss05') and n.startswith('l') and not n.startswith('lj') and n not in lefts]
        spec = {'right': rights, 'left': {}}
        fonts = [TTFont(ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{w}{"Italic" if style == "Ita" else ""}.ttf') for w in ('Hairline', 'Black')]
        ys = np.arange(-400, 1540, 2)+.25
        caches = [{n: edges(f.getGlyphSet(), build.output_name(source, n, f), ys)
                   for n in set(lefts+['l']+sum(list(rights.values()), []))} for f in fonts]
        for name in sorted(lefts):
            reference = name[:-5] if name.endswith('.ss05') else name
            if reference not in width_changes:
                reference = 'l'
            original_widths = []
            for black in (False, True):
                layer = rev.master(source.glyphs[reference], black)
                original_widths.append(layer['advanceWidth']-width_changes[reference][layer['name']])
            item = {'reference': reference, 'original_widths': original_widths, 'clearance': {}}
            for group, members in rights.items():
                extras = []
                for i, (font, cache) in enumerate(zip(fonts, caches)):
                    out_ref = build.output_name(source, reference, font)
                    proposed_gaps = []
                    for right in members:
                        kern = pair_advance(font, out_ref, build.output_name(source, right, font))
                        gaps = cache[right][0]+original_widths[i]+kern-cache[name][1]
                        proposed_gaps.append(float(np.nanmin(gaps)))
                    needed = max(0, math.ceil(42-min(proposed_gaps)))
                    added_width = rev.master(source.glyphs[name], bool(i))['advanceWidth']-original_widths[i]
                    extras.append(min(added_width, needed))
                item['clearance'][group] = extras
            spec['left'][name] = item
        add_l_pairs(source, spec, fonts, report)
        # Native FontLab glyph-to-class exceptions preserve other class members.
        text = path.read_text()
        for index, wrapped in enumerate(data['masters']):
            fm = wrapped['fontMaster']; k = fm['kerning']; old = copy.deepcopy(k)
            black = fm['name'].startswith('Black'); i = int(black)
            for name, item in spec['left'].items():
                row = k['pairs'].setdefault(name, {})
                delta = item['original_widths'][i]-rev.master(glyphs[name], black)['advanceWidth']
                for group, members in rights.items():
                    adjustment = otRound((delta+item['clearance'][group][i])*
                                         spacing_strength(report, group, i*1000))
                    values = {right: effective(old['pairs'], old['kerningClasses'], item['reference'], right)
                              +adjustment for right in members}
                    common = values[members[0]]
                    row[('@'+group) if group.startswith('_KERN') else group] = str(common)
                    for right, value in values.items():
                        if value != common or right in row:
                            row[right] = str(value)
            text = patch_json_block(text, old, k, 10)
        path.write_text(text)
        report['styles'][style] = spec
        print(style, len(lefts), 'left forms;', sum(map(len, rights.values())), 'right forms')
    for path in sorted((ROOT/'build').glob('Lato3*2M/ds-ufo/masters/**/*.ttf'))+sorted((ROOT/'build').glob('Lato3*2M/ds-ufo/masters/*.otf')):
        report['fonts'][str(path.relative_to(ROOT))] = original_layout_metadata(TTFont(path))
    CONFIG.write_text(json.dumps(report, indent=2)+'\n')
    manifest['ae_join_refined'] = True
    rev.MANIFEST.write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
