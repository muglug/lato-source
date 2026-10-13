"""Vector PDF proof drawing with HarfBuzz shaping and exact font outlines.

Use the HarfBuzz shared library bundled with Pillow, or a system installation.
The PDF preserves GPOS/GSUB placement without depending on a viewer's shaper.
"""
import ctypes as C
import ctypes.util
from functools import lru_cache
from pathlib import Path

import PIL
from PIL import ImageFont
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as pdfcanvas


class Info(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('codepoint', 'mask', 'cluster', 'var1', 'var2')]


class Position(C.Structure):
    _fields_ = [(n, C.c_int32) for n in ('x_advance', 'y_advance', 'x_offset', 'y_offset', 'var')]


bundled = list(Path(PIL.__file__).parent.glob('.dylibs/libharfbuzz*.dylib'))
hb = C.CDLL(str(bundled[0]) if bundled else ctypes.util.find_library('harfbuzz'))


def bind(name, result, arguments):
    fn = getattr(hb, name)
    fn.restype = result
    fn.argtypes = arguments
    return fn


ptr, uint, sint = C.c_void_p, C.c_uint, C.c_int
blob_create = bind('hb_blob_create', ptr, [ptr, uint, sint, ptr, ptr])
blob_destroy = bind('hb_blob_destroy', None, [ptr])
face_create = bind('hb_face_create', ptr, [ptr, uint])
font_create = bind('hb_font_create', ptr, [ptr])
font_funcs = bind('hb_ot_font_set_funcs', None, [ptr])
font_scale = bind('hb_font_set_scale', None, [ptr, sint, sint])
buffer_create = bind('hb_buffer_create', ptr, [])
buffer_destroy = bind('hb_buffer_destroy', None, [ptr])
add_utf8 = bind('hb_buffer_add_utf8', None, [ptr, C.c_char_p, sint, uint, sint])
guess = bind('hb_buffer_guess_segment_properties', None, [ptr])
shape = bind('hb_shape', None, [ptr, ptr, ptr, uint])
get_infos = bind('hb_buffer_get_glyph_infos', C.POINTER(Info), [ptr, C.POINTER(uint)])
get_positions = bind('hb_buffer_get_glyph_positions', C.POINTER(Position), [ptr, C.POINTER(uint)])


class OutlinePen(BasePen):
    def __init__(self, glyph_set, path):
        super().__init__(glyph_set)
        self.path = path

    def _moveTo(self, p): self.path.moveTo(*p)
    def _lineTo(self, p): self.path.lineTo(*p)
    def _curveToOne(self, a, b, c): self.path.curveTo(*a, *b, *c)
    def _closePath(self): self.path.close()


class Face:
    def __init__(self, path):
        self.path = str(path)
        data = Path(path).read_bytes()
        buffer = C.create_string_buffer(data)
        blob = blob_create(buffer, len(data), 0, None, None)
        self.face = face_create(blob, 0)
        blob_destroy(blob)
        self.font = font_create(self.face)
        self.tt = TTFont(path)
        self.upm = self.tt['head'].unitsPerEm
        font_funcs(self.font)
        font_scale(self.font, self.upm, self.upm)
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.outlines = {}

    def shaped(self, text):
        buffer = buffer_create()
        try:
            encoded = text.encode('utf-8')
            add_utf8(buffer, encoded, len(encoded), 0, len(encoded))
            guess(buffer)
            shape(self.font, buffer, None, 0)
            count = uint()
            infos = get_infos(buffer, C.byref(count))
            positions = get_positions(buffer, C.byref(count))
            result = [(infos[i].codepoint, positions[i].x_advance,
                       positions[i].y_advance, positions[i].x_offset,
                       positions[i].y_offset) for i in range(count.value)]
            assert all(gid != 0 for gid, *_ in result), (self.path, text)
            return result
        finally:
            buffer_destroy(buffer)

    def outline(self, gid, canvas):
        if gid not in self.outlines:
            path = canvas.beginPath()
            self.glyphs[self.order[gid]].draw(OutlinePen(self.glyphs, path))
            self.outlines[gid] = path
        return self.outlines[gid]


face = lru_cache(maxsize=None)(Face)


class Font:
    def __init__(self, path, size):
        self.face = face(str(path))
        self.size = size
        self.ascent = ImageFont.truetype(str(path), size).getmetrics()[0]


class Document:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.canvas = pdfcanvas.Canvas(str(path), pageCompression=1)
        self.canvas.setTitle('Lato26 - outline and spacing proofs')
        self.canvas.setAuthor('Lato26 font revision')
        self.pages = 0

    def page(self, width, height):
        return Page(self, width, height)

    def save(self):
        self.canvas.save()
        print(self.path, f'{self.pages} vector proof pages')


class Page:
    def __init__(self, document, width, height):
        self.document = document
        self.canvas = document.canvas
        self.width, self.height = width, height
        scale = 612/width
        self.canvas.setPageSize((width*scale, height*scale))
        self.canvas.scale(scale, scale)
        self.canvas.setFillColor(HexColor('#faf9f6'))
        self.canvas.rect(0, 0, width, height, fill=1, stroke=0)

    def text(self, point, text, font, fill):
        shaped = font.face.shaped(text)
        # Verify the vector placements against the same RAQM shaper as PNGs.
        reference = ImageFont.truetype(font.face.path, font.face.upm).getlength(text)
        assert abs(sum(g[1] for g in shaped)-reference) <= 1.01, (text, reference, shaped)
        x, y = point
        c = self.canvas
        c.saveState()
        c.setFillColor(HexColor(fill))
        c.translate(x, self.height-y-font.ascent)
        c.scale(font.size/font.face.upm, font.size/font.face.upm)
        cursor_x = cursor_y = 0
        for gid, advance_x, advance_y, offset_x, offset_y in shaped:
            c.saveState()
            c.translate(cursor_x+offset_x, cursor_y+offset_y)
            c.drawPath(font.face.outline(gid, c), stroke=0, fill=1, fillMode=1)
            c.restoreState()
            cursor_x += advance_x
            cursor_y += advance_y
        c.restoreState()

    def line(self, points, fill):
        x0, y0, x1, y1 = points
        self.canvas.setStrokeColor(HexColor(fill))
        self.canvas.setLineWidth(1)
        self.canvas.line(x0, self.height-y0, x1, self.height-y1)

    def image(self, path, box):
        x,y,width,height = box
        self.canvas.drawImage(str(path),x,self.height-y-height,width,height,
                              preserveAspectRatio=True,anchor='c')

    def save(self, _legacy_png_path):
        self.canvas.showPage()
        self.document.pages += 1
