#!/usr/bin/env python3
"""Validate hint coverage, preserved geometry/layout, and real bytecode execution."""
import argparse
import ctypes as C
import importlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from truetype_hinting import assert_same_outlines, bytecode, hint_font
from lcd_font_proofs import RasterFace, Matrix, Vector, transform, set_size, load, render

build=importlib.import_module('07_build_revised_lato')
ROOT=build.ROOT


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--before-build',required=True,type=Path)
    args=ap.parse_args()
    report={'fonts':0,'glyph_outlines_preserved':0,'revised_glyphs_hinted':0,
            'native_glyph_loads':0,'native_rasterizations':0,'render_targets':['grayscale','LCD']}
    for style in ('Upr','Ita'):
        source=build.Source(style)
        paths=sorted((ROOT/f'build/Lato3{style}2M/ds-ufo/masters').glob('Lato26-*.ttf'))
        paths.append(ROOT/'build/Carlito26'/('Carlito26-LightItalic.ttf' if style=='Ita' else 'Carlito26-Light.ttf'))
        for path in paths:
            before=args.before_build/path.relative_to(ROOT/'build')
            old,font=TTFont(before),TTFont(path,checkChecksums=2)
            assert_same_outlines(old,font)
            assert old['hmtx'].metrics==font['hmtx'].metrics
            for tag in ('hmtx','hhea','name','cmap','GSUB','GPOS','GDEF','OS/2','post'):
                if tag in old:assert old.getTableData(tag)==font.getTableData(tag),(path,tag)
            assert old['head'].created==font['head'].created
            assert old['head'].modified==font['head'].modified
            assert 'TTFA' in font and all(tag in font for tag in ('fpgm','prep','cvt ','gasp'))
            required=[build.output_name(source,n,font) for n in source.affected]
            for name in required:assert bytecode(font['glyf'][name]),(path,name)
            face=RasterFace(path)
            matrix=Matrix(65536,0,0,65536);delta=Vector(0,0)
            transform(face.handle,C.byref(matrix),C.byref(delta))
            order=font.getGlyphOrder()
            ids=[font.getGlyphID(n) for n in required]
            # Every glyph at representative small/large sizes, and every revised
            # glyph at every optimized ppem. PEDANTIC makes bytecode errors fatal.
            for mode in (0,3):
                for size in range(8,51):
                    assert set_size(face.handle,0,size*64,72,72)==0
                    targets=range(len(order)) if size in (8,12,16,24,32,48) else ids
                    for gid in targets:
                        err=load(face.handle,gid,(mode<<16)|(1<<15)|(1<<7)|(1<<3))
                        assert err==0,(path,order[gid],size,mode,'load',err)
                        report['native_glyph_loads']+=1
                        err=render(face.handle.contents.glyph,mode)
                        assert err==0,(path,order[gid],size,mode,'render',err)
                        report['native_rasterizations']+=1
            for size in (64,200,201,256):
                assert set_size(face.handle,0,size*64,72,72)==0
                for gid in ids:
                    assert load(face.handle,gid,(3<<16)|(1<<15)|(1<<7)|(1<<3))==0
                    report['native_glyph_loads']+=1
            report['fonts']+=1
            report['glyph_outlines_preserved']+=len(order)
            report['revised_glyphs_hinted']+=len(required)
            print(path.name,'geometry, layout, and grayscale/LCD bytecode passed',flush=True)
    # Repeating the export hinting pass must not accumulate or change hints.
    p=ROOT/'build/Lato3Upr2M/ds-ufo/masters/Lato26-Regular.ttf'
    a=TTFont(p,recalcTimestamp=False);b=TTFont(p,recalcTimestamp=False)
    hint_font(b)
    for tag in ('glyf','fpgm','prep','cvt ','gasp','maxp','TTFA'):
        assert a.getTableData(tag)==b.getTableData(tag),('non-idempotent',tag)
    report['hint_pass_idempotent']=True
    report['status']='passed'
    output=ROOT/'build/proofs/truetype-hint-validation.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
