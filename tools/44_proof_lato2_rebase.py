#!/usr/bin/env python3
"""Vector comparisons and native-hint samples for the Lato 2.015 rebase."""
import argparse
import importlib
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from variable_font_support import ProofFace
from lcd_font_proofs import RasterFace,GAMMA
base=importlib.import_module('41_rebase_on_lato2');ROOT=base.ROOT


def label(c,text,x,y,size=10,color='#566374',bold=False):
    c.setFillColor(HexColor(color));c.setFont('Helvetica-Bold' if bold else 'Helvetica',size);c.drawString(x,y,text)


def specimen(c,face,text,x,y,size,color='#192a39'):
    c.saveState();c.setFillColor(HexColor(color));c.translate(x,y);c.scale(size/face.upm,size/face.upm)
    cursor=0
    for gid,advance,_,dx,dy in face.shaped(text):
        c.saveState();c.translate(cursor+dx,dy);c.drawPath(face.outline(gid,c),fill=1,stroke=0,fillMode=1);c.restoreState();cursor+=advance
    c.restoreState()
    return cursor*size/face.upm


def old_path(style,weight,snapshot):
    rel=Path(f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{base.label(style,weight)}.ttf')
    path=snapshot/rel
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(subprocess.check_output(['git','show','fe9eda744:'+str(rel)],cwd=ROOT))
    return path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--static-dir',type=Path,default=ROOT/'build/Lato26-Desktop/Lato26/TTF')
    ap.add_argument('--variable-dir',type=Path,default=ROOT/'build/Lato26-Variable')
    ap.add_argument('--snapshot',type=Path,default=ROOT/'.cache/lato2-before')
    ap.add_argument('--output',type=Path,default=ROOT/'output/pdf/Lato26-Lato-2.015-Rebase.pdf')
    args=ap.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(args.output),pagesize=(1080,780),pageCompression=1)
    c.setTitle('Lato26 on Lato 2.015 - outlines, spacing, variable fonts and hints')
    page=0
    def header(title,subtitle):
        nonlocal page
        page+=1
        c.setFillColor(HexColor('#fafbf9'));c.rect(0,0,1080,780,fill=1,stroke=0)
        label(c,title,36,735,25,'#192a39',True);label(c,subtitle,36,710,11)
        c.setStrokeColor(HexColor('#d9dfe5'));c.line(36,693,1044,693)
        label(c,'Lato26 / published Lato 2.015 base - 2,000 units per em',36,25,9)
        label(c,str(page),1024,25,9)
    for weight in base.WEIGHTS:
        header(weight+' - before and after','Published 2.015, previous Lato26 on 3.100, and Lato26 rebuilt on 2.015. Same size and baseline.')
        for si,style in enumerate(('Upr','Ita')):
            y=661-si*292
            label(c,'UPRIGHT' if style=='Upr' else 'ITALIC',36,y,11,'#192a39',True)
            paths=[base.REFERENCE/f'Lato-{base.label(style,weight)}.ttf',old_path(style,weight,args.snapshot),args.static_dir/f'Lato26-{base.label(style,weight)}.ttf']
            for ci,(title,path) in enumerate(zip(('Original Lato 2.015','Previous Lato26','Rebased Lato26'),paths)):
                x=36+ci*344;face=ProofFace(path)
                label(c,title,x,y-28,11,'#246878' if ci==2 else '#566374',True)
                for ri,chars in enumerate(('abcdefghijklm','nopqrstuvwxyz')):
                    specimen(c,face,' '.join('l'+ch for ch in chars),x,y-66-ri*34,22)
                specimen(c,face,'a á ä  æ  e é ë  œ  l ł ľ',x,y-140,27)
                specimen(c,face,'fi ffi  IoloIolo  l. l, l: l;',x,y-181,24)
                specimen(c,face,'A little clarity. All quietly well.',x,y-225,21)
        label(c,'All la-lz pairs are shown. The reviewed outline-edge gaps are retained to within half a font unit in static exports.',36,62,10)
        c.showPage()
    for style in ('Upr','Ita'):
        header('Variable '+('italic' if style=='Ita' else 'upright'),'Nine release weights, with intermediate weights shown between them. These variable fonts are unhinted.')
        path=args.variable_dir/('Lato26-VariableItalic.ttf' if style=='Ita' else 'Lato26-Variable.ttf')
        for i,weight in enumerate(range(100,901,50)):
            col,row=divmod(i,9);x=36+520*col;y=655-row*64
            label(c,str(weight),x,y,11,'#246878',True)
            face=ProofFace(path,weight)
            specimen(c,face,'la le lo ly  a e fi ffi',x+52,y,28)
            specimen(c,face,'IoloIolo   little clarity.   l. l: l;',x+52,y-25,19)
        label(c,'Named weights retain the release silhouettes within curve-conversion rounding; interpolation is reconstructed from published binaries.',36,60,10)
        c.showPage()
    header('Bold a - native TrueType hint samples','FreeType RGB subpixel simulation, enlarged 4x. This is a hint inspection proof, not a Windows DirectWrite capture.')
    paths=[base.REFERENCE/'Lato-Bold.ttf',old_path('Upr','Bold',args.snapshot),args.static_dir/'Lato26-Bold.ttf']
    for ci,(title,path) in enumerate(zip(('Original Lato 2.015','Previous Lato26 / corrected','Rebased Lato26 / corrected'),paths)):
        x=36+ci*344;label(c,title,x,655,11,'#192a39',True);face=RasterFace(path)
        for ri,size in enumerate((12,14,16,20,24)):
            y=608-ri*108;label(c,str(size)+' px',x,y,10)
            alpha,margin,baseline,advance=face.coverage('aáäą',size,'rgb')
            rgb=np.round(255*(1-alpha)**(1/GAMMA)).clip(0,255).astype('uint8')
            image=Image.fromarray(rgb)
            box=Image.fromarray((255-rgb).max(axis=2)).getbbox();image=image.crop((box[0]-2,box[1]-2,box[2]+2,box[3]+2))
            image=image.resize((image.width*4,image.height*4),Image.Resampling.NEAREST)
            c.drawImage(ImageReader(image),x+48,y-48,width=image.width,height=image.height)
    label(c,'The revised bowl keeps its thinner top stroke. Join instructions also reach the accented forms through their original 2.015 components.',36,62,10)
    c.showPage();c.save();print(args.output, page,'pages')
if __name__=='__main__':main()
