"""Restore source substitutions without changing kerning, outlines, or hints."""
import copy
import json
import re
from functools import lru_cache

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont, newTable


@lru_cache(maxsize=2)
def source_features(style, root):
    data = json.loads((root / f'sources/Lato3{style}2M.vfj').read_text())['font']
    prefix = data['openTypeFeatures'][0]['feature']
    classes = '\n'.join('@' + c['name'] + ' = [' + ' '.join(c['names']) + '];'
                        for c in data['classes']
                        if not re.search(r'@' + re.escape(c['name']) + r'\s*=', prefix))
    font = TTFont()
    font.setGlyphOrder([g['name'] for g in data['glyphs']])
    addOpenTypeFeaturesFromString(font, classes + '\n' + '\n'.join(
        f['feature'] for f in data['openTypeFeatures']))
    # No mark attachment/filtering classes need to be copied into GDEF.
    assert all(lookup.LookupFlag == 0 for lookup in font['GSUB'].table.LookupList.Lookup)
    return font


def restore_substitutions(font, source, output_name):
    if 'GSUB' in font and any(r.FeatureTag == 'liga'
                             for r in font['GSUB'].table.FeatureList.FeatureRecord):
        return False
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    order = font.getGlyphOrder()
    source_order = list(source.glyphs)
    mapping = {}
    for i, name in enumerate(source_order):
        try:
            mapping[name] = output_name(source, name, font)
        except ValueError:
            # The old CFF exports use seven historical production spellings
            # and omit a few final helper glyphs. Their exported order is the
            # source order; verify every resolvable name before using it.
            if 'CFF ' not in font:
                raise
            if i < len(order):
                mapping[name] = order[i]
    if 'CFF ' in font:
        assert all(order[i] == mapping[name] for i, name in enumerate(source_order[:len(order)]))
    assert len(set(mapping.values())) == len(mapping)
    scratch = copy.deepcopy(source_features(source.style, root))
    options = Options()
    options.layout_features = ['*']
    options.layout_closure = False
    subsetter = Subsetter(options)
    subsetter.populate(glyphs=mapping)
    subsetter.subset(scratch)
    inverse = {v: k for k, v in mapping.items()}
    # Compile with target glyph IDs, then decode the same IDs with its names.
    scratch.setGlyphOrder([inverse.get(n, n) for n in order])
    table = newTable('GSUB')
    table.decompile(scratch['GSUB'].compile(scratch), font)
    font['GSUB'] = table
    return True
