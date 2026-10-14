"""Lato 2.015 connected fi/ffi outlines and compatible nine-weight sources."""
import copy
import json
from functools import lru_cache
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen

PATH = Path(__file__).resolve().parents[1] / 'sources/data/connected-ligatures.json'
TEXTS = dict(f_i='fi', f_f_i='ffi', f_iogonek='fį', f_f_iogonek='ffį',
             f_idotbelow='fị', f_f_idotbelow='ffị', f_itildebelow='fḭ',
             f_f_itildebelow='ffḭ', f_istroke='fɨ', f_f_istroke='ffɨ')


@lru_cache(None)
def data():
    return json.loads(PATH.read_text()) if PATH.exists() else {}


def recording(style, name, design, exact=False, reverse=False):
    records = data()['styles'][style]['glyphs'][name]
    key = str(int(design))
    if exact and key in records:
        value = records[key]['quadratic']
    else:
        stops = sorted(map(int, records))
        lo, hi = next((a, b) for a, b in zip(stops, stops[1:]) if a <= design <= b)
        t = (design - lo) / (hi - lo)
        a, b = records[str(lo)]['cubic'], records[str(hi)]['cubic']
        value = [(op, [tuple(x + (y-x)*t for x,y in zip(p,q)) for p,q in zip(pa,pb)])
                 for (op,pa),(_,pb) in zip(a,b)]
    out = RecordingPen()
    for op, points in value:
        getattr(out, op)(*[tuple(p) for p in points])
    if reverse:
        reversed_recording = RecordingPen()
        out.replay(ReverseContourPen(reversed_recording))
        out = reversed_recording
    return out


def selected_hinting(font, names):
    """Rehint changed outlines without replacing unrelated glyph instructions."""
    from truetype_hinting import hint_font, HINT_TABLES
    donor = copy.deepcopy(font)
    hint_font(donor, names)
    for tag in HINT_TABLES:
        if tag == 'maxp':
            continue
        assert (font.getTableData(tag) if tag in font else None) == (donor.getTableData(tag) if tag in donor else None), tag
    for name in names:
        font['glyf'][name].program = copy.deepcopy(donor['glyf'][name].program)
    for key in ('maxZones','maxTwilightPoints','maxStorage','maxFunctionDefs',
                'maxInstructionDefs','maxStackElements','maxSizeOfInstructions'):
        setattr(font['maxp'], key, max(getattr(font['maxp'],key),getattr(donor['maxp'],key)))
