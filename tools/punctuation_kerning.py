"""Fira's positive l/punctuation adjustments, scaled to Lato's 2000 UPM."""
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildLookup, buildPairPosGlyphs, buildValue
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder


def adjustment(policy, right, design):
    stops = policy['curves'][policy['rights'][right]]
    for (a, va), (b, vb) in zip(stops, stops[1:]):
        if a <= design <= b:
            return otRound(va + (vb - va) * (design - a) / (b - a))
    raise ValueError(design)


def remove_master_adjustments(designspace, style, policy):
    """The variable exporter adds the exact nine-weight curve after compiling.

    Editable Glyphs sources retain punctuation kerning at their four masters.
    Remove just those additions in memory to avoid applying them twice.
    """
    if not policy:
        return
    axis = designspace.axes[0].name
    for descriptor in designspace.sources:
        if descriptor.layerName:
            continue
        design = descriptor.location[axis]
        for left in policy['lefts'][style]:
            for right in policy['rights']:
                descriptor.font.kerning[left, right] -= adjustment(policy, right, design)


def append_variable_adjustments(font, style, policy):
    """Append positive adjustments without touching existing kerning or widths.

    Use triangular supports at all nine named weights. Integer deltas from
    Regular give exact values at every stop, including the intermediate
    weights that have only sparse outline layers in the Glyphs sources.
    Call once on a fresh compiled font (or the pre-migration binary).
    """
    if not policy:
        return
    weights = list(range(100, 901, 100))
    locations = [font.normalizeLocation({'wght': w})['wght'] for w in weights]
    default = weights.index(400)
    supports = []
    indices = []
    for i, value in enumerate(locations):
        if i == default:
            continue
        supports.append({'wght': (locations[max(i - 1, 0)], value,
                                  locations[min(i + 1, len(locations) - 1)])})
        indices.append(i)
    builder = OnlineVarStoreBuilder(['wght'])
    builder.setSupports(supports)
    old_store = font['GDEF'].table.VarStore
    outer_offset = len(old_store.VarData)
    values = {}
    for group, stops in policy['curves'].items():
        assert len(stops) == len(weights)
        base = stops[default][1]
        deltas = [stops[i][1] - base for i in indices]
        fields = {'XAdvance': base}
        if any(deltas):
            index = builder.storeDeltas(deltas) + (outer_offset << 16)
            fields['XAdvDevice'] = buildVarDevTable(index)
        values[group] = fields
    additions = builder.finish()
    region_offset = len(old_store.VarRegionList.Region)
    old_store.VarRegionList.Region.extend(additions.VarRegionList.Region)
    old_store.VarRegionList.RegionCount = len(old_store.VarRegionList.Region)
    for data in additions.VarData:
        data.VarRegionIndex = [i + region_offset for i in data.VarRegionIndex]
        old_store.VarData.append(data)
    old_store.VarDataCount = len(old_store.VarData)
    pairs = {(left, right): (buildValue(values[group]), None)
             for left in policy['lefts'][style]
             for right, group in policy['rights'].items()}
    lookup = buildLookup(buildPairPosGlyphs(pairs, font.getReverseGlyphMap()), flags=8)
    table = font['GPOS'].table
    index = len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(lookup)
    table.LookupList.LookupCount = index + 1
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag == 'kern':
            record.Feature.LookupListIndex.append(index)
            record.Feature.LookupCount = len(record.Feature.LookupListIndex)
