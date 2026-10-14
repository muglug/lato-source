#!/usr/bin/env python3
"""Validate the smaller l, authored source preservation, hints and pair gaps."""
import argparse
import ctypes as C
import hashlib
import importlib
import json
import zipfile
from pathlib import Path

import numpy as np
import openstep_plist
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from lowercase_kerning import CONFIG, strip_spacing
from truetype_hinting import bytecode
from lcd_font_proofs import RasterFace, Matrix, Vector, transform, set_size, load, render

build=importlib.import_module('07_build_revised_lato')
spacing_check=importlib.import_module('24_check_l_bowl_spacing')
narrow=importlib.import_module('27_propagate_smaller_l')
ROOT=build.ROOT


def bounds(font,names):
    gs=font.getGlyphSet();result={}
    for name in names:
        pen=BoundsPen(gs);gs[name].draw(pen);result[name]=pen.bounds
    return result


def native_hint_check(record):
    """Execute the new instructions across the optimized ppem range."""
    result={'fonts':0,'glyphs':0,'native_loads':0,'native_rasterizations':0}
    for style,label in (('Upr','Light'),('Ita','LightItalic')):
        source=build.Source(style)
        paths=sorted((ROOT/f'build/Lato3{style}2M/ds-ufo/masters').glob('Lato26-*.ttf'))
        paths.append(ROOT/f'build/Carlito26/Carlito26-{label}.ttf')
        for path in paths:
            font=TTFont(path);face=RasterFace(path)
            matrix=Matrix(65536,0,0,65536);delta=Vector(0,0)
            transform(face.handle,C.byref(matrix),C.byref(delta))
            names=[build.output_name(source,n,font) for n in record['styles'][style]['glyphs']]
            ids=[font.getGlyphID(n) for n in names]
            for mode in (0,3):
                for size in (*range(8,51),64,200,201,256):
                    assert set_size(face.handle,0,size*64,72,72)==0
                    for name,gid in zip(names,ids):
                        error=load(face.handle,gid,(mode<<16)|(1<<15)|(1<<7)|(1<<3))
                        assert error==0,(path,name,size,mode,'load',error)
                        result['native_loads']+=1
                        if size<=50:
                            error=render(face.handle.contents.glyph,mode)
                            assert error==0,(path,name,size,mode,'render',error)
                            result['native_rasterizations']+=1
            result['fonts']+=1;result['glyphs']+=len(names)
            print(path.name,'revised l instructions passed grayscale/LCD execution',flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--snapshot',type=Path,required=True)
    args=parser.parse_args();record=json.loads(narrow.RECORD.read_text());config=json.loads(CONFIG.read_text())
    report={'fonts':[],'status':'running','unrelated_glyphs_preserved':0,'special_pairs_checked':0,
            'max_special_edge_gap_difference':0,'revised_glyphs_with_instructions':0}
    sources={s:build.Source(s) for s in ('Upr','Ita')}
    for filename,metadata in config['fonts'].items():
        path=ROOT/filename;old_path=args.snapshot/'before-build'/path.relative_to(ROOT/'build')
        a,z=TTFont(old_path),TTFont(path)
        style='Ita' if 'Ita2M' in filename else 'Upr';source=sources[style]
        changed={build.output_name(source,n,z) for n in record['styles'][style]['glyphs']}
        assert a.getGlyphOrder()==z.getGlyphOrder()
        for tag in set(a.keys())-{'GlyphOrder','head','hmtx','hhea','maxp','glyf','loca','GPOS','CFF '}:
            assert a.getTableData(tag)==z.getTableData(tag),(filename,tag)
        for name in z.getGlyphOrder():
            if name in changed:
                if 'glyf' in z and '.~VF' not in filename:
                    assert bytecode(z['glyf'][name]),(filename,name)
                    report['revised_glyphs_with_instructions']+=1
                continue
            assert a['hmtx'][name]==z['hmtx'][name],(filename,name,'metrics')
            if 'glyf' in z:
                assert a['glyf'][name].compile(a['glyf'])==z['glyf'][name].compile(z['glyf']),(filename,name,'glyf')
            else:
                aa=a['CFF '].cff.topDictIndex[0].CharStrings[name];zz=z['CFF '].cff.topDictIndex[0].CharStrings[name]
                aa.compile();zz.compile();assert aa.bytecode==zz.bytecode,(filename,name,'CFF')
            report['unrelated_glyphs_preserved']+=1
        before,after=spacing_check.pairs(a),spacing_check.pairs(z)
        assert before.keys()==after.keys()
        names={n for pair in before for n in pair};ab=bounds(a,names);zb=bounds(z,names)
        maximum=0
        for (left,right),kern in before.items():
            difference=(z['hmtx'][left][0]-a['hmtx'][left][0]+after[left,right]-kern
                        +zb[right][0]-ab[right][0]-zb[left][2]+ab[left][2])
            maximum=max(maximum,abs(difference))
            # Export-specific compensation absorbs curve conversion errors;
            # the remaining error is just integer kerning rounding.
            assert abs(difference)<=.501,(filename,left,right,difference)
            report['special_pairs_checked']+=1
        report['max_special_edge_gap_difference']=max(report['max_special_edge_gap_difference'],maximum)
        strip_spacing(a,metadata);strip_spacing(z,metadata)
        assert ('GPOS' in a)==('GPOS' in z)
        if 'GPOS' in a:assert a['GPOS'].compile(a)==z['GPOS'].compile(z)
        report['fonts'].append({'path':filename,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'edge_gap_max_difference':maximum})
        print(path.name,'maximum edge-gap rounding difference',round(maximum,4),flush=True)
    for style,label in (('Upr','Upright'),('Ita','Italic')):
        rel=Path(f'sources/Lato26-{label}.glyphs')
        a,z=[openstep_plist.loads(p.read_text(),use_numbers=True) for p in (args.snapshot/'before-source'/rel,ROOT/rel)]
        ga,gz=[{g['glyphname']:g for g in f['glyphs']} for f in (a,z)]
        for name in ga:
            if name not in record['styles'][style]['glyphs']:assert ga[name]==gz[name],(rel,name)
        if style=='Upr':
            mid='7E34DB9F-A80D-501A-A57E-0A6D858088AF'
            la,lz=[next(l for l in f['l']['layers'] if l['layerId']==mid) for f in (ga,gz)]
            assert la==lz,'Authored Regular l changed'
            generated=narrow.flat(build.revision.contours(narrow.export.blended_layer(sources['Upr'].glyphs['l'],540))[0])[[*range(1,16),0]]
            assert np.max(abs(generated-np.array([n[:2] for n in la['shapes'][0]['nodes']])))<.001
    for style,label in (('Upr','Light'),('Ita','LightItalic')):
        path=ROOT/f'build/Carlito26/Carlito26-{label}.ttf';old=args.snapshot/'before-build'/path.relative_to(ROOT/'build')
        a,z=TTFont(old),TTFont(path);changed=set(record['styles'][style]['glyphs'])
        assert {n:m[0] for n,m in a['hmtx'].metrics.items()}=={n:m[0] for n,m in z['hmtx'].metrics.items()}
        for tag in ('fpgm','prep','cvt ','gasp','GPOS','GSUB'):
            if tag in a:assert a.getTableData(tag)==z.getTableData(tag),(label,tag)
        for name in z.getGlyphOrder():
            if name not in changed:assert a['glyf'][name].compile(a['glyf'])==z['glyf'][name].compile(z['glyf']),(label,name)
        report['fonts'].append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    report['hint_execution']=native_hint_check(record)
    with zipfile.ZipFile(ROOT/'build/Lato26-Desktop.zip') as archive:
        packaged=0
        for name in archive.namelist():
            p=Path(name)
            if p.suffix not in ('.ttf','.otf'):continue
            style='Ita' if 'Italic' in p.name else 'Upr'
            path=(ROOT/f'build/Lato3{style}2M/ds-ufo/masters'/p.name if p.parts[0]=='Lato26' else ROOT/'build'/p)
            assert archive.read(name)==path.read_bytes(),('stale archive',name)
            extracted=ROOT/'build/Lato26-Desktop'/p
            if extracted.exists():assert extracted.read_bytes()==path.read_bytes(),('stale extracted copy',name)
            packaged+=1
        assert packaged==38
    report.update(status='passed',font_count=len(report['fonts']),authored_regular_preserved=True,
                  packaged_fonts_verified=packaged,
                  unrelated_hint_programs_preserved=True,carlito_advances_preserved=True)
    (ROOT/'build/proofs/smaller-l-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k!='fonts'},flush=True)


if __name__=='__main__':main()
