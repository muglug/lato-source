#!/usr/bin/env python3
"""Render vector PDF proofs, or optional PNGs at double width and height."""
import argparse
import json
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-dir', required=True, type=Path)
parser.add_argument('--previous-build', required=True, type=Path)
parser.add_argument('--format', choices=('pdf','png'), default='pdf')
parser.add_argument('--output', type=Path)
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1]
SCALE=2
if args.format=='pdf':
    from vector_font_proofs import Document, Font
    document=Document(args.output or ROOT/'output/pdf/Lato26-Proofs.pdf')

@lru_cache(maxsize=None)
def font(path,size):
    if args.format=='pdf':return Font(path,size)
    return ImageFont.truetype(path,size*SCALE)

def canvas(width,height):
    if args.format=='pdf':return document.page(width,height)
    return Image.new('RGB',(width*SCALE,height*SCALE),'#faf9f6')

class Draw:
    def __init__(self,image): self.draw=image if args.format=='pdf' else ImageDraw.Draw(image)
    def text(self,point,text,**kwargs):
        if args.format=='pdf':return self.draw.text(point,text,**kwargs)
        self.draw.text(tuple(v*SCALE for v in point),text,**kwargs)
    def line(self,points,**kwargs):
        if args.format=='pdf':return self.draw.line(points,**kwargs)
        self.draw.line(tuple(v*SCALE for v in points),width=SCALE,**kwargs)

root=ROOT;old=args.baseline_dir
label=font('/System/Library/Fonts/Supplemental/Arial.ttf',22)
small=font('/System/Library/Fonts/Supplemental/Arial.ttf',18)
im=canvas(1700,2400);d=Draw(im)
d.text((50,25),'Lato26 lowercase revision · outline proof',font=label,fill='#151d29')
d.text((50,60),'Original',font=small,fill='#69707a');d.text((875,60),'Lato26',font=small,fill='#69707a')
y=115
for style,suffix in [('Upr',''),('Ita','Italic')]:
 for weight in ['Hairline','Light','Regular','Bold','Black']:
  filename='Lato-'+('Italic' if weight=='Regular' and suffix else weight+suffix)+'.ttf'
  rel=Path('Lato3'+style+'2M/ds-ufo/masters')/filename
  d.text((50,y),weight+(' Italic' if suffix else ''),font=small,fill='#69707a')
  for x,base in [(50,old),(875,root/'build')]:
   path=base/(rel if base==old else rel.with_name(filename.replace('Lato-', 'Lato26-')))
   f=font(str(path),100)
   d.text((x,y+28),'l j t  a e æ œ',font=f,fill='#111827')
   ff=font(str(path),36)
   d.text((x,y+142),'little leaf · allee · ﬂower · ł ĺ ľ · á é а е',font=ff,fill='#111827')
  d.line((50,y+215,1650,y+215),fill='#dddcd7')
  y+=220
im.save(root/'build/proofs/lowercase-overview.png')


r=ROOT;old=args.baseline_dir
label=font('/System/Library/Fonts/Supplemental/Arial.ttf',22)
im=canvas(1600,1700);d=Draw(im);d.text((40,20),'Carlito26 · metric-preserving outline revision',font=label,fill='#111827')
y=70
for labelname in ['Light','LightItalic']:
 for caption,base in [('Original',old),('Revised',r/'build')]:
  family='Carlito' if base==old else 'Carlito26'
  f=font(str(base/family/(family+'-'+labelname+'.ttf')),100)
  d.text((40,y),labelname+' / '+caption,font=label,fill='#626973');d.text((40,y+38),'l j t a e æ œ · little leaf · allegro',font=f,fill='#111827');y+=200
samples=['l ĺ ļ ľ ł ŀ ḷ ḹ ḻ ḽ ɫ ɬ ǉ ﬂ ﬄ', 'a à á â ã ä å ą æ ǽ ǣ а ә е ё', 'e è é ê ë ę ě ē œ ə ǝ ɘ', 'ᵃ ᵉ ˡ ₐ ₑ ₔ · aͣ eͤ']
y+=25
for labelname,folder in [('Regular','Lato3Upr2M'),('Italic','Lato3Ita2M')]:
 f=font(str(r/'build'/folder/'ds-ufo/masters'/('Lato26-'+labelname+'.ttf')),70)
 d.text((40,y),labelname+' / related characters',font=label,fill='#626973');y+=35
 for sample in samples:d.text((40,y),sample,font=f,fill='#111827');y+=78
 y+=20
im.save(r/'build/proofs/lowercase-details.png')


root=ROOT; before=args.previous_build;original=args.baseline_dir
label=font('/System/Library/Fonts/Supplemental/Arial.ttf',23)
small=font('/System/Library/Fonts/Supplemental/Arial.ttf',18)
im=canvas(1800,2230);d=Draw(im)
d.text((40,20),'Lato26 · æ join and l spacing refinement',font=label,fill='#111827')
for x,caption in ((40,'Original Lato'),(630,'Previous Lato26'),(1220,'Updated Lato26')):d.text((x,65),caption,font=small,fill='#667085')
y=112
for style,suffix in [('Upr',''),('Ita','Italic')]:
 for weight in ['Hairline','Regular','Black']:
  name='Italic' if suffix and weight=='Regular' else weight+suffix
  rel=Path(f'Lato3{style}2M/ds-ufo/masters')
  d.text((40,y),weight+(' Italic' if suffix else ''),font=small,fill='#667085')
  for x,p in ((40,original/rel/f'Lato-{name}.ttf'),(630,before/rel/f'Lato26-{name}.ttf'),(1220,root/'build'/rel/f'Lato26-{name}.ttf')):
   big=font(str(p),150);text=font(str(p),49)
   d.text((x,y+27),'æ ǽ ǣ',font=big,fill='#111827')
   d.text((x,y+204),'le lo · ﬂe ﬂo · ll',font=text,fill='#111827')
   d.text((x,y+265),'little · alley · ﬂeet',font=text,fill='#111827')
  d.line((40,y+337,1760,y+337),fill='#dddcd7');y+=350
im.save(root/'build/proofs/ae-and-l-spacing.png')

if args.format=='pdf':
    # One page per weight/style keeps all 26 pairs large enough to compare.
    weights=['Hairline','Thin','Light','Regular','Medium','Semibold','Bold','Heavy','Black']
    letters='abcdefghijklmnopqrstuvwxyz'
    heading=font('/System/Library/Fonts/Supplemental/Arial.ttf',32)
    subheading=font('/System/Library/Fonts/Supplemental/Arial.ttf',24)
    tablelabel=font('/System/Library/Fonts/Supplemental/Arial.ttf',20)
    note=font('/System/Library/Fonts/Supplemental/Arial.ttf',17)
    audit_path=ROOT/'build/proofs/optical-spacing.json'
    audit=json.loads(audit_path.read_text()) if audit_path.exists() else None
    indices={(r['style'],r['weight'],r['pair']):r['after']['blur_index'] for r in audit['rows']} if audit else {}
    total_pages=document.pages+2*len(weights)+(3 if audit else 0)
    pair_count=0
    for style,suffix in [('Upr',''),('Ita','Italic')]:
        for weight in weights:
            name='Italic' if suffix and weight=='Regular' else weight+suffix
            caption=weight+(' Italic' if suffix else ' Upright')
            rel=Path(f'Lato3{style}2M/ds-ufo/masters')
            before_font=font(str(args.baseline_dir/rel/f'Lato-{name}.ttf'),64)
            after_font=font(str(ROOT/'build'/rel/f'Lato26-{name}.ttf'),64)
            im=canvas(1200,1553);d=Draw(im)
            bookmark=f'l-combinations-{style}-{weight}'
            document.canvas.bookmarkPage(bookmark)
            if pair_count==0:
                document.canvas.addOutlineEntry('Lowercase l combinations',bookmark,level=0)
            document.canvas.addOutlineEntry(caption,bookmark,level=1)
            d.text((54,40),'Lato26 · lowercase l combinations',font=heading,fill='#151d29')
            d.text((54,88),caption,font=subheading,fill='#151d29')
            d.text((54,130),'Before: original Lato. After: current Lato26. Kerning enabled.',font=note,fill='#69707a')
            if audit:d.text((54,155),'Index: current blurred-ink interaction, relative to le = 1.00; higher is stronger, not necessarily worse.',font=note,fill='#69707a')
            for base,characters in [(54,letters[:13]),(640,letters[13:])]:
                d.text((base,190),'Next',font=note,fill='#69707a')
                d.text((base+60,186),'Before',font=tablelabel,fill='#69707a')
                d.text((base+290,186),'After',font=tablelabel,fill='#69707a')
                if audit:d.text((base+423,190),'Index',font=note,fill='#69707a')
                for row,letter in enumerate(characters):
                    y=230+row*90
                    d.text((base,y+31),letter,font=note,fill='#69707a')
                    for x,proof_font in [(base+60,before_font),(base+290,after_font)]:
                        sample='l'+letter
                        width=sum(g[1] for g in proof_font.face.shaped(sample))*proof_font.size/proof_font.face.upm
                        assert width<120,(caption,sample,width)
                        d.text((x,y),sample,font=proof_font,fill='#111827')
                    if audit:d.text((base+423,y+31),f'{indices[style,weight,sample]:.2f}',font=note,fill='#69707a')
                    d.line((base,y+85,base+506,y+85),fill='#e3e1dc')
                    pair_count+=1
            d.line((600,184,600,1400),fill='#dddcd7')
            d.text((54,1479),'la-lz · lowercase l followed by every lowercase Latin letter',font=note,fill='#69707a')
            d.text((1020,1479),f'{document.pages+1} / {total_pages}',font=note,fill='#69707a')
            im.save(None)
    assert pair_count==26*18
    print(pair_count,'before/after l combinations across 18 styles')
    if audit:
        from optical_proof_pages import append_optical_proofs
        append_optical_proofs(document,font,args.previous_build,audit)
    document.save()
else:
    for name,size in [('lowercase-overview.png',(3400,4800)),('lowercase-details.png',(3200,3400)),('ae-and-l-spacing.png',(3600,4460))]:
        path=ROOT/'build/proofs'/name
        with Image.open(path) as im: assert im.size==size
        print(name, size)
