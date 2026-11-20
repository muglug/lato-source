"""Published Lato 2.015 line metrics, shared by static and variable exports.

Glyphs' design ascender/descender (1610/-390) do not specify the hhea or
Windows line box. Leaving those export values implicit produces 2010/-390
instead of 1974/-426: the same 2400-unit height with a 36-unit baseline shift.
"""

FIELDS = {
    'hheaAscender': ('hhea', 'ascent', 1974),
    'hheaDescender': ('hhea', 'descent', -426),
    'hheaLineGap': ('hhea', 'lineGap', 0),
    'winAscent': ('OS/2', 'usWinAscent', 1974),
    'winDescent': ('OS/2', 'usWinDescent', 426),
    'typoAscender': ('OS/2', 'sTypoAscender', 1610),
    'typoDescender': ('OS/2', 'sTypoDescender', -390),
    'typoLineGap': ('OS/2', 'sTypoLineGap', 400),
}
GLYPHS_PARAMETERS = {name: value for name, (_, _, value) in FIELDS.items()}
GLYPHS_PARAMETERS['Use Typo Metrics'] = False
UFO_FIELDS = {
    'hheaAscender': 'openTypeHheaAscender',
    'hheaDescender': 'openTypeHheaDescender',
    'hheaLineGap': 'openTypeHheaLineGap',
    'winAscent': 'openTypeOS2WinAscent',
    'winDescent': 'openTypeOS2WinDescent',
    'typoAscender': 'openTypeOS2TypoAscender',
    'typoDescender': 'openTypeOS2TypoDescender',
    'typoLineGap': 'openTypeOS2TypoLineGap',
}


def metrics(font):
    result = {name: getattr(font[tag], field) for name, (tag, field, _) in FIELDS.items()}
    result['Use Typo Metrics'] = bool(font['OS/2'].fsSelection & 0x80)
    return result


def assert_published_metrics(font):
    assert font['head'].unitsPerEm == 2000
    assert metrics(font) == GLYPHS_PARAMETERS, metrics(font)
    if 'MVAR' in font:
        assert not {'hasc', 'hdsc', 'hlgp', 'hcla', 'hcld'} & {
            v.ValueTag for v in font['MVAR'].table.ValueRecord
        }, 'Published Lato has constant line metrics across weights'


def assert_designspace_metrics(designspace):
    for source in designspace.sources:
        if source.layerName:
            continue
        for name, field in UFO_FIELDS.items():
            assert getattr(source.font.info, field) == GLYPHS_PARAMETERS[name], (source.name, field)
        assert 7 not in (source.font.info.openTypeOS2Selection or [])
