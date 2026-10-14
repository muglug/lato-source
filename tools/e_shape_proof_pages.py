"""Focused before/after pages for the authored upright e revision."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def append_e_shape_proofs(document,font,before):
    arial='/System/Library/Fonts/Supplemental/Arial.ttf'
    heading=font(arial,32);label=font(arial,21);note=font(arial,18)
    rel=Path('Lato3Upr2M/ds-ufo/masters')
    page=document.page(1200,1553)
    document.canvas.bookmarkPage('e-shape')
    document.canvas.addOutlineEntry('Upright e shape revision','e-shape',level=0)
    page.text((54,40),'Lato26 - upright e shape revision',font=heading,fill='#151d29')
    page.text((54,91),'Four authored masters; intermediate weights interpolate between them. Italics unchanged.',font=note,fill='#69707a')
    for x,caption in ((270,'Before'),(720,'After')):page.text((x,132),caption,font=label,fill='#69707a')
    for i,weight in enumerate(('Hairline','Thin','Light','Regular','Medium','Semibold','Bold','Heavy','Black')):
        y=178+i*139
        page.text((54,y+31),weight,font=label,fill='#151d29')
        for x,base in ((270,before),(720,ROOT/'build')):
            f=font(str(base/rel/f'Lato26-{weight}.ttf'),108)
            page.text((x,y),'e é æ œ',font=f,fill='#111827')
        page.line((54,y+126,1146,y+126),fill='#dddcd7')
    page.text((54,1479),'Advances and kerning are preserved. The ae bowl joins follow the revised e crossbar.',font=note,fill='#69707a')
    page.save(None)
    page=document.page(1200,1553)
    document.canvas.bookmarkPage('e-related')
    document.canvas.addOutlineEntry('Upright e related forms','e-related',level=1)
    page.text((54,40),'Lato26 - related e forms and joins',font=heading,fill='#151d29')
    page.text((54,91),'Current upright forms. Accents, small forms, Cyrillic and turned forms follow the edit.',font=note,fill='#69707a')
    for i,weight in enumerate(('Regular','Bold','Black')):
        y=157+i*425;path=ROOT/'build'/rel/f'Lato26-{weight}.ttf'
        page.text((54,y),weight,font=label,fill='#69707a')
        page.text((54,y+39),'e é è ê ë ě ē ę ė ẹ ẽ ȩ',font=font(str(path),77),fill='#111827')
        page.text((54,y+137),'æ ǽ ǣ œ  ə ǝ ɘ  е ё ѐ',font=font(str(path),77),fill='#111827')
        page.text((54,y+237),'ᵉ ₑ ₔ · eͤ · légère · encyclopædia · œuvre',font=font(str(path),58),fill='#111827')
        page.line((54,y+383,1146,y+383),fill='#dddcd7')
    page.text((54,1479),'The smaller l and the corrected Bold a are preserved. Native hints are checked separately.',font=note,fill='#69707a')
    page.save(None)
