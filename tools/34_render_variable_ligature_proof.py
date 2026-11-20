#!/usr/bin/env python3
"""Vector proofs of restored ligatures and continuous upright/italic weights."""
import argparse
import importlib
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
import numpy as np
from variable_font_support import ProofFace
from lcd_font_proofs import RasterFace, GAMMA

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT


def draw(canvas, face, text, x, y, size, color='#172633'):
    canvas.saveState()
    canvas.setFillColor(HexColor(color))
    canvas.translate(x, y)
    canvas.scale(size / face.upm, size / face.upm)
    cursor = 0
    for gid, advance, _, dx, dy in face.shaped(text):
        assert gid != 0, text
        canvas.saveState()
        canvas.translate(cursor + dx, dy)
        canvas.drawPath(face.outline(gid, canvas), fill=1, stroke=0, fillMode=1)
        canvas.restoreState()
        cursor += advance
    assert x + cursor * size / face.upm < 576, (text, size, cursor)
    canvas.restoreState()


def label(canvas, text, x, y, size=9, color='#566b7a'):
    canvas.setFillColor(HexColor(color))
    canvas.setFont('Helvetica', size)
    canvas.drawString(x, y, text)


def header(canvas, title, subtitle, number):
    canvas.setFillColor(HexColor('#faf9f6'))
    canvas.rect(0, 0, 612, 792, fill=1, stroke=0)
    label(canvas, 'LATO26 / LIGATURES + VARIABLE WEIGHT', 36, 758, 9)
    label(canvas, title, 36, 723, 23, '#172633')
    label(canvas, subtitle, 36, 702, 10)
    label(canvas, f'{number} / 8', 551, 24)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--reference-dir', type=Path, default=Path('/Library/Fonts'))
    args = ap.parse_args()
    output = ROOT / 'output/pdf/Lato26-Variable-Ligatures.pdf'
    c = Canvas(str(output), pagesize=(612, 792), pageCompression=1)
    c.setTitle('Lato26 - ligature repair and variable weight proofs')
    c.setAuthor('Lato26 font revision')
    for page, (style, italic, title, extension) in enumerate([
            ('Upr', '', 'Upright ligatures', 'ttf'), ('Ita', 'Italic', 'Italic ligatures', 'otf')], 1):
        header(c, title, 'Dotted 3.100 forms before; connected, dotless 2.015 forms restored.', page)
        label(c, 'BEFORE', 98, 669)
        label(c, 'RESTORED', 342, 669)
        for i, weight in enumerate(build.WEIGHTS):
            name = 'Italic' if italic and weight == 'Regular' else weight + italic
            relative = Path(f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{name}.{extension}')
            y = 629 - i * 64
            label(c, weight, 36, y + 5, 8)
            draw(c, ProofFace(args.snapshot / relative), 'fi ffi office affinity', 98, y, 23, '#7b858c')
            draw(c, ProofFace(ROOT / relative), 'fi ffi office affinity', 342, y, 23)
        label(c, 'Existing advances and kerning retained. Static TTF hints rebuilt for these forms only.', 36, 47, 9)
        c.showPage()
    for page, (italic, title) in enumerate([('', 'Upright variable font'), ('Italic', 'Italic variable font')], 3):
        header(c, title, 'Weight 100-900; default 400. Nine named weights plus intermediate samples.', page)
        path = ROOT / f'build/Lato26-Variable/Lato26-Variable{italic}.ttf'
        weights = (100, 200, 300, 350, 400, 500, 600, 650, 700, 800, 850, 900)
        for i, weight in enumerate(weights):
            y = 650 - i * 47
            label(c, str(weight), 36, y + 4, 10)
            draw(c, ProofFace(path, weight), 'fi ffi office  a e æ  la le lo ly ll', 88, y, 25)
        label(c, 'Vector outlines from the actual variable files, shaped at each displayed weight.', 36, 61, 9)
        label(c, 'Variable fonts are unhinted; use the static TTFs for the existing native hinting.', 36, 45, 9)
        c.showPage()
    for page, (style,italic,title) in enumerate([('Upr','','Upright related forms'),('Ita','Italic','Italic related forms')],5):
        header(c,title,'Each weight: released Lato 2.015 above; restored Lato26 below.',page)
        for i,weight in enumerate(build.WEIGHTS):
            name='Italic' if italic and weight=='Regular' else weight+italic
            old=args.reference_dir/f'Lato-{name}.ttf'
            new=ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{name}.ttf'
            y=651-i*63
            label(c,weight,36,y-10,8)
            sample='fi ffi  fį ffį  fị ffị  fḭ ffḭ  fɨ ffɨ'
            draw(c,ProofFace(old),sample,108,y,21,'#7b858c')
            draw(c,ProofFace(new),sample,108,y-27,21)
        label(c,'Exact 2.015 quadratic outlines, including the joined ogonek and stroke variants.',36,49,9)
        c.showPage()
    for page,(style,italic,title) in enumerate([('Upr','','Upright screen sizes'),('Ita','Italic','Italic screen sizes')],7):
        header(c,title,'Native TTF instructions; RGB subpixel simulation at 2x pixel magnification.',page)
        label(c,'LATO 2.015',135,669);label(c,'LATO26 RESTORED',360,669)
        for row,(weight,size) in enumerate((w,s) for w in ('Regular','Bold') for s in (12,14,16,18,24)):
            name='Italic' if italic and weight=='Regular' else weight+italic
            y=626-row*52
            label(c,f'{weight} / {size} px',36,y,8)
            for x,path in [(135,args.reference_dir/f'Lato-{name}.ttf'),(360,ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{name}.ttf')]:
                alpha,_,_,_=RasterFace(path).coverage('fi ffi fį fị',size)
                pixels=np.round(255*(1-alpha)**(1/GAMMA)).clip(0,255).astype('uint8')
                mask=np.any(pixels<254,axis=2);ys,xs=np.where(mask)
                im=Image.fromarray(pixels).crop((max(0,xs.min()-1),max(0,ys.min()-1),xs.max()+2,ys.max()+2))
                assert im.width*2<215
                im=im.resize((im.width*4,im.height*4),Image.Resampling.NEAREST)
                c.drawImage(ImageReader(im),x,y-8,width=im.width/2,height=im.height/2)
        label(c,'FreeType approximation, not a Windows DirectWrite capture. PDF zoom can resample pixels.',36,57,9)
        label(c,'Automated checks also cover every weight and related form at 8-50, 64 and 72 px.',36,41,9)
        c.showPage()
    c.save()
    print(output, '8 pages: vector comparisons, variable weights and hinted screen sizes', flush=True)


if __name__ == '__main__':
    main()
