#!/usr/bin/env python3
"""Apply the October 2026 lowercase revision to the two active VFJ sources.

Run once against the original sources and exported Regular TTF. The authored
Regular .glyphs file supplies the a/e edits. Splitting cubic curves lets us
transfer its quadratic control-point edits without fitting away their detail.
The dated sources/240102 snapshots are historical and are not build inputs.

Requires fonttools, numpy and openstep-plist. See 07_build_revised_lato.py for
repeatable exports after the sources have been revised.
"""
import copy
import json
import re
from pathlib import Path

import numpy as np
import openstep_plist
from fontTools.misc.bezierTools import splitCubicAtT
from fontTools.pens.basePen import decomposeQuadraticSegment
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
REGULAR = ROOT / 'build/Lato3Upr2M/ds-ufo/masters/Lato-Regular.glyphs'
MANIFEST = ROOT / 'sources/data/lowercase-revision.json'


def points(node):
    numbers = re.findall(r'-?\d+(?:\.\d+)?', node.split('{')[0])
    return np.array([float(n) for n in numbers]).reshape((-1, 2))


def node_text(pts, suffix=''):
    return '  '.join(' '.join(f'{v:.4f}'.rstrip('0').rstrip('.') if v else '0'
                             for v in p) for p in pts) + suffix


def contours(layer):
    return [c for e in layer.get('elements', [])
            if isinstance(e.get('elementData'), dict)
            for c in e['elementData'].get('contours', [])]


def master(glyph, black):
    return next(l for l in glyph['layers']
                if l['name'] == ('Black' if black else 'Hairline') or
                l['name'] == ('BlackItalic' if black else 'HairlineItalic'))


def draw_contour(contour, pen):
    nodes = contour['nodes']
    start = tuple(points(nodes[0])[-1])
    pen.moveTo(start)
    for node in nodes[1:]:
        p = [tuple(v) for v in points(node)]
        if len(p) == 3:
            pen.curveTo(*p)
        elif len(p) == 2:
            pen.curveTo(*p, start)
        else:
            pen.lineTo(p[0])
    pen.closePath()


def contour_from_recording(recording):
    nodes = []
    for op, p in recording:
        if op == 'moveTo':
            nodes.append(node_text(p))
        elif op == 'lineTo':
            nodes.append(node_text(p))
        elif op == 'curveTo':
            if tuple(p[-1]) == tuple(points(nodes[0])[0]):
                nodes.append(node_text(p[:-1], ' c'))
            else:
                nodes.append(node_text(p, ' s'))
        else:
            assert op == 'closePath', op
    return {'nodes': nodes}


def transformed_contour(contour, matrix, offset=(0, 0), reverse=False):
    result = copy.deepcopy(contour)
    result['nodes'] = [node_text(points(n) @ matrix.T + offset,
                                ' c' if len(points(n)) == 2 else
                                ' s' if ' s' in n else '')
                       for n in contour['nodes']]
    if reverse:
        pen = RecordingPen()
        draw_contour(result, ReverseContourPen(pen))
        result = contour_from_recording(pen.value)
    return result


def read_redraw_deltas():
    """Align the saved Glyphs contours to their imported TTF point order."""
    saved = openstep_plist.load(REGULAR.open())
    glyphs = {g['glyphname']: g for g in saved['glyphs']}
    font = TTFont(REGULAR.with_suffix('.ttf'))
    result = {}
    for name in ('a', 'e'):
        old = font['glyf'][name]
        new = copy.deepcopy(old)
        start = 0
        for end, shape in zip(old.endPtsOfContours,
                              glyphs[name]['layers'][0]['shapes']):
            original = list(old.coordinates[start:end + 1])
            edited = [tuple(map(float, n[:2])) for n in shape['nodes']]
            size = len(original)
            assert size == len(edited)
            _, direction, rotation = min(
                (sum(sum((x-y)**2 for x, y in zip(edited[i],
                     original[(rotation+direction*i) % size]))
                     for i in range(size)), direction, rotation)
                for direction in (-1, 1) for rotation in range(size))
            for i, point in enumerate(edited):
                new.coordinates[start + (rotation+direction*i) % size] = point
            start = end + 1
        before, after = RecordingPen(), RecordingPen()
        old.draw(before, font['glyf'])
        new.draw(after, font['glyf'])
        result[name] = []
        for (op, p), (op2, p2) in zip(before.value, after.value):
            assert op == op2
            if op == 'moveTo':
                result[name].append([])
            if op != 'closePath':
                result[name][-1].append((op, np.array(p2, dtype=float)-np.array(p, dtype=float)))
    return result


def apply_segments(contour, delta_segments, matrix, mapping=None):
    """Add quadratic edit curves to exact subdivisions of a cubic contour."""
    if mapping is None:
        mapping = {i: i for i in range(len(delta_segments))}
    inverse = {target: origin for origin, target in mapping.items()}
    old_nodes = contour['nodes']
    new_nodes = [old_nodes[0]]
    start = points(old_nodes[0])[-1]
    previous = start
    for i, node in enumerate(old_nodes[1:], 1):
        cp = points(node)
        closing = len(cp) == 2
        if closing:
            cp = np.vstack((cp, start))
        origin = inverse.get(i)
        if origin is None:
            new_nodes.append(node)
            previous = cp[-1]
            continue
        op, delta = delta_segments[origin]
        before_delta = delta_segments[origin-1][1][-1]
        if not np.any(delta) and not np.any(before_delta):
            new_nodes.append(node)
        elif op == 'lineTo':
            assert len(cp) in (1, 3)
            ds = ([delta[-1]] if len(cp) == 1 else
                  [before_delta, delta[-1], delta[-1]])
            new_nodes.append(node_text(cp + np.array(ds) @ matrix.T,
                                       ' s' if ' s' in node else ''))
        else:
            assert op == 'qCurveTo' and len(cp) == 3
            quadratics = decomposeQuadraticSegment([tuple(d) for d in delta])
            n = len(quadratics)
            cubics = splitCubicAtT(tuple(previous), *[tuple(p) for p in cp],
                                  *[j/n for j in range(1, n)])
            delta_start = before_delta
            for j, (cubic, (control, end)) in enumerate(zip(cubics, quadratics)):
                control, end = np.array(control), np.array(end)
                ds = np.array([delta_start + (control-delta_start)*2/3,
                               end + (control-end)*2/3, end]) @ matrix.T
                altered = np.array(cubic[1:]) + ds
                last = j == n - 1
                if closing and last:
                    new_nodes.append(node_text(altered[:2], ' c'))
                else:
                    new_nodes.append(node_text(altered, ' s'))
                delta_start = end
        previous = cp[-1]
    contour['nodes'] = new_nodes


def bounds(contour):
    p = np.vstack([points(n) for n in contour['nodes']])
    return p.min(axis=0), p.max(axis=0)


def dimensions(cs):
    lo, hi = zip(*(bounds(c) for c in cs))
    return np.min(lo, axis=0), np.max(hi, axis=0)


def clear_hints(layer):
    # These hints name old node indexes and must not survive a topology change.
    for key in ('hints', 'tth'):
        layer.pop(key, None)


def make_tail(upright, italic, black):
    """Mirror j; transfer t's bowl narrowing/shear to the italic tail."""
    ul = contours(master(upright['l'], black))[0]
    j = contours(master(upright['j'], black))[0]
    left, top = bounds(ul)
    jp = points(j['nodes'][0])[0]
    jright = points(j['nodes'][-1])[0]
    baseline = -16 if black else -12
    dy = baseline - bounds(j)[0][1]
    reflected = transformed_contour(j, np.diag([-1., 1.]),
                                    (left[0] + jright[0], dy), reverse=True)
    # Keep l's ascender, replacing only the top two points of the j stem.
    for i, n in enumerate(reflected['nodes']):
        p = points(n)
        if len(p) == 1 and abs(p[0, 1] - (jp[1] + dy)) < .001:
            p[0, 1] = top[1]
            reflected['nodes'][i] = node_text(p)
    if not italic:
        return reflected
    t = contours(master(upright['t'], black))[0]
    ti = contours(master(italic['t'], black))[0]
    # The bottom, terminal and inner-bottom points correspond exactly; italic
    # t has two additional stem-to-bowl segments, outside this fitted region.
    a = [points(t['nodes'][2])[-1]]
    b = [points(ti['nodes'][3])[-1]]
    for u, v in ((3, 4), (4, 5), (5, 6), (6, 7)):
        a.extend(points(t['nodes'][u])); b.extend(points(ti['nodes'][v]))
    a, b = np.array(a), np.array(b)
    fit = np.linalg.lstsq(np.column_stack((a, np.ones(len(a)))), b[:, 0], rcond=None)[0]
    il = contours(master(italic['l'], black))[0]
    ip = np.vstack([points(n) for n in il['nodes']])
    bottom = sorted(ip[ip[:, 1] == 0].tolist())
    ascender = sorted(ip[ip[:, 1] == ip[:, 1].max()].tolist())
    stem_shear = (ascender[0][0] - bottom[0][0]) / ascender[0][1]
    ul_width = top[0] - left[0]
    stem_scale = (bottom[1][0] - bottom[0][0]) / ul_width
    # Express the fitted t bowl relative to its stem at baseline, then place it
    # on l. At the two joins, preserve the original l stem and its tangent.
    tu_left = points(t['nodes'][0])[0, 0]
    ti_top = points(ti['nodes'][0])[0]
    ti_left0 = ti_top[0] - stem_shear * ti_top[1]
    shift = bottom[0][0] - ti_left0
    transformed = []
    join_y = sorted({p[1] for n in reflected['nodes'] for p in points(n)
                     if abs(p[0]-left[0]) < .001 and p[1] < top[1]})[-1]
    for n in reflected['nodes']:
        p = points(n)
        for q in p:
            x, y = q
            if y == top[1]:
                q[:] = (ascender[0] if x == left[0] else ascender[1])
            elif abs(x-left[0]) < .001 or abs(x-top[0]) < .001:
                q[0] = bottom[0][0] + stem_scale*(x-left[0]) + stem_shear*y
            else:
                q[0] = fit[0]*(x + tu_left-left[0]) + fit[1]*y + fit[2] + shift
        transformed.append(node_text(p, ' c' if len(p) == 2 else ' s' if ' s' in n else ''))
    reflected['nodes'] = transformed
    return reflected


def replace_l_stem(target, original_l, tail):
    """Preserve a ligature/modifier's existing stem height, width and slant."""
    p = np.vstack([points(n) for n in target['nodes']])
    src = np.vstack([points(n) for n in original_l['nodes']])
    low, high = p[:, 1].min(), p[:, 1].max()
    bottom = sorted(p[p[:, 1] == low].tolist())
    top = sorted(p[p[:, 1] == high].tolist())
    srcbottom = sorted(src[src[:, 1] == src[:, 1].min()].tolist())
    srctop = sorted(src[src[:, 1] == src[:, 1].max()].tolist())
    sy = (high-low)/(srctop[0][1]-srcbottom[0][1])
    sx = (bottom[-1][0]-bottom[0][0])/(srcbottom[-1][0]-srcbottom[0][0])
    target_shear = (top[0][0]-bottom[0][0])/(high-low)
    source_shear = (srctop[0][0]-srcbottom[0][0])/(srctop[0][1]-srcbottom[0][1])
    matrix = np.array([[sx, target_shear*sy-source_shear*sx], [0, sy]])
    offset = np.array(bottom[0])-np.array(srcbottom[0])@matrix.T
    result = transformed_contour(tail, matrix, offset)
    target['nodes'] = result['nodes']
    return sx


def save_changed_glyphs(path, original, revised, names):
    """Patch glyph blocks only, avoiding unrelated VFJ serialization churn."""
    text = path.read_text()
    for name in names:
        g0, g1 = original[name], revised[name]
        old = json.dumps(g0, indent=2, separators=(',', ':'), ensure_ascii=False)
        new = json.dumps(g1, indent=2, separators=(',', ':'), ensure_ascii=False)
        old = '\n'.join('      '+line for line in old.splitlines())
        new = '\n'.join('      '+line for line in new.splitlines())
        assert text.count(old) == 1, name
        text = text.replace(old, new, 1)
    path.write_text(text)


def apply():
    if MANIFEST.exists():
        raise SystemExit('Revision already applied; use 07_build_revised_lato.py to rebuild.')
    paths = {s: ROOT/f'sources/Lato3{s}2M.vfj' for s in ('Upr', 'Ita')}
    fonts = {s: json.loads(p.read_text())['font'] for s, p in paths.items()}
    original = {s: {g['name']: copy.deepcopy(g) for g in f['glyphs']}
                for s, f in fonts.items()}
    revised = copy.deepcopy(original)
    edits = read_redraw_deltas()
    changed = {s: set() for s in fonts}
    widths = {s: {} for s in fonts}
    a_names = ['a', 'a-cy', 'a.sups', 'amod', 'ainferior', 'acomb', 'acomb.case', 'aTurnedmod']
    e_names = ['e', 'ie-cy', 'e.sups', 'emod', 'einferior', 'ecomb', 'ecomb.case',
               'eSign-myanmar', 'eSign-myanmar.case', 'schwa', 'schwa-cy', 'schwamod', 'eturned']
    for style in ('Upr', 'Ita'):
        glyphs = revised[style]
        for black in (False, True):
            base_a = contours(master(original['Upr']['a'], black))
            base_e = contours(master(original['Upr']['e'], black))[0]
            for name in a_names + ['ae', 'aeTurned', 'aeTurnedmod']:
                layer = master(glyphs[name], black)
                cs = contours(layer)
                candidates = [c for c in cs if len(c['nodes']) == 9 and
                              len(points(c['nodes'][-1])) == 2]
                ligature = name.startswith('ae')
                if ligature:
                    candidates = [c for c in cs if len(c['nodes']) == 8 and
                                  len(points(c['nodes'][1])) == 3]
                if not candidates:
                    continue  # Full-size italic a is single-storey.
                assert len(candidates) == 1, (style, name)
                c = candidates[0]
                lo, hi = dimensions(cs)
                alo, ahi = dimensions(base_a)
                sy = (hi[1]-lo[1])/(ahi[1]-alo[1])
                sx = (bounds(c)[1][0]-bounds(c)[0][0])/(bounds(base_a[2])[1][0]-bounds(base_a[2])[0][0])
                if name in ('aTurnedmod', 'aeTurned', 'aeTurnedmod'):
                    sx, sy = -sx, -sy
                matrix = np.array([[sx, .1228*sy if style == 'Ita' else 0], [0, sy]])
                mapping = {i: i-1 for i in range(2, 8)} if ligature else None
                apply_segments(c, edits['a'][2], matrix, mapping)
                clear_hints(layer); changed[style].add(name)
            for name in e_names + ['ae', 'oe', 'aeTurned', 'aeTurnedmod', 'oeTurned']:
                layer = master(glyphs[name], black)
                cs = contours(layer)
                candidates = [c for c in cs if len(c['nodes']) == 15]
                if not candidates:
                    continue
                assert len(candidates) == 1, (style, name)
                c = candidates[0]
                sy = (points(c['nodes'][0])[0, 1]-points(c['nodes'][2])[-1, 1]) / (points(base_e['nodes'][0])[0, 1]-points(base_e['nodes'][2])[-1, 1])
                matrix = np.array([[1, .1228*sy if style == 'Ita' else 0], [0, sy]])
                # Keep the Hairline crossbar fine: the extra 10 Regular units
                # of bar thickness scale with its existing stroke thickness.
                ds = copy.deepcopy(edits['e'][0])
                stroke = abs(points(c['nodes'][10])[-1, 1]-points(c['nodes'][11])[-1, 1])
                extra = 10*(stroke/abs(sy))/109.8
                for index in (11, 12, 13):
                    ds[index][1][:, 1] *= (30+extra)/40
                apply_segments(c, ds, matrix)
                clear_hints(layer); changed[style].add(name)
            # Italic e and its ligatures have a curved cross-stroke, with a
            # different topology from upright e. Lower both edges and their
            # adjacent handles along the italic slant.
            if style == 'Ita':
                for name in ('e', 'ie-cy', 'eturned', 'ereversed', 'ae', 'oe', 'aeTurned', 'aeTurnedmod', 'oeTurned'):
                    layer = master(glyphs[name], black)
                    cs = contours(layer)
                    c = next((c for c in cs if len(c['nodes']) in (13, 14)), None)
                    if c is None:
                        continue
                    lo, hi = bounds(c); scale = (hi[1]-lo[1])/(1070 if black else 1006)
                    if name in ('eturned', 'aeTurned', 'aeTurnedmod', 'oeTurned'):
                        scale = -scale
                    length = len(c['nodes'])
                    stroke = (20 if not black else 200) if length == 13 else (18 if not black else 188)
                    regular_stroke = 117.2 if length == 13 else 109.8
                    lower = -30 - 10*stroke/regular_stroke
                    handle = lower*25/40
                    if length == 13:
                        if name == 'ereversed':
                            moves = {0: [-30], 1: [-20, 0, 0], 12: [0, handle, lower]}
                        else:
                            moves = {0: [lower], 1: [handle, 0, 0], 12: [0, -20, -30]}
                    else:
                        moves = {10: [0, -20, -30], 11: [lower], 12: [handle, 0, 0]}
                    for i, ys in moves.items():
                        p = points(c['nodes'][i]); assert len(p) == len(ys)
                        dy = np.array(ys)*scale
                        p[:, 1] += dy; p[:, 0] += .1228*dy
                        c['nodes'][i] = node_text(p, ' s' if ' s' in c['nodes'][i] else '')
                    clear_hints(layer); changed[style].add(name)
            # The horizontally mirrored e has reverse node order.
            if style == 'Upr':
                layer = master(glyphs['ereversed'], black)
                e = master(glyphs['e'], black)
                contours(layer)[0]['nodes'] = transformed_contour(contours(e)[0], np.diag([-1., 1.]), (e['advanceWidth'], 0), reverse=True)['nodes']
                clear_hints(layer); changed[style].add('ereversed')
            # Stem variants retain their own height; distinct descending hooks
            # and the connected ls/lz digraphs retain their existing terminals.
            tail = make_tail(original['Upr'], original['Ita'] if style == 'Ita' else None, black)
            ol = contours(master(original[style]['l'], black))[0]
            base_delta = master(original[style]['l.ss05'], black)['advanceWidth'] - master(original[style]['l'], black)['advanceWidth']
            for name in ('l', 'l.ss05', 'l.sups', 'lmod', 'lbelt', 'f_l', 'f_f_l'):
                layer = master(glyphs[name], black)
                cs = contours(layer)
                if name == 'l.ss05':
                    cs[0]['nodes'] = copy.deepcopy(tail['nodes']); delta = 0
                else:
                    c = next(c for c in cs if len(c['nodes']) == 4 and all(len(points(n)) == 1 for n in c['nodes']) and (bounds(c)[1][1]-bounds(c)[0][1]) > 500)
                    sx = replace_l_stem(c, ol, tail)
                    delta = round(base_delta*sx)
                    layer['advanceWidth'] += delta
                clear_hints(layer); changed[style].add(name)
                widths[style].setdefault(name, {})[layer['name']] = delta
        # Propagate dependencies and spacing. Diacritics keep their offsets;
        # the second letter in lj moves with the widened first letter.
        while True:
            added = False
            for name, g in glyphs.items():
                if name in changed[style]:
                    continue
                refs = {e['component']['glyphName'] for l in g['layers']
                        for e in l.get('elements', []) if 'component' in e}
                if not refs.intersection(changed[style]):
                    continue
                changed[style].add(name); added = True
                for black in (False, True):
                    layer = master(g, black)
                    delta = sum(widths[style].get(r, {}).get(layer['name'], 0) for r in refs)
                    if delta:
                        layer['advanceWidth'] += delta
                        widths[style].setdefault(name, {})[layer['name']] = delta
                    if name == 'lj':
                        for e in layer['elements']:
                            if e.get('component', {}).get('glyphName') == 'j':
                                e.setdefault('transform', {})['xOffset'] = e.get('transform', {}).get('xOffset', 0) + delta
                    clear_hints(layer)
            if not added:
                break
    report = {'reference': str(REGULAR.relative_to(ROOT)), 'styles': {}}
    for style in fonts:
        actual = sorted(n for n in changed[style] if original[style][n] != revised[style][n])
        report['styles'][style] = {'glyphs': sorted(changed[style]), 'direct_or_metrics': actual, 'width_changes': widths[style]}
        save_changed_glyphs(paths[style], original[style], revised[style], actual)
        print(style, len(changed[style]), 'affected glyphs;', len(actual), 'source blocks updated')
    MANIFEST.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    apply()
