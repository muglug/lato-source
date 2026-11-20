#!/usr/bin/env python3
"""Verify release preservation, native hints, joins, and variable reconstruction."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont
from truetype_hinting import bytecode
from lato_vertical_metrics import assert_published_metrics
from lowercase_kerning import pair_advance
from variable_font_support import ProofFace,PairValues
import lcd_font_proofs as ft
base=importlib.import_module('41_rebase_on_lato2')
ROOT=base.ROOT


def geometry(gs,name):
    p=BoundsPen(gs);gs[name].draw(p)
    a=AreaPen(gs);gs[name].draw(a)
    return p.bounds,a.value


def check_static(directory):
    result=[]
    data=json.loads(base.PATCHES.read_text())
    for style in ('Upr','Ita'):
        for weight in base.WEIGHTS:
            path=directory/f'Lato26-{base.label(style,weight)}.ttf'
            font=TTFont(path);_,original,changed,_=base.prepare(style,weight)
            assert len(font.getGlyphOrder())==3023
            assert_published_metrics(font)
            for tag in ('fpgm','prep','cvt ','gasp','GSUB','cmap','OS/2','hhea'):
                assert font.getTableData(tag)==original.getTableData(tag),(path.name,tag)
            for name in font.getGlyphOrder():
                if name not in changed:
                    assert base.glyph_record(font['glyf'][name])==base.glyph_record(original['glyf'][name]),(path.name,name)
                    assert font['hmtx'][name]==original['hmtx'][name],(path.name,name)
                    assert bytecode(font['glyf'][name])==bytecode(original['glyf'][name]),(path.name,name)
            shape=ProofFace(path);native=ft.RasterFace(path)
            oldshape=ProofFace(base.REFERENCE/f'Lato-{base.label(style,weight)}.ttf')
            for text in ('fi','ffi','fį','ffį'):
                assert shape.shaped(text)==oldshape.shaped(text),(path.name,text)
                assert len(shape.shaped(text))==1,(path.name,text)
            for size in (12,14,16,20,36):
                assert ft.set_size(native.handle,0,size*64,72,72)==0
                for gid in range(len(font.getGlyphOrder())):
                    assert ft.load(native.handle,gid,(3<<16)|(1<<15)|(1<<7)|(1<<3))==0,(path.name,gid,size)
            gaps=data['styles'][style]['weights'][weight]['pair_gaps']
            gs=font.getGlyphSet();edges={n:geometry(gs,n)[0] for n in set(gaps)|{r for row in gaps.values() for r in row}}
            error=max(abs(font['hmtx'][l][0]+pair_advance(font,l,r)+edges[r][0]-edges[l][2]-gap) for l,row in gaps.items() for r,gap in row.items())
            assert error<=.50001,(path.name,error)
            otf_path=path.with_suffix('.otf');otf=TTFont(otf_path)
            for tag in ('cmap','GSUB','GPOS','OS/2','hhea','hmtx'):
                assert otf.getTableData(tag)==font.getTableData(tag),(otf_path.name,tag)
            otf_native=ft.RasterFace(otf_path);assert ft.set_size(otf_native.handle,0,16*64,72,72)==0
            for gid in range(3023):
                assert ft.load(otf_native.handle,gid,(3<<16)|(1<<15)|(1<<7))==0,(otf_path.name,gid)
                assert ft.render(otf_native.handle.contents.glyph,3)==0,(otf_path.name,gid)
            otf_glyphs=otf.getGlyphSet();otf_edges={n:geometry(otf_glyphs,n)[0] for n in edges}
            otf_error=max(abs(otf['hmtx'][l][0]+pair_advance(otf,l,r)+otf_edges[r][0]-otf_edges[l][2]-gap) for l,row in gaps.items() for r,gap in row.items())
            assert otf_error<=.50001,(otf_path.name,otf_error)
            result.append({'font':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'unchanged_glyphs':3023-len(changed),'pair_gap_error':error,
                           'otf_sha256':hashlib.sha256(otf_path.read_bytes()).hexdigest(),'otf_pair_gap_error':otf_error,'otf_native_renders':3023})
            print('Static verified',path.name,flush=True)
    return result


def check_bold(directory):
    path=directory/'Lato26-Bold.ttf';font=TTFont(path);face=ft.RasterFace(path)
    reference=list(font['glyf']['a'].coordinates[:60]);forms={}
    for name in font.getGlyphOrder():
        coords,ends,flags=font['glyf'][name].getCoordinates(font['glyf'])
        for start in [0]+[p+1 for p in ends[:-1]]:
            if start+60>len(coords):continue
            dx,dy=coords[start][0]-reference[0][0],coords[start][1]-reference[0][1]
            if all((x+dx,y+dy)==point for (x,y),point in zip(reference,coords[start:start+60])):
                forms[name]=start;break
    minimum=100;samples=[]
    for size in sorted(set(range(6,202))|{n/4 for n in range(32,201)}|{256}):
        for target in (0,2,3):
            basepoints=face.hinted_points('a',size,target)
            for name,start in forms.items():
                pts=basepoints if name=='a' else face.hinted_points(name,size,target)
                for lower,upper in ((29,2),(30,1)):
                    overlap=pts[start+lower][1]-pts[start+upper][1]
                    assert overlap>=-1e-8,(name,size,target,overlap)
                    minimum=min(minimum,overlap)
                # Composite accents must inherit the corrected bowl thickness.
                thickness=pts[start+57][1]-pts[start+58][1]
                expected=basepoints[57][1]-basepoints[58][1]
                assert abs(thickness-expected)<=1/64,(name,size,target,thickness,expected)
            if size in (12,14,16,18,20,24) and target==3:
                samples.append({'ppem':size,'bowl_top_px':basepoints[57][1]-basepoints[58][1]})
    print('Bold joins verified',len(forms),'simple/composite forms',flush=True)
    return {'forms':sorted(forms),'minimum_overlap_px':minimum,'samples':samples}


def check_variable(directory,static_dir):
    result=[];data=json.loads(base.PATCHES.read_text())
    for style in ('Upr','Ita'):
        path=directory/('Lato26-VariableItalic.ttf' if style=='Ita' else 'Lato26-Variable.ttf')
        font=TTFont(path);assert_published_metrics(font)
        assert font['post'].italicAngle==(-7 if style=='Ita' else 0)
        assert [(a.axisTag,a.minValue,a.defaultValue,a.maxValue) for a in font['fvar'].axes]==[('wght',100,400,900)]
        assert len(font['fvar'].instances)==9
        assert not any(t in font for t in ('fpgm','prep','cvt '))
        for i,weight in enumerate(base.WEIGHTS):
            value=100*(i+1);gs=font.getGlyphSet(location={'wght':value})
            static=TTFont(static_dir/f'Lato26-{base.label(style,weight)}.ttf');old=static.getGlyphSet()
            from fontTools.varLib.varStore import VarStoreInstancer
            metric_store=VarStoreInstancer(font['MVAR'].table.VarStore,font['fvar'].axes,font.normalizeLocation({'wght':value}))
            metric_records={r.ValueTag:r.VarIdx for r in font['MVAR'].table.ValueRecord}
            for field,tag in [('underlinePosition','undo'),('underlineThickness','unds')]:
                actual=getattr(font['post'],field)+metric_store[metric_records[tag]]
                assert abs(actual-getattr(static['post'],field))<1,(style,weight,field,actual)

            worst=(0,None);max_area=0;max_width=0
            for name in font.getGlyphOrder():
                a,area=geometry(old,name);b,other_area=geometry(gs,name)
                assert bool(a)==bool(b),(style,weight,name,a,b)
                if a:
                    error=max(abs(x-y) for x,y in zip(a,b))
                    if error>worst[0]:worst=(error,name)
                    assert error<2.01,(style,weight,name,'bounds error',error)
                    assert abs(area-other_area)<=max(150,.06*abs(area)),(style,weight,name,'area',area,other_area)
                    max_area=max(max_area,abs(area-other_area))
                width_error=abs(gs[name].width-static['hmtx'][name][0]);max_width=max(max_width,width_error)
                assert width_error<1.01,(style,weight,name,'advance',width_error)
            gaps=data['styles'][style]['weights'][weight]['pair_gaps']
            edges={n:geometry(gs,n)[0] for n in set(gaps)|{r for row in gaps.values() for r in row}}
            pairs=PairValues(font,value)
            gap_error=max(abs(gs[l].width+pairs(l,r)+edges[r][0]-edges[l][2]-gap) for l,row in gaps.items() for r,gap in row.items())
            assert gap_error<.51,(style,weight,'pair error',gap_error)
            native=ProofFace(path,value);oldshape=ProofFace(static_dir/f'Lato26-{base.label(style,weight)}.ttf')
            for text in ('fi','ffi','fį','ffį','IoloIolo'):
                actual,expected=native.shaped(text),oldshape.shaped(text)
                assert len(actual)==len(expected) and [g[0] for g in actual]==[g[0] for g in expected],(style,weight,text)
                limit=2 if text=='IoloIolo' else 1
                assert all(abs(a-b)<=limit for ga,gb in zip(actual,expected) for a,b in zip(ga[1:],gb[1:])),(style,weight,text,actual,expected)
            result.append({'font':path.name,'weight':weight,'maximum_bounds_error':worst[0],'worst_glyph':worst[1],'maximum_pair_gap_error':gap_error,'maximum_signed_area_error':max_area,'maximum_advance_error':max_width})
            print('Variable verified',style,weight,worst,gap_error,flush=True)
    return result


def check_native_variables(directory):
    set_design=ft.bind('FT_Set_Var_Design_Coordinates',ft.C.c_int,
        [ft.C.POINTER(ft.FaceRecord),ft.C.c_uint,ft.C.POINTER(ft.C.c_long)])
    count=0
    for name in ('Lato26-Variable.ttf','Lato26-VariableItalic.ttf'):
        face=ft.RasterFace(directory/name)
        for weight in range(100,901,50):
            coordinate=(ft.C.c_long*1)(weight*65536)
            assert set_design(face.handle,1,coordinate)==0
            assert (face.handle.contents.ascender,face.handle.contents.descender,face.handle.contents.height)==(1974,-426,2400)
            for size in (14,16,24):
                assert ft.set_size(face.handle,0,size*64,72,72)==0
                for gid in range(3023):
                    assert ft.load(face.handle,gid,(3<<16)|(1<<15)|(1<<7))==0,(name,weight,size,gid)
                    assert ft.render(face.handle.contents.glyph,3)==0,(name,weight,size,gid)
                    count+=1
        print('Native variable rendering verified',name,flush=True)
    return {'rendered_glyph_cases':count,'weights':list(range(100,901,50)),'ppem':[14,16,24]}


def check_sources(directory,masters,styles=('Upr','Ita')):
    from glyphsLib import GSFont,to_designspace
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    result=[]
    for style in styles:
        path=directory/f'Lato26-{"Italic" if style=="Ita" else "Upright"}.glyphs'
        source=GSFont(path)
        assert len(source.glyphs)==3023 and len(source.masters)==9 and len(source.instances)==9
        assert source.customParameters['Use Extension Kerning']
        assert all(left.startswith('@MMK_L_') and right.startswith('@MMK_R_')
                   for rows in source.kerning.values() for left,row in rows.items()
                   for right in row), 'Ungrouped reconstructed kerning can overflow Glyphs variable Text Preview'
        signatures={}
        for master,weight in zip(source.masters,base.WEIGHTS):
            font=TTFont(masters/f'Lato26-{base.label(style,weight)}.ttf');glyphs=font.getGlyphSet()
            assert master.italicAngle==-font['post'].italicAngle
            for field in ('underlinePosition','underlineThickness'):
                assert master.customParameters[field]==getattr(font['post'],field)

            layers={g.name:g.layers[master.id] for g in source.glyphs}
            for name,layer in layers.items():
                signature=([[n.type for n in p.nodes] for p in layer.paths],[c.name for c in layer.components])
                if name in signatures:assert signature==signatures[name],(style,weight,name,'source topology')
                else:signatures[name]=signature
                a,area=geometry(layers,name);b,original_area=geometry(glyphs,name)
                assert a==b or (a and b and max(abs(x-y) for x,y in zip(a,b))<1e-5),(style,weight,name,'source bounds')
                assert abs(area-original_area)<.01,(style,weight,name,'source area')
                assert layer.width==font['hmtx'][name][0],(style,weight,name,'source width')
            print('Source verified',style,weight,flush=True)
        test=TTFont();test.setGlyphOrder([g.name for g in source.glyphs])
        addOpenTypeFeaturesFromString(test,'\n'.join(prefix.code for prefix in source.featurePrefixes))
        assert 'GSUB' in test
        from ufo2ft.featureCompiler import FeatureCompiler
        designspace=to_designspace(source)
        FeatureCompiler(designspace.sources[3].font,ttFont=test).compile()
        assert all(tag in test for tag in ('GSUB','GPOS','GDEF'))
        for tag in ('GSUB','GPOS','GDEF'):test.getTableData(tag)
        result.append({'file':path.name,'masters':9,'glyphs':3023,'compatible_topology':True,'geometry_roundtrip':True,'substitutions_compile':True,'full_regular_layout_compiles':True})
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--static-dir',type=Path,default=ROOT/'build/Lato26-Desktop/Lato26/TTF')
    ap.add_argument('--variable-dir',type=Path,default=ROOT/'build/Lato26-Variable')
    ap.add_argument('--static-only',action='store_true');ap.add_argument('--variable-only',action='store_true')
    args=ap.parse_args();path=ROOT/'build/proofs/lato2-rebase-checks.json'
    report=json.loads(path.read_text()) if path.exists() and (args.static_only or args.variable_only) else {'base':'2.015','status':'passed'}
    if not args.variable_only:report.update(static=check_static(args.static_dir),bold_joins=check_bold(args.static_dir))
    if not args.static_only:
        report['variable']=check_variable(args.variable_dir,args.static_dir)
        report['native_variable']=check_native_variables(args.variable_dir)
    path=ROOT/'build/proofs/lato2-rebase-checks.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(path)
if __name__=='__main__':main()
