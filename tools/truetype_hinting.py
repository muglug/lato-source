"""Hint desktop outlines with the exact engine/settings of released Lato 2.015.

Recreate instructions for the current point topology rather than transplanting
programs from a different outline. Source masters stay unhinted.
"""
import copy
import io
import os
from pathlib import Path
import subprocess
import tempfile
from functools import lru_cache

from fontTools.ttLib import TTFont
from bold_a_hint_controls import bold_a_controls, link_bold_a_joins
from install_ttfautohint_13 import DESTINATION

OPTIONS = ['--no-info', '--ttfa-table', '--windows-compatibility',
           '--increase-x-height=14', '--strong-stem-width=gGD',
           '--fallback-script=latn',
           '--hinting-range-min=8', '--hinting-range-max=50', '--hinting-limit=200']
# Glyphs bundles a newer engine: use the current spelling of strong widths
# in all three render modes. The pinned 1.3 executable still needs -w gGD.
GLYPHS_OPTIONS = ' '.join('--stem-width-mode=sss' if o == '--strong-stem-width=gGD' else o
                         for o in OPTIONS if o != '--ttfa-table')
HINT_TABLES = ('fpgm', 'prep', 'cvt ', 'gasp', 'maxp', 'TTFA')


def configure_glyphs_instances(text):
    """Patch export settings in the authored static Glyphs file only."""
    import openstep_plist
    data = openstep_plist.loads(text, use_numbers=True)
    instances = copy.deepcopy(data['instances'])
    for instance in instances:
        params = instance.setdefault('customParameters', [])
        params[:] = [p for p in params if p['name'] not in ('Autohint','TTFAutohint options')]
        params.extend([{'name':'Autohint','value':1},
                       {'name':'TTFAutohint options','value':GLYPHS_OPTIONS}])
    start = text.index('\ninstances = ')+len('\ninstances = ')
    assert text[start] == '('
    depth = 0; quoted = escaped = False
    for end in range(start,len(text)):
        ch=text[end]
        if ch=='"' and not escaped:quoted=not quoted
        if not quoted:
            if ch=='(':depth+=1
            elif ch==')':
                depth-=1
                if depth==0:break
        escaped=ch=='\\' and not escaped
    result=text[:start]+openstep_plist.dumps(instances,indent=0,sort_keys=False)+text[end+1:]
    parsed=openstep_plist.loads(result, use_numbers=True)
    assert parsed['glyphs']==data['glyphs']
    return result


@lru_cache(maxsize=1)
def engine_path():
    path = Path(os.environ.get('TTFAUTOHINT_13', DESTINATION)).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError('Install ttfautohint 1.3 with tools/install_ttfautohint_13.py, '
                           'or set TTFAUTOHINT_13 to a native 1.3 executable.')
    version = subprocess.run([str(path), '--version'], capture_output=True,
                             text=True, check=True).stdout.splitlines()[0]
    if version != 'ttfautohint 1.3':
        raise RuntimeError(f'Expected ttfautohint 1.3; found {version}')
    return path


def engine_version():
    engine_path()
    return 'ttfautohint 1.3'


def run_engine(source, destination, controls=()):
    """Run the pinned recipe; also used to verify the reference font programs."""
    with tempfile.TemporaryDirectory(prefix='lato-hint-controls-') as directory:
        options = list(OPTIONS)
        if controls:
            control = Path(directory) / 'bold-a.txt'
            control.write_text('\n'.join(controls) + '\n')
            options.extend(['--control-file', str(control)])
        subprocess.run([str(engine_path()), *options, str(source), str(destination)],
                       capture_output=True, check=True)


def bytecode(glyph):
    return bytes(glyph.program.getBytecode()) if hasattr(glyph, 'program') else b''


def assert_same_outlines(before, after):
    assert before.getGlyphOrder() == after.getGlyphOrder()
    for name in before.getGlyphOrder():
        a, b = before['glyf'][name], after['glyf'][name]
        assert a.numberOfContours == b.numberOfContours, name
        if a.numberOfContours > 0:
            assert a.coordinates == b.coordinates, name
            assert a.endPtsOfContours == b.endPtsOfContours, name
            assert a.flags == b.flags, name
        elif a.isComposite():
            assert [c.getComponentInfo() for c in a.components] == [c.getComponentInfo() for c in b.components], name
            assert [c.flags for c in a.components] == [c.flags for c in b.components], name


def hint_font(font, required_glyphs=()):
    """Replace hint programs without changing geometry, widths, or layout."""
    assert 'glyf' in font and 'fvar' not in font
    required_glyphs = list(required_glyphs)
    controls = bold_a_controls(font)
    with tempfile.TemporaryDirectory(prefix='lato-2015-hints-') as directory:
        source, destination = Path(directory)/'input.ttf', Path(directory)/'hinted.ttf'
        font.save(source)
        run_engine(source, destination, controls)
        hinted = TTFont(io.BytesIO(destination.read_bytes()), recalcTimestamp=False)
    assert_same_outlines(font, hinted)
    assert font['hmtx'].metrics == hinted['hmtx'].metrics
    for tag in ('GPOS', 'GSUB', 'GDEF', 'cmap', 'OS/2', 'hhea'):
        if tag in font:
            assert font.getTableData(tag) == hinted.getTableData(tag), tag
    for name in required_glyphs:
        assert bytecode(hinted['glyf'][name]), ('missing revised-glyph instructions', name)
    linked_forms = link_bold_a_joins(hinted)
    counts = {'glyphs':len(font.getGlyphOrder()),
              'glyphs_with_instructions':sum(bool(bytecode(hinted['glyf'][n])) for n in hinted.getGlyphOrder()),
              'revised_glyphs_with_instructions':len(required_glyphs),
              'instruction_bytes':sum(len(bytecode(hinted['glyf'][n])) for n in hinted.getGlyphOrder()),
              'hinting_reference':'Lato 2.015',
              'bold_a_controlled_forms':len(controls),
              'bold_a_linked_join_forms':linked_forms}
    # Preserve the existing container, metadata, naming and layout bytes.
    # The donor's glyph geometry has been verified point-for-point above.
    font['glyf'] = hinted['glyf']
    for tag in HINT_TABLES:
        font[tag] = copy.deepcopy(hinted[tag])
    # Point-size dependence and advance-width behavior describe the new
    # programs; other original header flags remain intact.
    mask = 0x1c
    font['head'].flags = (font['head'].flags & ~mask) | (hinted['head'].flags & mask)
    for tag in ('hdmx', 'VDMX', 'LTSH'):
        if tag in font:
            del font[tag]
    return counts
