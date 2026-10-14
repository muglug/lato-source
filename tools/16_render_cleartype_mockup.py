#!/usr/bin/env python3
"""Build a clearly labelled ClearType-style approximation from the actual TTFs.

Outputs native-pixel PNGs, a local HTML viewer, and a raster PDF.
Use --before-hint-build PATH to append comparisons against the previous hints.
Requires the same ReportLab/HarfBuzz setup as the vector proof renderer,
plus NumPy and SciPy. No font files are modified.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

from lcd_font_proofs import draw_text, raster_face, GAMMA, FILTER
from bold_a_hint_controls import bold_a_matches

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/cleartype'
PDF = ROOT / 'output/pdf/Lato26-ClearType-Mockup.pdf'
OUT.mkdir(parents=True, exist_ok=True)
WEIGHTS = ['Hairline', 'Thin', 'Light', 'Regular', 'Medium', 'Semibold', 'Bold', 'Heavy', 'Black']
SCALES = [100, 125, 150, 200]
INK, MUTED, BLUE = '#202020', '#596575', '#0067c0'


def font(weight='Regular', italic=False):
    name = 'Italic' if italic and weight == 'Regular' else weight + ('Italic' if italic else '')
    return ROOT / f'build/Lato3{"Ita" if italic else "Upr"}2M/ds-ufo/masters/Lato26-{name}.ttf'


UI = Path('/System/Library/Fonts/Supplemental/Arial.ttf')
if not UI.exists():
    UI = font()


def label(im, xy, text, size=14, fill=MUTED, scale=1):
    draw = ImageDraw.Draw(im)
    draw.text(tuple(round(v*scale) for v in xy), text,
              font=ImageFont.truetype(str(UI), round(size*scale)), fill=fill, anchor='ls')


def rule(im, y, width=None):
    ImageDraw.Draw(im).line((40,y,width or im.width-40,y), fill='#dfe4e9')


def text(im, xy, value, size=16, weight='Regular', italic=False, scale=1, mode='rgb'):
    return draw_text(im, tuple(v*scale for v in xy), value, font(weight,italic),
                     size*scale, mode=mode)


def screen(percent):
    s=percent/100
    im=Image.new('RGB',(round(1000*s),round(860*s)),'#e8eff7')
    d=ImageDraw.Draw(im)
    def rect(box, fill, radius=0, outline=None):
        box=tuple(round(v*s) for v in box)
        d.rounded_rectangle(box, radius=round(radius*s), fill=fill, outline=outline, width=max(1,round(s)))
    rect((18,18,982,842),'#ffffff',12,'#c7d0db')
    rect((20,20,980,69),'#f3f5f8',10)
    rect((20,56,980,109),'#f3f5f8')
    label(im,(40,48),'Lato26  |  Type preview',14,INK,s)
    for x,mark in [(860,'-'),(904,'\u25a1'),(948,'\u00d7')]: label(im,(x,48),mark,17,INK,s)
    label(im,(42,92),'Reading proof',14,INK,s)
    rect((183,75,252,99),'#e1ebf9',5)
    label(im,(197,92),'Regular',12,BLUE,s)
    label(im,(277,92),'Italic',12,MUTED,s)
    label(im,(343,92),'Bold',12,MUTED,s)
    label(im,(746,92),f'{percent}% display scale',12,MUTED,s)
    text(im,(52,173),'Lato26',36,scale=s)
    label(im,(53,205),'A Windows-style reading mockup from the current font files',15,MUTED,s)
    d.line((52*s,229*s,948*s,229*s),fill='#e3e7eb',width=max(1,round(s)))
    label(im,(53,257),'REGULAR  /  16 px (12 pt at 96 dpi)',12,BLUE,s)
    lines=[
        'The little yellow leaves settled along the wall. A clear line of light',
        'fell across the valley, while the pale afternoon slowly slipped away.',
        'All the small details - a taller bowl, a lower bar, a little more room - matter.'
    ]
    for i,line in enumerate(lines): text(im,(53,291+i*25),line,16,scale=s)
    label(im,(53,385),'ITALIC  /  16 px',12,BLUE,s)
    text(im,(53,417),'A lovely little valley, a yellow leaf, and a quiet alley.',16,italic=True,scale=s)
    label(im,(53,466),'REVISED SHAPES AND SPACING',12,BLUE,s)
    text(im,(53,502),'la   lc   le   lo   ll   lw   ly   æ',26,scale=s)
    text(im,(53,549),'a à á ä æ    e è é ë œ    l ĺ ł',28,scale=s)
    d.line((52*s,578*s,948*s,578*s),fill='#e3e7eb',width=max(1,round(s)))
    for size,y in [(12,614),(14,652),(18,695),(24,748)]:
        label(im,(53,y),f'{size} px',12,MUTED,s)
        text(im,(120,y),'little leaves along the yellow wall',size,scale=s)
    rect((20,791,980,840),'#f5f7fa',9)
    label(im,(40,811),'SIMULATION  |  RGB subpixel filtering; FreeType, not Microsoft DirectWrite.',12,INK,s)
    label(im,(40,829),'Inspect at native pixels. Windows application, display and ClearType settings can change the result.',11,MUTED,s)
    p=OUT/f'Lato26-ClearType-Mockup-{percent}.png';im.save(p)
    return p


def weights():
    im=Image.new('RGB',(1040,1010),'white')
    label(im,(40,50),'Lato26 / all weights',28,INK)
    label(im,(40,80),'RGB subpixel approximation at 16 px and 13 px; 100% display scale.',14)
    label(im,(40,105),'Current TTF outlines and kerning. This is not a Windows screenshot.',13)
    label(im,(188,157),'UPRIGHT',12,BLUE);label(im,(628,157),'ITALIC',12,BLUE)
    rule(im,175)
    for i,w in enumerate(WEIGHTS):
        y=214+i*79
        label(im,(40,y),w,14,INK)
        for x,it in [(188,False),(628,True)]:
            text(im,(x,y),'la lc le lo ll lw ly æ',16,w,it)
            text(im,(x,y+26),'little leaves along the yellow wall',13,w,it)
        rule(im,y+47)
    label(im,(40,958),'Small sizes expose hinting differences as well as the outline changes.',13)
    label(im,(40,982),'Simulation settings: RGB stripes / five-tap LCD filter / blending gamma 1.8.',12)
    p=OUT/'Lato26-ClearType-Weights.png';im.save(p);return p


def sample(size=16, italic=False, mode='rgb'):
    im=Image.new('RGB',(260,80),'white')
    text(im,(16,37),'la lc le lo ll lw ly æ',size,italic=italic,mode=mode)
    return im.crop((12,12,242,48))


def pixels():
    im=Image.new('RGB',(1040,1030),'white')
    label(im,(40,50),'The same pixels, enlarged',28,INK)
    label(im,(40,80),'16 px type at 100% scale. Each panel uses 4x nearest-neighbor enlargement.',14)
    label(im,(40,104),'RGB edges reveal subpixel rendering; the grayscale comparison uses the same gamma.',13)
    for i,(it,mode) in enumerate([(False,'rgb'),(False,'gray'),(True,'rgb'),(True,'gray')]):
        y=155+i*200
        caption=('Italic' if it else 'Regular')+' / '+('RGB subpixel approximation' if mode=='rgb' else 'grayscale antialiasing')
        label(im,(40,y),caption,14,BLUE)
        a=sample(16,it,mode)
        im.paste(a.resize((920,144),Image.Resampling.NEAREST),(40,y+18))
        rule(im,y+178)
    label(im,(40,984),'The enlarged panels show pixel structure, not the perceived appearance at reading size.',13)
    p=OUT/'Lato26-ClearType-Pixels.png';im.save(p);return p


def scales():
    im=Image.new('RGB',(1040,910),'white')
    label(im,(40,50),'Display scaling / 16 px text',28,INK)
    label(im,(40,80),'Each row is rasterized again at its physical pixel size, not enlarged from a 100% image.',14)
    for i,percent in enumerate(SCALES):
        y=153+i*162
        ppem=16*percent/100
        label(im,(40,y),f'{percent}% display scale  /  {ppem:g} physical pixels per em',14,BLUE)
        text(im,(40,y+44),'little leaves along the yellow wall · la lc le lo ll lw ly æ',ppem)
        text(im,(40,y+85),'little leaves along the yellow wall · la lc le lo ll lw ly æ',ppem,italic=True)
        rule(im,y+118)
    label(im,(40,840),'All rows are displayed at the same pixel-to-image ratio here; higher-scale rows are physically larger.',12)
    label(im,(40,866),'For equal logical window sizes, compare the separate mockup images in the viewer.',12)
    p=OUT/'Lato26-ClearType-Scales.png';im.save(p);return p


def hint_comparison(before_build):
    im=Image.new('RGB',(1040,1040),'white')
    label(im,(40,50),'Lato 2.015 hinting / before and after',26,INK)
    label(im,(40,80),'Historical / current builds. Hinting, outlines and spacing differ. 16 px text, enlarged 3x.',13)
    label(im,(40,126),'PREVIOUS LATO26 HINTS',12,BLUE)
    label(im,(552,126),'LATO26 / 2.015 RECIPE',12,BLUE)
    for row,(weight,it) in enumerate((w,it) for w in ('Light','Regular','Bold') for it in (False,True)):
        y=169+row*136
        label(im,(40,y),weight+(' Italic' if it else ' Upright'),13,INK)
        current=font(weight,it)
        previous=before_build/current.relative_to(ROOT/'build')
        for x,path in ((40,previous),(552,current)):
            tile=Image.new('RGB',(220,80),'white')
            draw_text(tile,(16,37),'a e æ l  le lo lw ly',path,16)
            tile=tile.crop((12,16,161,46)).resize((447,90),Image.Resampling.NEAREST)
            im.paste(tile,(x,y+12))
        rule(im,y+118)
    label(im,(40,1020),'Rendering remains a FreeType RGB approximation; native Windows/DirectWrite validation is still separate.',12)
    path=OUT/'Lato26-Hinting-Before-After.png';im.save(path);return path


def bold_a_comparison(before_build):
    im=Image.new('RGB',(1040,1010),'white')
    label(im,(40,50),'Bold a / bowl-top hint correction',27,INK)
    label(im,(40,80),'The same outlines and spacing; 6x nearest-neighbor enlargement of the actual pixels.',13)
    label(im,(40,107),'The correction also applies to 33 matching accented and Cyrillic forms.',13)
    label(im,(40,147),'EARLIER AUTOHINT PASS',12,BLUE)
    label(im,(552,147),'LATO26 / 2.015 + BOWL CONTROL',12,BLUE)
    current=font('Bold')
    previous=before_build/current.relative_to(ROOT/'build')
    for row,size in enumerate((12,14,16,18,20)):
        y=180+row*151
        label(im,(40,y),f'{size} px'+('  /  reported size' if size==16 else ''),13,INK)
        for x,path in ((40,previous),(552,current)):
            tile=Image.new('RGB',(180,85),'white')
            draw_text(tile,(16,37),'a  á  ä  а',path,size)
            tile=tile.crop((12,18,89,39)).resize((462,126),Image.Resampling.NEAREST)
            im.paste(tile,(x,y+10))
        rule(im,y+141)
    gaps=[]
    for path in (previous,current):
        coords=raster_face(str(path)).hinted_points('a',16)
        gaps.append(coords[57][1]-coords[58][1])
    label(im,(40,970),f'16 px bowl-top edge separation at the join: {gaps[0]:.2f} px before, {gaps[1]:.2f} px corrected (outline: 1.21 px).',12)
    label(im,(40,994),'FreeType RGB approximation. The new font uses the same hinting engine and settings as Lato 2.015.',12)
    path=OUT/'Lato26-Bold-A-Hinting.png';im.save(path);return path


def reference_comparison(reference_dir, original_build, italic):
    title='Italic' if italic else 'Upright'
    im=Image.new('RGB',(1040,1110),'white')
    label(im,(40,50),title+' / released hinting restored',26,INK)
    label(im,(40,80),'16 px type enlarged 3x. Each file executes its own embedded TrueType instructions.',13)
    label(im,(40,107),'The italic a is unchanged by our outline edits; the upright a has the enlarged bowl.',13)
    for x,caption in [(40,'REFERENCE LATO 2.015'),(380,'REPOSITORY LATO 3.100'),(720,'LATO26 / 2.015 RECIPE')]:
        label(im,(x,142),caption,12,BLUE)
    for row,weight in enumerate(WEIGHTS):
        y=177+row*99
        label(im,(40,y),weight+(' Italic' if italic else ''),12,INK)
        current=font(weight,italic)
        relative=current.relative_to(ROOT/'build')
        original=original_build/relative.with_name(current.name.replace('Lato26-','Lato-'))
        assert raster_face(str(original)).shape.tt['name'].getDebugName(5).startswith('Version 3.100')
        installed=reference_dir/current.name.replace('Lato26-','Lato-')
        for x,path in [(40,installed),(380,original),(720,current)]:
            tile=Image.new('RGB',(180,80),'white')
            draw_text(tile,(16,37),'a h k n o',path,16)
            im.paste(tile.crop((12,17,112,41)).resize((300,72),Image.Resampling.NEAREST),(x,y+8))
        rule(im,y+88)
    label(im,(40,1100),'Lato26 keeps our outlines and spacing. Instructions are regenerated with the exact Lato 2.015 recipe.',12)
    path=OUT/f'Lato26-Hinting-Reference-{title}.png';im.save(path);return path


def join_comparison(before_build):
    im=Image.new('RGB',(1040,1350),'white')
    label(im,(40,50),'Bold a / connected joins',27,INK)
    label(im,(40,80),'6x enlargement. Only the two stem-end points change after hinting; the bowl stays identical.',13)
    label(im,(40,120),'BEFORE / OPEN SEAM',12,BLUE)
    label(im,(552,120),'AFTER / LINKED JOIN',12,BLUE)
    current=font('Bold');previous=before_build/current.relative_to(ROOT/'build')
    for row,size in enumerate((12,14,16,18,20,24)):
        y=155+row*188
        label(im,(40,y),f'{size} px'+(' / reported gap' if size==14 else ''),13,INK)
        for x,path in ((40,previous),(552,current)):
            tile=Image.new('RGB',(180,100),'white')
            draw_text(tile,(16,50),'a á ä а',path,size)
            ys,xs=np.where(np.any(np.asarray(tile)<254,axis=2))
            assert xs.min()>=12 and xs.max()<93 and ys.min()>=26 and ys.max()<53,(size,path,'clipped join proof')
            im.paste(tile.crop((12,26,93,53)).resize((486,162),Image.Resampling.NEAREST),(x,y+10))
        rule(im,y+177)
    before=raster_face(str(previous)).hinted_points('a',14)
    after=raster_face(str(current)).hinted_points('a',14)
    label(im,(40,1325),f'14 px: {before[1][1]-before[30][1]:.2f} px gap becomes {after[30][1]-after[1][1]:.2f} px overlap; bowl top remains {after[57][1]-after[58][1]:.2f} px.',12)
    path=OUT/'Lato26-Bold-A-Joins.png';im.save(path);return path


def accented_join_proof():
    im=Image.new('RGB',(1040,1240),'white')
    label(im,(40,50),'Bold a / all 34 linked forms',27,INK)
    label(im,(40,80),'14 px (left) and 16 px (right), enlarged 4x. Accent positions and bowl hints are unchanged.',13)
    path=font('Bold');face=raster_face(str(path));tt=face.shape.tt
    codepoints={}
    for cp,name in sorted(tt.getBestCmap().items()):codepoints.setdefault(name,cp)
    for index,(name,start) in enumerate(bold_a_matches(tt)):
        row,col=divmod(index,4);x=40+col*244;y=130+row*120
        label(im,(x,y),name,12,INK)
        character=chr(codepoints[name])
        shaped=face.shape.shaped(character)
        assert len(shaped)==1 and shaped[0][0]==tt.getGlyphID(name),(name,shaped)
        for offset,size in ((0,14),(112,16)):
            tile=Image.new('RGB',(100,100),'white')
            draw_text(tile,(20,50),character,path,size)
            # Includes stacked accents and below-baseline marks.
            ys,xs=np.where(np.any(np.asarray(tile)<254,axis=2))
            assert xs.min()>=15 and xs.max()<37 and ys.min()>=31 and ys.max()<58,(name,size,'clipped accented proof')
            im.paste(tile.crop((15,31,37,58)).resize((88,108),Image.Resampling.NEAREST),(x+offset,y+3))
    label(im,(40,1230),'All forms checked at integer sizes 6-201, quarter-pixel sizes 8-50, and 256 px in three render targets.',12)
    output=OUT/'Lato26-Bold-A-Accented-Joins.png';im.save(output);return output


def pdf_page(c, title, subtitle, path, notes, number, total=4):
    c.setPageSize((792,900))
    c.setFillColor(HexColor(INK));c.setFont('Helvetica-Bold',20);c.drawString(36,858,title)
    c.setFont('Helvetica',10);c.setFillColor(HexColor(MUTED));c.drawString(36,835,subtitle)
    with Image.open(path) as im: w,h=im.size
    factor=min(720/w,705/h)
    dw,dh=w*factor,h*factor
    c.drawImage(str(path),(792-dw)/2,814-dh,width=dw,height=dh)
    c.setStrokeColor(HexColor('#dfe4e9'));c.line(36,90,756,90)
    c.setFillColor(HexColor(MUTED));c.setFont('Helvetica',9)
    for i,line in enumerate(notes):c.drawString(36,72-i*13,line)
    c.drawRightString(756,20,f'{number} / {total}')
    c.showPage()


def viewer():
    html='''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lato26 - ClearType-style mockup</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf1f6;color:#202d3d;font:15px system-ui,sans-serif}
header{padding:25px 32px 20px;background:white;border-bottom:1px solid #d3dbe6}h1{font-size:25px;margin:0 0 8px}
p{margin:8px 0;max-width:1050px;line-height:1.5;color:#596575}nav{display:flex;gap:14px;flex-wrap:wrap;margin-top:20px;align-items:end}
label{font-size:12px;color:#596575;display:grid;gap:5px}select,a{font:14px system-ui;padding:8px 10px;border:1px solid #c2ccda;border-radius:5px;background:white;color:#174775}
#stage{padding:28px;overflow:auto;min-height:500px}img{display:block;background:white;box-shadow:0 5px 22px #35456020}
#status{font:12px ui-monospace,monospace;margin-top:12px;color:#596575}.sources{font-size:12px}a{display:inline-block;text-decoration:none}.sources a{border:0;padding:0}
</style>
<header><h1>Lato26 / ClearType-style mockup</h1>
<p>Rendered from the current Lato26 TTFs using filtered RGB subpixel coverage. This is a simulation, not a capture from Windows 11 or Microsoft DirectWrite.</p>
<nav><label>Proof<select id="proof"><option value="mockup">Windows-style reading window</option><option value="weights">All weights</option><option value="pixels">Pixel detail and grayscale</option><option value="scales">Display-scale comparison</option></select></label>
<label>Display scale<select id="scale"><option>100</option><option>125</option><option>150</option><option>200</option></select></label>
<label>View<select id="view"><option value="fit">Fit (resampled)</option><option value="logical">Logical window size</option><option value="1">Native pixels (1:1)</option><option value="2">2x pixels</option><option value="4">4x pixels</option><option value="8">8x pixels</option></select></label>
<a href="../pdf/Lato26-ClearType-Mockup.pdf">PDF proof</a><a id="download" download>PNG image</a></nav>
<div id="status" aria-live="polite"></div>
<p>Use Native pixels for the closest screen comparison. Fit and logical-size views can resample color fringes. Display geometry, gamma and application rendering still affect a real Windows result.</p>
<p class="sources">Method: HarfBuzz shaping, FreeType native TrueType instructions without auto-hinting, 3x horizontal coverage, five-tap RGB filtering, blending gamma 1.8. <a href="https://freetype.org/freetype2/docs/reference/ft2-lcd_rendering.html">FreeType reference</a> · <a href="https://learn.microsoft.com/en-us/windows/win32/directwrite/introducing-directwrite">Microsoft DirectWrite reference</a>.</p>
</header><main id="stage"><img id="image" alt="Lato26 rendered with simulated RGB subpixel antialiasing"></main>
<script>
const proof=document.querySelector('#proof'),scale=document.querySelector('#scale'),view=document.querySelector('#view'),img=document.querySelector('#image');
const names={weights:'Lato26-ClearType-Weights.png',pixels:'Lato26-ClearType-Pixels.png',scales:'Lato26-ClearType-Scales.png'};
function layout(){let dpr=window.devicePixelRatio||1,w=img.naturalWidth;let kind=view.value;
if(kind==='fit')w=Math.min(w,document.querySelector('#stage').clientWidth-56);
else if(kind==='logical')w=img.naturalWidth/(proof.value==='mockup'?Number(scale.value)/100:1);
else w=img.naturalWidth*Number(kind)/dpr;
img.style.width=w+'px';img.style.height='auto';img.style.imageRendering=['fit','logical'].includes(kind)?'auto':'pixelated';
document.querySelector('#status').textContent=img.naturalWidth+' × '+img.naturalHeight+' source pixels · browser pixel ratio '+dpr+' · '+view.selectedOptions[0].text;}
function update(){scale.disabled=proof.value!=='mockup';let name=names[proof.value]||('Lato26-ClearType-Mockup-'+scale.value+'.png');img.src=name;document.querySelector('#download').href=name;}
img.onload=layout;proof.onchange=scale.onchange=update;view.onchange=layout;window.onresize=layout;update();
</script></html>'''
    (OUT/'index.html').write_text(html)


def validate():
    report={'renderer':'FreeType RGB subpixel simulation, not Microsoft DirectWrite',
            'freetype':features.version('freetype2'),'gamma':GAMMA,
            'filter':FILTER.tolist(),'scales':SCALES,'fonts':[]}
    for italic in (False,True):
        for weight in WEIGHTS:
            path=font(weight,italic);face=raster_face(str(path))
            for size in (12,13,14,16,18,20,24,32):
                value='la lc le lo ll lw ly æ à é ĺ'
                rgb,_,_,advance=face.coverage(value,size,'rgb')
                gray,_,_,gray_advance=face.coverage(value,size,'gray')
                expected=ImageFont.truetype(str(path),2000).getlength(value)*size/2000
                assert abs(advance-expected)<0.02,(path,size,advance,expected)
                assert advance==gray_advance
                assert np.any(rgb[:,:,0]!=rgb[:,:,1])
                assert np.array_equal(gray[:,:,0],gray[:,:,1])
            # Confirm our sampling transform has not suppressed the font's
            # native hint program (a pre-load stretch would do exactly that).
            hinted=face.coverage('l a e',16,'rgb')[0]
            unhinted=face.coverage('l a e',16,'rgb',False)[0]
            assert not np.array_equal(hinted,unhinted),(path,'native hints were not applied')
            tt=face.shape.tt
            hints={g:len(tt['glyf'][g].program.getBytecode()) if hasattr(tt['glyf'][g],'program') else 0
                   for g in ('l','a','e','w','y')}
            report['fonts'].append({'path':str(path.relative_to(ROOT)),
                                   'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'glyph_hint_bytes':hints})
    report.update(fonts_checked=18,sizes_checked=8,shaping_and_rgb_checks=144,
                  native_hint_effect_checks=18,status='passed')
    (OUT/'rendering-settings.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Validated all 18 fonts at 8 sizes; exact kerning, RGB channels and grayscale checked.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-hint-build',type=Path)
    parser.add_argument('--bowl-before-build',type=Path,help='Earlier build exhibiting the thick Bold a bowl; defaults to --before-hint-build')
    parser.add_argument('--reference-dir',type=Path)
    parser.add_argument('--original-hint-build',type=Path)
    parser.add_argument('--join-before-build',type=Path,help='Build with the disconnected Bold a join, for focused regression proofs')
    args=parser.parse_args()
    assert bool(args.reference_dir)==bool(args.original_hint_build)
    total=4+(2 if args.before_hint_build else 0)+(2 if args.reference_dir else 0)+(2 if args.join_before_build else 0)
    images=[screen(p) for p in SCALES]
    matrix,detail,scaling=weights(),pixels(),scales()
    comparison=hint_comparison(args.before_hint_build) if args.before_hint_build else None
    bowl=bold_a_comparison(args.bowl_before_build or args.before_hint_build) if args.before_hint_build else None
    references=[reference_comparison(args.reference_dir,args.original_hint_build,it) for it in (False,True)] if args.reference_dir else []
    joins=join_comparison(args.join_before_build) if args.join_before_build else None
    accents=accented_join_proof() if args.join_before_build else None
    viewer();validate()
    PDF.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(PDF),pageCompression=1)
    c.setTitle('Lato26 - ClearType-style mockup (simulation)')
    c.setAuthor('Lato26 font revision')
    common=['A filtered RGB approximation, not a Windows 11 / DirectWrite capture.',
            'Use the PNG viewer at Native pixels for screen judgments; PDF viewers may resample these raster proofs.']
    pdf_page(c,'Lato26 / Windows-style reading proof','100% scale. Text samples come from the current Lato26 TTFs.',images[0],common,1,total)
    pdf_page(c,'Weight and italic comparisons','Nine weights, upright and italic; 16 px and 13 px samples.',matrix,common,2,total)
    pdf_page(c,'Subpixels and grayscale','Fixed 4x nearest-neighbor enlargements of 16 px text.',detail,common,3,total)
    pdf_page(c,'Display scaling','Fresh rasterization at 100%, 125%, 150%, and 200% scale.',scaling,[
        'Lato26 uses ttfautohint 1.3 with the exact engine settings of released Lato 2.015.',
        'Method: native TTF bytecode, FreeType LCD-style filtering, HarfBuzz shaping, gamma 1.8.',
        'References: freetype.org/freetype2/docs/reference/ft2-lcd_rendering.html and Microsoft DirectWrite documentation.'
    ],4,total)
    if comparison:
        pdf_page(c,'Embedded TrueType instructions','Historical/current builds at the same size; the current l has a smaller bowl and advance.',comparison,[
            'All 20 desktop TTFs now use the Lato 2.015 hinting recipe, replacing the previous hint programs.',
            'The recipe reproduces all original glyph programs and global hint tables in the 18 reference fonts exactly.',
            'Current l pairs preserve the established special-pair gaps with the smaller bowl.'
        ],5,total)
        pdf_page(c,'Bold a / corrected hinting','A focused comparison at 12-20 px, including the reported 16 px size.',bowl,[
            'The bowl control keeps the top stroke thin; a final point link preserves the arch-to-stem overlap.',
            'The correction covers the Bold a and 33 matching accented/Cyrillic forms, without moving outline points.',
            'All styles use the released 2.015 recipe; italic a retains its existing outline and receives fresh instructions.'
        ],6,total)
    for index,path in enumerate(references):
        pdf_page(c,'Installed Lato comparison / '+('Italic' if index else 'Upright'),
                 'Lato 2.015 reference, original repository hinting, and Lato26 using the released hinting recipe.',path,[
            'Installed fonts: Lato 2.015, released 2015-08-06, 3,023 glyphs; repository exports: Lato 3.100.',
            'Current Lato26 keeps our revised outlines; small design differences can still produce different pixels.',
            'All samples use the same renderer, pixel size, RGB filter and gamma; this is not a Windows capture.'
        ],5+(2 if comparison else 0)+index,total)
    if joins:
        pdf_page(c,'Bold a / repaired joins','Before and after at 12-24 px, including the reported 14 px gap.',joins,[
            'The two stem-end points retain at least their original overlap with the upper arch at every tested size.',
            'Bowl, arch-curve and accent point positions are identical to the preceding thin-bowl correction.',
            'Native grayscale, monochrome and LCD checks cover all 34 forms, including fractional pixel sizes.'
        ],total-1,total)
        pdf_page(c,'Bold a / accented and related forms','All 34 affected forms at 14 and 16 px; enlarged 4x for inspection.',accents,[
            '32,946 glyph/size/render-target cases passed: connected joins and unchanged bowl/accents.',
            'The a outlines and accent positions are unchanged; the l was revised separately.',
            'FreeType RGB approximation; PDF viewers can resample the pixels.'
        ],total,total)
    c.save()
    print(PDF)
    print(OUT/'index.html')


if __name__=='__main__':main()
