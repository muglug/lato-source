#!/usr/bin/env python3
"""Validate exact 2.015 outlines, selective hints, source isolation and variables."""
import argparse
import ctypes as C
import hashlib
import importlib
import json
from pathlib import Path

import openstep_plist
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from connected_ligatures import TEXTS, recording
from lcd_font_proofs import RasterFace,set_size,load,render
from variable_font_support import ProofFace
from truetype_hinting import bytecode

build=importlib.import_module('07_build_revised_lato');ROOT=build.ROOT


def geometry(font,name):
    glyphs=font.getGlyphSet();pen=DecomposingRecordingPen(glyphs);glyphs[name].draw(pen)
    return pen.value


def measure(glyphs,name):
    bounds=BoundsPen(glyphs);area=AreaPen(glyphs)
    glyphs[name].draw(bounds);glyphs[name].draw(area)
    return bounds.bounds,area.value


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--snapshot',type=Path,required=True);args=ap.parse_args()
    report={'status':'running','static_fonts':[],'native_renders':0,'unrelated_glyphs_checked':0,'variable_checks':0,'sources':[]}
    for style in ('Upr','Ita'):
        source=build.Source(style);folder=ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
        for weight,design in build.WEIGHTS.items():
            label=weight if style=='Upr' else ('Italic' if weight=='Regular' else weight+'Italic')
            for ext in ('ttf','otf'):
                path=folder/f'Lato26-{label}.{ext}';font=TTFont(path);old=TTFont(args.snapshot/path.relative_to(ROOT))
                names={build.output_name(source,n,font):n for n in TEXTS}
                for tag in set(font.keys())-{'GlyphOrder','glyf','loca','head','hmtx','maxp','CFF '}:
                    assert font.getTableData(tag)==old.getTableData(tag),(path,tag)
                for n in font.getGlyphOrder():
                    assert font['hmtx'][n][0]==old['hmtx'][n][0],(path,n,'advance')
                    if n in names:continue
                    assert font['hmtx'][n]==old['hmtx'][n],(path,n,'metrics')
                    if ext=='ttf':assert font['glyf'][n].compile(font['glyf'])==old['glyf'][n].compile(old['glyf']),(path,n,'glyph changed')
                    else:assert geometry(font,n)==geometry(old,n),(path,n,'CFF outline changed')
                    report['unrelated_glyphs_checked']+=1
                for n,source_name in names.items():
                    rec=recording(style,source_name,design,exact=True)
                    if ext=='ttf':
                        assert geometry(font,n)==rec.value,(path,n,'not exact reference')
                        assert bytecode(font['glyf'][n]),(path,n,'missing hints')
                    expected=1 if source_name.endswith(('i','iogonek','istroke')) else 2
                    assert sum(op=='moveTo' for op,_ in geometry(font,n))==expected,(path,n,'contours')
                face=ProofFace(path)
                for n,text in TEXTS.items():
                    shaped=face.shaped(text);assert len(shaped)==1 and face.order[shaped[0][0]]==build.output_name(source,n,font),(path,text)
                if ext=='ttf':
                    native=RasterFace(path)
                    for ppem in [*range(8,51),64,72]:
                        assert set_size(native.handle,0,ppem*64,72,72)==0
                        for n in names:
                            for target,mode in ((0,0),(2,2),(3,3)):
                                assert load(native.handle,font.getGlyphID(n),(target<<16)|(1<<15)|(1<<7))==0,(path,n,ppem,target)
                                assert render(native.handle.contents.glyph,mode)==0,(path,n,ppem,mode)
                                report['native_renders']+=1
                report['static_fonts'].append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'restored_forms':len(names)})
            print(label,'exact reference outlines; unaffected outlines, metrics, layout and hints preserved',flush=True)
        suffix='Italic' if style=='Ita' else ''
        path=ROOT/f'build/Lato26-Variable/Lato26-Variable{suffix}.ttf';font=TTFont(path)
        largest=0
        for i,design in enumerate(build.WEIGHTS.values()):
            glyphs=font.getGlyphSet(location={'wght':100+i*100})
            for name in TEXTS:
                bounds,area=measure(glyphs,name);rec=recording(style,name,design,exact=True)
                bp=BoundsPen(None);ap=AreaPen(None);rec.replay(bp);rec.replay(ap)
                error=max(abs(a-b) for a,b in zip(bounds,bp.bounds));largest=max(largest,error)
                assert error<1.6,(style,name,design,error)
                assert abs(area-ap.value)<max(100,abs(ap.value)*.012),(style,name,design,'area',area,ap.value)
                report['variable_checks']+=1
        report.setdefault('maximum_variable_bounds_error',{})[style]=largest
        for relative in (f'sources/Lato3{style}2M.vfj',f'sources/Lato26-{ "Italic" if style=="Ita" else "Upright"}.glyphs'):
            p=ROOT/relative;oldp=args.snapshot/relative
            if p.suffix=='.vfj':
                a=json.loads(p.read_text());b=json.loads(oldp.read_text())
                a['font']['glyphs']=[g for g in a['font']['glyphs'] if g['name'] not in TEXTS]
                b['font']['glyphs']=[g for g in b['font']['glyphs'] if g['name'] not in TEXTS]
            else:
                a=openstep_plist.load(p.open(),use_numbers=True);b=openstep_plist.load(oldp.open(),use_numbers=True)
                a['glyphs']=[g for g in a['glyphs'] if g['glyphname'] not in TEXTS]
                b['glyphs']=[g for g in b['glyphs'] if g['glyphname'] not in TEXTS]
            assert a==b,(relative,'unrelated source changed')
            report['sources'].append(relative)
    report['status']='passed';(ROOT/'build/proofs/connected-ligature-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k not in ('static_fonts','sources')},flush=True)

if __name__=='__main__':main()
