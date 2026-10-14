"""Pair spacing for the widened Lato26 l; preserve the original layout lookups."""
import base64
import json
from functools import lru_cache
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.otlLib.builder import buildLookup, buildPairPosGlyphs, buildValue
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'sources/data/lowercase-spacing.json'


def pair_advance(font, left, right):
    """Read the additive x advance in the font's existing kern feature."""
    if 'GPOS' not in font:
        return 0
    table = font['GPOS'].table
    indices = {i for r in table.FeatureList.FeatureRecord if r.FeatureTag == 'kern'
               for i in r.Feature.LookupListIndex}
    value = 0
    for i in sorted(indices):
        lookup = table.LookupList.Lookup[i]
        for sub in lookup.SubTable:
            kind = lookup.LookupType
            if kind == 9:
                kind, sub = sub.ExtensionLookupType, sub.ExtSubTable
            if kind != 2 or left not in sub.Coverage.glyphs:
                continue
            if sub.Format == 1:
                pairs = sub.PairSet[sub.Coverage.glyphs.index(left)].PairValueRecord
                pair = next((p for p in pairs if p.SecondGlyph == right), None)
                if pair is None:
                    continue
            else:
                pair = sub.Class1Record[sub.ClassDef1.classDefs.get(left, 0)].Class2Record[
                    sub.ClassDef2.classDefs.get(right, 0)]
            value += getattr(pair.Value1, 'XAdvance', 0) if pair.Value1 else 0
            break  # First matching subtable in a lookup wins.
    return value


def strip_spacing(font, metadata):
    """Remove only this revision's final lookup, making rebuilds idempotent."""
    if 'GPOS' not in font:
        assert not metadata['had_gpos']
        return
    table = font['GPOS'].table
    count = metadata['lookups']
    if len(table.LookupList.Lookup) == count:
        return
    assert len(table.LookupList.Lookup) == count+1
    if count == 0:
        del font['GPOS']
        if metadata['had_gpos']:
            font['GPOS'] = newTable('GPOS')
            font['GPOS'].decompile(base64.b64decode(metadata['empty_gpos']), font)
    else:
        table.LookupList.Lookup.pop()
        table.LookupList.LookupCount = count
        for record in table.FeatureList.FeatureRecord:
            feature = record.Feature
            feature.LookupListIndex = [i for i in feature.LookupListIndex if i != count]
            feature.LookupCount = len(feature.LookupListIndex)


def original_layout_metadata(font):
    result = {'had_gpos': 'GPOS' in font, 'lookups': 0}
    if 'GPOS' in font:
        result['lookups'] = len(font['GPOS'].table.LookupList.Lookup)
        if not result['lookups']:
            result['empty_gpos'] = base64.b64encode(font.getTableData('GPOS')).decode()
    return result


def spacing_strength(config, right, design):
    if right not in config.get('e_rights', []):
        return 1.
    stops = config['e_spacing_strength']
    for (a, va), (b, vb) in zip(stops, stops[1:]):
        if a <= design <= b:
            return va+(vb-va)*(design-a)/(b-a)
    raise ValueError(design)


def _base_correction(source, name, group, design, config):
    item = config['styles'][source.style]['left'][name]
    t = design/1000
    old_width = otRound(item['original_widths'][0]*(1-t)+item['original_widths'][1]*t)
    extra = item['clearance'][group]
    delta = old_width-source.width(name, design)+otRound(extra[0]*(1-t)+extra[1]*t)
    return otRound(delta*spacing_strength(config, group, design))


@lru_cache(maxsize=128)
def e_left_edge_difference(source, right, design):
    """Compare actual outlines, including the authored Regular e."""
    bounds = []
    for name in ('e', right):
        pen = BoundsPen(None)
        source.recording(name, design).replay(pen)
        bounds.append(pen.bounds[0])
    return otRound(bounds[0]-bounds[1])


def e_o_left_edge_difference(source, design):
    return e_left_edge_difference(source, 'o', design)


def optical_addition(config, group):
    return sum(item['units'] for item in config.get('optical_adjustments', {}).values()
               if group in item['rights'])


def bowl_allowance(config, style, group, design, left='l'):
    """Restore part of the added l advance, with independent style/weight curves."""
    policy = config.get('bowl_allowance', {})
    if left not in policy.get('lefts', {}).get(style, []):
        return 0
    stops = policy['additions'][style].get(group)
    if stops is None:
        return 0
    for (a, va), (b, vb) in zip(stops, stops[1:]):
        if a <= design <= b:
            return otRound(va+(vb-va)*(design-a)/(b-a))
    raise ValueError(design)


def base_correction(source, name, group, design, config):
    allowance = bowl_allowance(config, source.style, group, design, name)
    if group in config.get('match_e_spacing_rights', []):
        # Original e/c/o pair kerns agree for these left forms. Match the
        # e gap, retaining extra clearance for accents and hooks.
        base = config.get('match_e_spacing_bases', {}).get(group, 'o')
        clearance = (_base_correction(source, name, group, design, config)
                     - _base_correction(source, name, base, design, config))
        return (_base_correction(source, name, 'e', design, config)
                + e_left_edge_difference(source, base, design) + clearance + allowance)
    return (_base_correction(source, name, group, design, config)
            + optical_addition(config, group) + allowance)


@lru_cache(maxsize=4096)
def source_edges(source, name, design):
    pen = BoundsPen(None)
    source.recording(name, design).replay(pen)
    return pen.bounds[0], pen.bounds[2]


class PreviousMetrics:
    def __init__(self, source, reference):
        self.source, self.reference, self.style = source, reference, source.style

    def width(self, name, design):
        if name not in self.reference['widths']:
            return self.source.width(name, design)
        a, b = self.reference['widths'][name]
        return otRound(a+(b-a)*design/1000)

    def recording(self, *args, **kwargs):
        return self.source.recording(*args, **kwargs)


def reference_edges(reference, name, design):
    stops = reference['edges'][name]
    for a, b in zip(stops, stops[1:]):
        if a[0] <= design <= b[0]:
            t = (design-a[0])/(b[0]-a[0])
            return tuple(x+(y-x)*t for x,y in zip(a[1:],b[1:]))
    raise ValueError((name,design))


def correction(source, name, group, design, config):
    """Keep the established special-pair ink gaps after narrowing l."""
    policy = config.get('outline_spacing_reference', {}).get(source.style)
    if not policy or name not in policy['widths']:
        return base_correction(source, name, group, design, config)
    if not hasattr(source, '_previous_spacing_metrics'):
        source._previous_spacing_metrics = PreviousMetrics(source, policy)
    previous = source._previous_spacing_metrics
    delta = (previous.width(name,design)-source.width(name,design)
             + source_edges(source,name,design)[1]-reference_edges(policy,name,design)[1])
    if group in policy['edges']:
        delta += reference_edges(policy,group,design)[0]-source_edges(source,group,design)[0]
    return otRound(base_correction(previous,name,group,design,config)+delta)


def apply_spacing(font, path, source, design, output_name):
    if not CONFIG.exists():
        return
    config = json.loads(CONFIG.read_text())
    metadata = config['fonts'][str(path.relative_to(ROOT))]
    strip_spacing(font, metadata)
    spec = config['styles'][source.style]
    pairs = {}
    reference = metadata.get('outline_reference_metrics', {})
    glyph_set = font.getGlyphSet() if reference else None
    compiled_edges = {}
    def edges(name):
        if name not in compiled_edges:
            pen=BoundsPen(glyph_set);glyph_set[name].draw(pen)
            compiled_edges[name]=(pen.bounds[0],pen.bounds[2])
        return compiled_edges[name]
    for name, item in spec['left'].items():
        left = output_name(source, name, font)
        reference_name = output_name(source, item['reference'], font)
        for group, rights in spec['right'].items():
            delta = correction(source, name, group, design, config)
            for right_name in rights:
                right = output_name(source, right_name, font)
                adjustment = delta
                if left in reference:
                    previous=source._previous_spacing_metrics
                    old_width,_,old_right=reference[left]
                    compensation=old_width-font['hmtx'][left][0]+edges(left)[1]-old_right
                    if right in reference:compensation+=reference[right][1]-edges(right)[0]
                    adjustment=otRound(base_correction(previous,name,group,design,config)+compensation)
                if reference_name != left:
                    adjustment += pair_advance(font, reference_name, right)-pair_advance(font, left, right)
                # Retain zero entries too, so both interpolation masters have
                # the same pair coverage and subsequent rebuilds stay stable.
                pairs[left, right] = (buildValue({'XAdvance': adjustment}), None)
    lookup = buildLookup(buildPairPosGlyphs(pairs, font.getReverseGlyphMap()), flags=8)
    if not metadata['lookups']:
        table = otTables.GPOS(); table.Version = 0x00010000
        table.LookupList = otTables.LookupList(); table.LookupList.Lookup = []
        table.FeatureList = otTables.FeatureList(); table.FeatureList.FeatureRecord = []
        table.ScriptList = otTables.ScriptList(); table.ScriptList.ScriptRecord = []
        feature = otTables.FeatureRecord(); feature.FeatureTag = 'kern'
        feature.Feature = otTables.Feature(); feature.Feature.FeatureParams = None
        feature.Feature.LookupListIndex = []; feature.Feature.LookupCount = 0
        table.FeatureList.FeatureRecord.append(feature); table.FeatureList.FeatureCount = 1
        for tag in ('DFLT', 'cyrl', 'grek', 'latn'):
            script = otTables.ScriptRecord(); script.ScriptTag = tag
            script.Script = otTables.Script(); script.Script.LangSysRecord = []; script.Script.LangSysCount = 0
            lang = otTables.LangSys(); lang.LookupOrder = None; lang.ReqFeatureIndex = 0xFFFF
            lang.FeatureIndex = [0]; lang.FeatureCount = 1
            script.Script.DefaultLangSys = lang
            table.ScriptList.ScriptRecord.append(script)
        table.ScriptList.ScriptCount = len(table.ScriptList.ScriptRecord)
        font['GPOS'] = newTable('GPOS'); font['GPOS'].table = table
    table = font['GPOS'].table
    index = len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(lookup); table.LookupList.LookupCount = index+1
    features = [r.Feature for r in table.FeatureList.FeatureRecord if r.FeatureTag == 'kern']
    assert features
    for feature in features:
        feature.LookupListIndex.append(index); feature.LookupCount = len(feature.LookupListIndex)
