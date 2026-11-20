#!/usr/bin/env python3
"""Verify default upstream outlines/layout and opt-in Lato26 forms."""
import importlib
import json
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.misc.roundTools import otRound
from lowercase_kerning import pair_advance
from punctuation_kerning import adjustment
from glyphsLib import GSFont

build = importlib.import_module('47_build_upstream_ss05')
ROOT, CACHE = build.ROOT, build.CACHE


@lru_cache(maxsize=4)
def shaping_font(path):
    return hb.Face(path.read_bytes()), TTFont(path)


def shape(path, text, weight, ss05=False):
    face, tt = shaping_font(path)
    font = hb.Font(face)
    font.set_variations({'wght': weight})
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(font, buf, {'ss05':ss05})
    return [(tt.getGlyphName(g.codepoint), p.x_advance, p.x_offset, p.y_offset)
            for g,p in zip(buf.glyph_infos,buf.glyph_positions)]


def main(styles=("Upr", "Ita")):
    result = {'status':'passed','styles':{}}
    for style, suffix in [('Upr',''),('Ita','Italic')]:
        if style not in styles:
            continue
        path = ROOT/f'build/Lato26-Variable/Lato26-Variable{suffix}.ttf'
        base_path = CACHE/f'upstream-{style}.ttf'
        current, original = TTFont(path), TTFont(base_path)
        source = GSFont(ROOT/f'sources/Lato26-{"Italic" if suffix else "Upright"}.glyphs')
        for instance in source.instances:
            assert instance.customParameters['Autohint']
            assert instance.customParameters['TTFAutohint options'] == build.GLYPHS_HINT_OPTIONS
        mapping = dict(source.userData['Lato26.ss05']['alternates'])
        spacing_path = CACHE/f'spacing-baseline-{style}.ttf'
        spacing_path.write_bytes(build.git_bytes('3cb00ee1b', str(path.relative_to(ROOT))))
        donor = build.load_donor(style)
        # Check the authored alternate paths and widths, including all accents,
        # at all four masters before quadratic conversion.
        for name, alt in mapping.items():
            for master in source.masters:
                a, b = source.glyphs[alt].layers[master.id], donor.glyphs[name].layers[master.id]
                assert a.width == b.width, (style,name,'advance')
                assert [[(tuple(n.position),n.type,n.smooth) for n in p.nodes] for p in a.paths] == [[(tuple(n.position),n.type,n.smooth) for n in p.nodes] for p in b.paths], (style,name,'paths')
                assert [(c.name,tuple(c.transform)) for c in a.components] == [
                    (mapping.get(c.name,c.name),tuple(c.transform)) for c in b.components], (style,name,'components')
        policy = json.loads(build.git_bytes(build.DONOR, 'sources/data/lowercase-spacing.json'))['punctuation_allowance']
        assert not set(('J.ss05', 'Jcircumflex.ss05', 'Jstroke.ss05', 'LJ.ss05', 'NJ.ss05')) & set(current.getGlyphOrder())
        unchanged = set(original.getGlyphOrder())-set(mapping.values())
        for weight in sorted(set(range(100,901,100)) | {250,550,850}):
            a = instantiateVariableFont(current,{'wght':weight},inplace=False)
            b = instantiateVariableFont(original,{'wght':weight},inplace=False)
            for name in unchanged:
                assert a['hmtx'][name] == b['hmtx'][name], (style,weight,name,'metrics')
                ga,gb=a['glyf'][name],b['glyf'][name]
                assert ga.getCoordinates(a['glyf']) == gb.getCoordinates(b['glyf']), (style,weight,name,'outline')
            if weight % 100 == 0:
                design = list(build.build.WEIGHTS.values())[weight//100-1]
                masters = sorted(source.masters, key=lambda m:m.axes[0])
                lo, hi = next((lo, hi) for lo, hi in zip(masters, masters[1:]) if lo.axes[0] <= design <= hi.axes[0])
                t = (design-lo.axes[0])/(hi.axes[0]-lo.axes[0])
                for left in policy['lefts'][style]:
                    if left not in mapping:
                        continue
                    for right in policy['rights']:
                        ka = build.effective(donor,lo.id,left,right)-adjustment(policy,right,lo.axes[0])
                        kb = build.effective(donor,hi.id,left,right)-adjustment(policy,right,hi.axes[0])
                        expected = otRound(ka*(1-t)+kb*t)+adjustment(policy,right,design)
                        actual = pair_advance(a,mapping[left],right)
                        assert abs(actual-expected) <= 1, (style,weight,left,right,actual,expected)
        texts = ['Il1 a e l á é ł ľ æ œ fl ffi ffl la le lo lc ll lt l.',
                 'The quick brown fox jumps over the lazy dog. A little elegant letter.',
                 'αβγ Ελληνικά Кириллица аллея', 'a\u0301 e\u0301 l\u0301']
        # Every encoded character also exercises upstream substitutions and
        # attachment. Compare names rather than glyph IDs (alternates append).
        texts.append(''.join(chr(c) for c in sorted(original.getBestCmap())))
        for weight in range(100,901,50):
            for text in texts:
                assert shape(path,text,weight) == shape(base_path,text,weight), (style,weight,'default shaping')
            for char in ('a','e','l','á','é','ł','ľ'):
                before=shape(path,char,weight)
                after=shape(path,char,weight,True)
                assert after[0][0] == mapping.get(before[0][0],before[0][0]), (style,weight,char,after)
            for text in ('fl','ffl'):
                before=shape(base_path,text,weight,True)
                after=shape(path,text,weight,True)
                assert len(after) == 2 and after[-1][0] == 'l.ss05', (style,weight,text,after)
                assert [p[0] for p in after] == [mapping.get(p[0],p[0]) for p in before], (style,weight,text,after)
            assert shape(path,'ffi',weight,True) == shape(base_path,'ffi',weight,True)
            for text in ('J', 'Ĵ', 'Ɉ', 'Ǉ', 'Ǌ', 'Ĳ', 'lJ', 'Jl', 'Ja', 'J\u0302'):
                before = shape(base_path, text, weight, True)
                after = shape(path, text, weight, True)
                for old, new in zip(before, after, strict=True):
                    expected_name = mapping.get(old[0], old[0])
                    assert new[0] == expected_name, (style, weight, text, old, new)
            assert [item[1:] for item in shape(path, 'JJ', weight, True)] == [
                item[1:] for item in shape(path, 'JJ', weight)]
            for text in ('J\u0301', 'J\u0307', 'J\u0323', 'J\u0301\u0323'):
                before = shape(path, text, weight)
                after = shape(path, text, weight, True)
                assert before == after, (style, weight, text, 'mark attachment')
            for text in ('lJ', 'lI', 'lJlI', 'lJlJ', 'lIlI', 'FillJitter', 'Jl', 'Il', 'JJ', 'II',
                         'la', 'le', 'lo', 'lĴ', 'lɈ', 'lǇ', 'lǊ', 'Ĳ'):
                before = shape(spacing_path, text, weight, True)
                after = shape(path, text, weight, True)
                expected = []
                for index, item in enumerate(before):
                    extra = build.SS05_CAPITAL_SPACING[before[index+1][0]] if (
                        item[0] == 'l.ss05' and index+1 < len(before)
                        and before[index+1][0] in ('J', 'I.ss05')) else 0
                    expected.append((item[0], item[1]+extra, item[2], item[3]))
                assert after == expected, (style, weight, text, before, after)
        for master in source.masters:
            for right in ('J', 'I.ss05'):
                pair = source.userData['Lato26.ss05']['capitalSpacingPairs'][master.id][right]
                assert pair['after']-pair['before'] == build.SS05_CAPITAL_SPACING[right]
                assert build.effective(source, master.id, 'l.ss05', right) == pair['after']
            for left in ['l','f_l','f_f_l']:
                for char in 'abcdefghijklmnopqrstuvwxyz.,:;!?':
                    right = current.getBestCmap()[ord(char)]
                    alt = mapping[left]
                    other = mapping.get(right,right)
                    extra = build.SS05_LO_SPACING if (left, right) == ('l', 'o') else 0
                    assert build.effective(source,master.id,alt,other) == build.effective(donor,master.id,left,right) + extra, (style,left,right)
        static_fonts = []
        for weight, name in enumerate(build.build.WEIGHTS, 1):
            label = 'Italic' if suffix and name == 'Regular' else name+suffix
            for extension in ('ttf', 'otf'):
                static_path = ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{label}.{extension}'
                if extension == 'ttf':
                    info = TTFont(static_path)['TTFA'].data.decode()
                    for setting in ('gray-stem-width-mode = quantized',
                                    'gdi-cleartype-stem-width-mode = strong',
                                    'dw-cleartype-stem-width-mode = quantized',
                                    'fallback-script = latn',
                                    'windows-compatibility = 0'):
                        assert setting in info, (static_path, setting)
                for enabled in (False, True):
                    for text in ('lJ', 'lI', 'FillJitter', 'fl', 'ffl', 'ffi', 'J\u0301\u0323'):
                        expected = shape(path, text, weight*100, enabled)
                        actual = shape(static_path, text, weight*100, enabled)
                        assert actual == expected, (static_path, text, enabled, actual, expected)
                static_fonts.append(static_path.name)
        result['styles'][style]={'unchanged_upstream_glyphs':len(unchanged),'alternate_glyphs':len(mapping),
            'capital_spacing_addition':build.SS05_CAPITAL_SPACING,
            'capital_spacing_pairs':['l.ss05 J', 'l.ss05 I.ss05'],
            'ss05_ligatures':{'fl':'f + l.ss05', 'ffl':'f_f + l.ss05', 'ffi':'upstream'},
            'validated_static_fonts':static_fonts,
            'static_hinting_options':build.HINT_OPTIONS,
            'punctuation_curve_weights':list(range(100,901,100)), 'outline_weights':sorted(set(range(100,901,100)) | {250,550,850}), 'shaping_weights':list(range(100,901,50))}
        print(style, result['styles'][style], flush=True)
    for filename in ('upstream-ss05-validation.json', 'variable-ligature-validation.json'):
        (ROOT/'build/proofs'/filename).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
