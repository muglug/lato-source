#!/usr/bin/env python3
"""Validate the four-master e import, preserved scope and native instructions."""
import argparse
import ctypes as C
import hashlib
import importlib
import json
import zipfile
from pathlib import Path

import numpy as np
import openstep_plist
from fontTools.ttLib import TTFont
from lcd_font_proofs import RasterFace,Matrix,Vector,transform,set_size,load,render
from truetype_hinting import bytecode

build=importlib.import_module('07_build_revised_lato')
export=importlib.import_module('11_export_editable_glyphs')
narrow=importlib.import_module('27_propagate_smaller_l')
ROOT=build.ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    args=parser.parse_args();record=json.loads(build.E_SHAPE.read_text());source=build.Source('Upr')
    report={'status':'running','fonts':[],'unchanged_italic_fonts':0,
            'unrelated_glyphs_preserved':0,'native_glyph_loads':0,'native_rasterizations':0,
            'ae_joins_checked':0}
    config=json.loads((ROOT/'sources/data/lowercase-spacing.json').read_text())
    paths=[ROOT/p for p in config['fonts']]
    paths += [ROOT/f'build/Carlito26/Carlito26-{name}.ttf' for name in ('Light','LightItalic')]
    for path in paths:
        old=args.snapshot/'before-build'/path.relative_to(ROOT/'build')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        report['fonts'].append({'path':str(path.relative_to(ROOT)),'sha256':digest})
        if 'Italic' in path.name:
            assert path.read_bytes()==old.read_bytes(),path
            report['unchanged_italic_fonts']+=1;continue
        a,z=TTFont(old),TTFont(path,checkChecksums=2)
        assert a.getGlyphOrder()==z.getGlyphOrder()
        changed={build.output_name(source,n,z) for n in record['glyphs']}
        assert {n:m[0] for n,m in a['hmtx'].metrics.items()}=={n:m[0] for n,m in z['hmtx'].metrics.items()}
        for tag in set(a.keys())-{'GlyphOrder','glyf','loca','CFF ','head','hmtx','hhea','maxp'}:
            assert a.getTableData(tag)==z.getTableData(tag),(path,tag)
        for name in z.getGlyphOrder():
            if name in changed:continue
            assert a['hmtx'][name]==z['hmtx'][name],(path,name,'metrics')
            if 'glyf' in z:
                assert a['glyf'][name].compile(a['glyf'])==z['glyf'][name].compile(z['glyf']),(path,name,'outline/hints')
            else:
                aa=a['CFF '].cff.topDictIndex[0].CharStrings[name]
                zz=z['CFF '].cff.topDictIndex[0].CharStrings[name]
                aa.compile();zz.compile();assert aa.bytecode==zz.bytecode,(path,name,'outline')
            report['unrelated_glyphs_preserved']+=1
        if path.suffix=='.ttf' and '.~VF' not in str(path):
            raster=RasterFace(path);matrix=Matrix(65536,0,0,65536);delta=Vector(0,0)
            transform(raster.handle,C.byref(matrix),C.byref(delta))
            for name in changed:assert bytecode(z['glyf'][name]),(path,name)
            for mode in (0,3):
                for size in (*range(8,51),64,200,201,256):
                    assert set_size(raster.handle,0,size*64,72,72)==0
                    for name in changed:
                        error=load(raster.handle,z.getGlyphID(name),(mode<<16)|(1<<15)|(1<<7)|(1<<3))
                        assert error==0,(path,name,size,mode,'load',error)
                        report['native_glyph_loads']+=1
                        if size<=50:
                            error=render(raster.handle.contents.glyph,mode)
                            assert error==0,(path,name,size,mode,'render',error)
                            report['native_rasterizations']+=1
        print(path.name,'scope, layout, advances and hint checks passed',flush=True)
    rel=Path('sources/Lato26-Upright.glyphs')
    a,z=[openstep_plist.loads(p.read_text(),use_numbers=True) for p in (args.snapshot/'before-source'/rel,ROOT/rel)]
    ga,gz=[{g['glyphname']:g for g in f['glyphs']} for f in (a,z)]
    for key in set(a)|set(z):
        if key!='glyphs':assert a.get(key)==z.get(key),key
    for name in ga:
        if name not in record['glyphs']:assert ga[name]==gz[name],name
        else:
            for la,lz in zip(ga[name]['layers'],gz[name]['layers']):
                assert {k:v for k,v in la.items() if k!='shapes'}=={k:v for k,v in lz.items() if k!='shapes'},name
    for design,layer in record['authored_layers'].items():
        saved=next(l for l in gz['e']['layers'] if l['layerId']==layer['layerId'])
        assert saved['shapes']==layer['shapes'] and saved['width']==layer['width']
        actual=export.blended_layer(source.glyphs['e'],int(design),source.intermediate_layers['e'])
        points=narrow.flat(build.revision.contours(actual)[0])[[*range(1,64),0]]
        assert np.max(abs(points-np.array([n[:2] for n in layer['shapes'][0]['nodes']])))<.00001
    for name in ('ae','aeTurned','aeTurnedmod'):
        for design in build.WEIGHTS.values():
            layer=export.blended_layer(source.glyphs[name],design,source.intermediate_layers[name])
            e,_,a=build.revision.contours(layer)
            for ai,ei in ((12,17),(13,16)):
                assert abs(build.revision.points(a['nodes'][ai])[-1,1]-build.revision.points(e['nodes'][ei])[-1,1])<.001,(name,design)
                report['ae_joins_checked']+=1
    for name in ('sources/Lato26-Italic.glyphs','sources/Lato3Ita2M.vfj','sources/data/lowercase-spacing.json'):
        assert (ROOT/name).read_bytes()==(args.snapshot/'before-source'/name).read_bytes(),name
    with zipfile.ZipFile(ROOT/'build/Lato26-Desktop.zip') as archive:
        count=0
        for filename in archive.namelist():
            p=Path(filename)
            if p.suffix not in ('.otf','.ttf'):continue
            style='Ita' if 'Italic' in p.name else 'Upr'
            path=ROOT/f'build/Lato3{style}2M/ds-ufo/masters'/p.name if p.parts[0]=='Lato26' else ROOT/'build'/p
            assert archive.read(filename)==path.read_bytes(),filename
            count+=1
        assert count==38
    report.update(status='passed',authored_master_count=4,updated_upright_forms=len(record['glyphs']),
                  advances_and_kerning_preserved=True,unrelated_hints_preserved=True,packaged_fonts_verified=count)
    (ROOT/'build/proofs/e-shape-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k!='fonts'},flush=True)


if __name__=='__main__':main()
