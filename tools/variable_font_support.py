"""HarfBuzz variation shaping and variation-aware pair measurements for proofs."""
import ctypes as C

from fontTools.varLib.varStore import VarStoreInstancer
from vector_font_proofs import (Face, bind, ptr, uint, buffer_create, buffer_destroy,
                                add_utf8, guess, shape, get_infos, get_positions)


class Variation(C.Structure):
    _fields_ = [('tag', C.c_uint32), ('value', C.c_float)]


class Feature(C.Structure):
    _fields_ = [('tag', C.c_uint32), ('value', C.c_uint32),
                ('start', C.c_uint32), ('end', C.c_uint32)]


set_variations = bind('hb_font_set_variations', None, [ptr, C.POINTER(Variation), uint])


class ProofFace(Face):
    def __init__(self, path, weight=None):
        super().__init__(path)
        if weight is not None:
            value = Variation(int.from_bytes(b'wght', 'big'), weight)
            set_variations(self.font, C.byref(value), 1)
            self.glyphs = self.tt.getGlyphSet(location={'wght': weight})

    def shaped(self, text, liga=True):
        buffer = buffer_create()
        try:
            encoded = text.encode('utf-8')
            add_utf8(buffer, encoded, len(encoded), 0, len(encoded))
            guess(buffer)
            feature = Feature(int.from_bytes(b'liga', 'big'), int(liga), 0, 0xffffffff)
            shape(self.font, buffer, C.byref(feature), 1)
            count = uint()
            infos = get_infos(buffer, C.byref(count))
            positions = get_positions(buffer, C.byref(count))
            return [(infos[i].codepoint, positions[i].x_advance, positions[i].y_advance,
                     positions[i].x_offset, positions[i].y_offset) for i in range(count.value)]
        finally:
            buffer_destroy(buffer)


class PairValues:
    def __init__(self, font, weight):
        table = font['GPOS'].table
        indices = {i for r in table.FeatureList.FeatureRecord if r.FeatureTag == 'kern'
                   for i in r.Feature.LookupListIndex}
        self.lookups = []
        for i in sorted(indices):
            lookup = table.LookupList.Lookup[i]
            subs = []
            for sub in lookup.SubTable:
                kind = lookup.LookupType
                if kind == 9:
                    kind, sub = sub.ExtensionLookupType, sub.ExtSubTable
                if kind == 2:
                    subs.append((sub, {n: j for j, n in enumerate(sub.Coverage.glyphs)}))
            self.lookups.append(subs)
        self.variations = VarStoreInstancer(font['GDEF'].table.VarStore, font['fvar'].axes,
                                           font.normalizeLocation({'wght': weight}))

    def __call__(self, left, right):
        value = 0
        for lookup in self.lookups:
            for sub, coverage in lookup:
                if left not in coverage:
                    continue
                if sub.Format == 1:
                    pair = next((p for p in sub.PairSet[coverage[left]].PairValueRecord if p.SecondGlyph == right), None)
                    if pair is None:
                        continue
                else:
                    pair = sub.Class1Record[sub.ClassDef1.classDefs.get(left, 0)].Class2Record[
                        sub.ClassDef2.classDefs.get(right, 0)]
                if pair.Value1:
                    value += getattr(pair.Value1, 'XAdvance', 0)
                    device = getattr(pair.Value1, 'XAdvDevice', None)
                    if device is not None:
                        assert device.DeltaFormat == 0x8000
                        value += self.variations[(device.StartSize << 16) | device.EndSize]
                break
        return value
