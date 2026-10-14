"""FreeType RGB subpixel proof renderer; explicitly not Microsoft DirectWrite.

HarfBuzz supplies font-native kerning and fractional advances. FreeType executes
existing TrueType instructions at the requested ppem, then a 3x horizontal
transform provides coverage samples for a five-tap LCD filter. No automatic
hinting is added to glyphs that lack instructions. Gamma is a proof setting,
not an assertion about the viewer's Windows settings.
"""
import ctypes as C
import ctypes.util
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageColor
from scipy.ndimage import convolve1d

from vector_font_proofs import face as shaped_face


class Vector(C.Structure):
    _fields_ = [('x', C.c_long), ('y', C.c_long)]


class Matrix(C.Structure):
    _fields_ = [(n, C.c_long) for n in ('xx', 'xy', 'yx', 'yy')]


class Generic(C.Structure):
    _fields_ = [('data', C.c_void_p), ('finalizer', C.c_void_p)]


class Bitmap(C.Structure):
    _fields_ = [('rows', C.c_uint), ('width', C.c_uint), ('pitch', C.c_int),
                ('buffer', C.POINTER(C.c_ubyte)), ('num_grays', C.c_ushort),
                ('pixel_mode', C.c_ubyte), ('palette_mode', C.c_ubyte),
                ('palette', C.c_void_p)]


class Metrics(C.Structure):
    _fields_ = [(n, C.c_long) for n in ('width', 'height', 'horiBearingX',
                'horiBearingY', 'horiAdvance', 'vertBearingX', 'vertBearingY', 'vertAdvance')]


class Outline(C.Structure):
    _fields_ = [('n_contours', C.c_short), ('n_points', C.c_short),
                ('points', C.POINTER(Vector)), ('tags', C.POINTER(C.c_ubyte)),
                ('contours', C.POINTER(C.c_short)), ('flags', C.c_int)]


class Slot(C.Structure):
    # Public prefix of FT_GlyphSlotRec, through its outline.
    _fields_ = [('library', C.c_void_p), ('face', C.c_void_p), ('next', C.c_void_p),
                ('glyph_index', C.c_uint), ('generic', Generic), ('metrics', Metrics),
                ('linearHoriAdvance', C.c_long), ('linearVertAdvance', C.c_long),
                ('advance', Vector), ('format', C.c_uint), ('bitmap', Bitmap),
                ('bitmap_left', C.c_int), ('bitmap_top', C.c_int), ('outline', Outline)]


class FaceRecord(C.Structure):
    # Public prefix of FT_FaceRec, through its default glyph slot.
    _fields_ = [(n, C.c_long) for n in ('num_faces', 'face_index', 'face_flags',
                                       'style_flags', 'num_glyphs')] + [
        ('family_name', C.c_char_p), ('style_name', C.c_char_p),
        ('num_fixed_sizes', C.c_int), ('available_sizes', C.c_void_p),
        ('num_charmaps', C.c_int), ('charmaps', C.c_void_p), ('generic', Generic),
        ('bbox', C.c_long * 4), ('units_per_EM', C.c_ushort),
    ] + [(n, C.c_short) for n in ('ascender', 'descender', 'height', 'max_advance_width',
                                 'max_advance_height', 'underline_position', 'underline_thickness')] + [
        ('glyph', C.POINTER(Slot))]


bundled = list((Path(PIL.__file__).parent / '.dylibs').glob('libfreetype*.dylib'))
ft = C.CDLL(str(bundled[0]) if bundled else ctypes.util.find_library('freetype'))


def bind(name, restype, args):
    fn = getattr(ft, name)
    fn.restype, fn.argtypes = restype, args
    return fn


init = bind('FT_Init_FreeType', C.c_int, [C.POINTER(C.c_void_p)])
new_face = bind('FT_New_Face', C.c_int, [C.c_void_p, C.c_char_p, C.c_long,
                                       C.POINTER(C.POINTER(FaceRecord))])
set_size = bind('FT_Set_Char_Size', C.c_int, [C.POINTER(FaceRecord), C.c_long,
                                            C.c_long, C.c_uint, C.c_uint])
transform = bind('FT_Set_Transform', None, [C.POINTER(FaceRecord),
                                          C.POINTER(Matrix), C.POINTER(Vector)])
load = bind('FT_Load_Glyph', C.c_int, [C.POINTER(FaceRecord), C.c_uint, C.c_int32])
render = bind('FT_Render_Glyph', C.c_int, [C.POINTER(Slot), C.c_int])
outline_transform = bind('FT_Outline_Transform', None, [C.POINTER(Outline), C.POINTER(Matrix)])
library = C.c_void_p()
assert init(C.byref(library)) == 0
GAMMA = 1.8
FILTER = np.array([8, 77, 86, 77, 8], dtype=np.float64) / 256


class RasterFace:
    def __init__(self, path):
        self.shape = shaped_face(str(path))
        self.handle = C.POINTER(FaceRecord)()
        assert new_face(library, str(path).encode(), 0, C.byref(self.handle)) == 0
        assert self.handle.contents.units_per_EM == self.shape.upm
        assert self.handle.contents.num_glyphs == len(self.shape.order)

    def hinted_points(self, glyph, size=16, target=3):
        """Native coordinates before proof sampling; LCD target by default."""
        assert set_size(self.handle, 0, round(size * 64), 72, 72) == 0
        matrix, delta = Matrix(65536, 0, 0, 65536), Vector(0, 0)
        transform(self.handle, C.byref(matrix), C.byref(delta))
        assert load(self.handle, self.shape.tt.getGlyphID(glyph),
                    (target << 16) | (1 << 15) | (1 << 7) | (1 << 3)) == 0
        outline = self.handle.contents.glyph.contents.outline
        return [(outline.points[i].x / 64, outline.points[i].y / 64)
                for i in range(outline.n_points)]

    @lru_cache(maxsize=4096)
    def coverage(self, text, size, mode='rgb', hinting=True):
        size = float(size)
        glyphs = self.shape.shaped(text)
        advance = sum(g[1] for g in glyphs) * size / self.shape.upm
        width, height = math.ceil(advance) + 32, math.ceil(size * 2) + 32
        baseline, margin = math.ceil(size * 1.4) + 8, 12
        sampling = 3 if mode == 'rgb' else 1
        alpha = np.zeros((height, width * sampling), dtype=np.float64)
        assert set_size(self.handle, 0, round(size * 64), 72, 72) == 0
        matrix = Matrix(65536, 0, 0, 65536)
        sampling_matrix = Matrix(sampling * 65536, 0, 0, 65536)
        cursor = 0
        for gid, ax, ay, ox, oy in glyphs:
            x = margin + (cursor + ox) * size / self.shape.upm
            origin = math.floor(x)
            delta = Vector(round((x-origin) * 64),
                           round(oy * size / self.shape.upm * 64))
            transform(self.handle, C.byref(matrix), C.byref(delta))
            # Native bytecode, LCD hinting target; never invent auto-hints.
            flags = (3 << 16) | (1 << 15) | (1 << 3)
            if not hinting:
                flags |= 1 << 1
            assert load(self.handle, gid, flags) == 0
            slot = self.handle.contents.glyph
            # Stretch only after executing the native instructions. Supplying
            # a stretched face transform before FT_Load_Glyph makes some hint
            # programs (including ttfautohint) intentionally disable hinting.
            if sampling != 1:
                outline_transform(C.byref(slot.contents.outline), C.byref(sampling_matrix))
            assert render(slot, 0) == 0  # Gray coverage after horizontal transform.
            bitmap = slot.contents.bitmap
            if bitmap.width and bitmap.rows:
                assert bitmap.pixel_mode == 2 and bitmap.pitch > 0
                raw = C.string_at(bitmap.buffer, bitmap.pitch * bitmap.rows)
                pixels = np.frombuffer(raw, dtype=np.uint8).reshape(bitmap.rows, bitmap.pitch)
                pixels = pixels[:, :bitmap.width].astype(np.float64) / 255
                left = origin * sampling + slot.contents.bitmap_left
                top = baseline - slot.contents.bitmap_top
                assert 0 <= left and 0 <= top
                assert left + bitmap.width <= alpha.shape[1] and top + bitmap.rows <= height
                target = alpha[top:top+bitmap.rows, left:left+bitmap.width]
                target[:] = 1 - (1-target) * (1-pixels)
            cursor += ax
            assert ay == 0
        if mode == 'rgb':
            alpha = convolve1d(alpha, FILTER, axis=1, mode='constant').reshape(height, width, 3)
        else:
            alpha = np.repeat(alpha[:, :, None], 3, axis=2)
        assert alpha.min() >= 0 and alpha.max() <= 1.000001
        alpha.flags.writeable = False
        return alpha, margin, baseline, advance


raster_face = lru_cache(maxsize=None)(RasterFace)


def draw_text(image, point, text, font, size, color='#202020', mode='rgb'):
    """Draw at a baseline coordinate, preserving fractional glyph positions."""
    alpha, margin, baseline, advance = raster_face(str(font)).coverage(text, size, mode)
    left, top = round(point[0]) - margin, round(point[1]) - baseline
    h, w = alpha.shape[:2]
    assert left >= 0 and top >= 0, (text, left, top)
    assert left+w <= image.width and top+h <= image.height, (text, left+w, top+h, image.size)
    region = np.asarray(image.crop((left, top, left+w, top+h)), dtype=float) / 255
    foreground = np.array(ImageColor.getrgb(color), dtype=float) / 255
    result = (region ** GAMMA * (1-alpha) + foreground ** GAMMA * alpha) ** (1/GAMMA)
    image.paste(Image.fromarray(np.round(result * 255).clip(0,255).astype('uint8')), (left,top))
    return advance
