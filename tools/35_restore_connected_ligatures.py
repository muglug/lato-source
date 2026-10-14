#!/usr/bin/env python3
"""Restore Lato 2.015 fi/ffi and dependent forms, preserving Lato26 spacing.

Import once with --reference-dir; the JSON manifest makes subsequent rebuilds
independent of installed fonts. Exact quadratics go into static TTFs. Source
cubics split curves exactly and harmonize polyline vertices for interpolation.
"""
import argparse
import copy
import hashlib
import importlib
import json
import math
import re
from pathlib import Path

from fontTools.misc.bezierTools import splitQuadraticAtT
from fontTools.pens.basePen import decomposeQuadraticSegment
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.ttLib import TTFont
from glyphsLib import GSFont, GSLayer
import openstep_plist

from connected_ligatures import PATH, TEXTS, data, recording, selected_hinting
from vector_font_proofs import Face
build = importlib.import_module('07_build_revised_lato')
merge = importlib.import_module('27_propagate_smaller_l')
ROOT = build.ROOT


def merge_glyphs_only(text, updated, names):
    original=openstep_plist.loads(text,use_numbers=True)
    by_name={g['glyphname']:g for g in updated['glyphs']}
    replacements=[];start=re.search(r'^glyphs = \(',text,re.M).end()
    for glyph in original['glyphs']:
        start=text.index('{',start);end=merge.balanced_end(text,start)
        if glyph['glyphname'] in names:
            block=openstep_plist.dumps(by_name[glyph['glyphname']],indent=0,sort_keys=False)
            # Keep short point/coordinate arrays compact like the authored files.
            block=re.sub(r'\(\n([^(){}]+)\n\)',lambda m:'('+m[1].replace('\n','')+')'
                         if len(m[1].splitlines())<=6 else m[0],block)
            replacements.append((start,end,block))
        start=end
    for a,b,value in reversed(replacements):text=text[:a]+value+text[b:]
    assert openstep_plist.loads(text,use_numbers=True)==updated
    return text


def groups(value):
    """Rotate contours to a shared landmark and group consecutive straight edges."""
    contours=[]; segments=[]
    for op,pts in value:
        if op=='moveTo':
            start=last=pts[0];segments=[]
        elif op=='closePath':
            if last!=start:segments.append(('lineTo',last,[start]))
            if not contours:
                candidates=[(i,p[0]) for i,(kind,p,_) in enumerate(segments) if kind=='qCurveTo' and p[1]>500]
                idx=min(candidates,key=lambda it:it[1])[0]
                segments=segments[idx:]+segments[:idx]
            result=[]
            for kind,p,ps in segments:
                if kind=='lineTo' and result and result[-1][0]=='lineTo':result[-1][1].extend(ps)
                else:result.append((kind,[p]+list(ps)))
            contours.append(result)
        else:
            segments.append((op,last,list(pts)));last=pts[-1]
    return contours


def compatible(values):
    all_groups=[groups(v) for v in values]
    signature=lambda g:[[op for op,_ in c] for c in g]
    assert all(signature(g)==signature(all_groups[0]) for g in all_groups), [signature(g) for g in all_groups]
    result=[[] for _ in values]
    for ci,contour in enumerate(all_groups[0]):
        for out,g in zip(result,all_groups):out.append(('moveTo',[g[ci][0][1][0]]))
        for gi,(op,_) in enumerate(contour):
            paths=[g[ci][gi][1] for g in all_groups]
            if op=='lineTo':
                lengths=[]
                for path in paths:
                    ds=[math.dist(a,b) for a,b in zip(path,path[1:])]
                    total=sum(ds);assert total
                    cum=[0.]
                    for d in ds:cum.append(cum[-1]+d/total)
                    cum[-1]=1.;lengths.append(cum)
                stops=sorted(set(round(v,10) for cum in lengths for v in cum[1:]))
                for out,path,cum in zip(result,paths,lengths):
                    for t in stops:
                        i=next((i for i in range(len(cum)-1) if cum[i+1]>=t-1e-9),len(cum)-2)
                        u=max(0,min(1,(t-cum[i])/(cum[i+1]-cum[i])))
                        out.append(('lineTo',[tuple(a+(b-a)*u for a,b in zip(path[i],path[i+1]))]))
            else:
                assert op=='qCurveTo',op
                count=math.lcm(*(len(p)-2 for p in paths))
                for out,path in zip(result,paths):
                    current=path[0];pieces=decomposeQuadraticSegment(path[1:]);n=count//len(pieces)
                    for control,end in pieces:
                        for a,b,c in splitQuadraticAtT(current,control,end,*[i/n for i in range(1,n)]):
                            out.append(('curveTo',[tuple(x+2*(y-x)/3 for x,y in zip(a,b)),tuple(x+2*(y-x)/3 for x,y in zip(c,b)),c]))
                        current=end
        for out in result:out.append(('closePath',[]))
    return result


def import_references(directory):
    manifest={'reference_version':'2.015','note':'Exact static quadratics; compatible cubics preserve reference curves and polyline geometry at all nine weights. Current Lato26 advances are retained.','styles':{}}
    for style in ('Upr','Ita'):
        glyphs={n:{} for n in TEXTS};refs=[]
        for label,design in build.WEIGHTS.items():
            name=label if style=='Upr' else ('Italic' if label=='Regular' else label+'Italic')
            path=directory/f'Lato-{name}.ttf';font=TTFont(path);face=Face(path)
            assert '2.015' in font['name'].getDebugName(5),(path,font['name'].getDebugName(5))
            refs.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            for n,text in TEXTS.items():
                shaped=face.shaped(text);assert len(shaped)==1,(name,text)
                old=face.order[shaped[0][0]];pen=DecomposingRecordingPen(font.getGlyphSet());font.getGlyphSet()[old].draw(pen)
                glyphs[n][str(design)]={'quadratic':pen.value}
        for n,records in glyphs.items():
            try:curves=compatible([r['quadratic'] for r in records.values()])
            except AssertionError as e:raise AssertionError((style,n,e))
            for r,c in zip(records.values(),curves):r['cubic']=c
        manifest['styles'][style]={'references':refs,'glyphs':glyphs}
    PATH.write_text(json.dumps(manifest,separators=(',',':'))+'\n');data.cache_clear()


def vfj_layer(old,rec):
    layer=copy.deepcopy(old);contours=[];part=[]
    for op,pts in rec.value:
        part.append((op,pts))
        if op=='closePath':contours.append(build.revision.contour_from_recording(part));part=[]
    layer['elements']=[{'elementData':{'contours':contours}}]
    build.revision.clear_hints(layer)
    return layer


def update_sources():
    for style in ('Upr','Ita'):
        path=ROOT/f'sources/Lato3{style}2M.vfj';original=json.loads(path.read_text())['font']
        old={g['name']:g for g in original['glyphs']};new=copy.deepcopy(old)
        for name in TEXTS:
            for black,design in ((False,0),(True,1000)):
                layer=build.revision.master(new[name],black)
                replacement=vfj_layer(layer,recording(style,name,design,reverse=True))
                layer.clear();layer.update(replacement)
        # Some FontLab blocks contain escape spelling that differs from json.dumps.
        # Locate actual JSON object boundaries instead of reserializing a match.
        text=path.read_text();start=re.search(r'"glyphs"\s*:\s*\[',text).end()
        decoder=json.JSONDecoder();replacements=[]
        for glyph in original['glyphs']:
            start=text.index('{',start);parsed,end=decoder.raw_decode(text,start)
            assert parsed==glyph,glyph['name']
            if glyph['name'] in TEXTS:
                replacement=json.dumps(new[glyph['name']],indent=2,separators=(',',':'),ensure_ascii=False)
                replacement='\n'.join(('      ' if i else '')+line for i,line in enumerate(replacement.splitlines()))
                replacements.append((start,end,replacement))
            start=end
        for a,b,replacement in reversed(replacements):text=text[:a]+replacement+text[b:]
        assert json.loads(text)['font']['glyphs']==[new[g['name']] for g in original['glyphs']]
        path.write_text(text)
        gp=ROOT/f'sources/Lato26-{ "Italic" if style=="Ita" else "Upright"}.glyphs'
        original_text=gp.read_text();font=GSFont(gp)
        source=build.Source(style)
        for name in TEXTS:
            g=font.glyphs[name]
            for layer in list(g.layers):
                if layer.layerId.startswith('LATO2015-'):del g.layers[layer.layerId]
            for master in font.masters:
                layer=g.layers[master.id];layer.shapes=[];layer.hints=[]
                recording(style,name,master.axes[0],reverse=True).replay(layer.getPen())
            for design in (100,250,600,666,880):
                layer=GSLayer();layer.layerId=f'LATO2015-{name}-{design}'
                master=min(font.masters,key=lambda m:abs(m.axes[0]-design));layer.associatedMasterId=master.id
                layer.attributes['coordinates']=[design];layer.name='{'+str(design)+'}'
                layer.width=source.width(name,design)
                recording(style,name,design,reverse=True).replay(layer.getPen());g.layers.append(layer)
        temp=Path('/tmp/lato-connected-ligatures')/gp.name;font.save(temp)
        updated=openstep_plist.load(temp.open(),use_numbers=True);original_plist=openstep_plist.loads(original_text,use_numbers=True)
        original_plist['glyphs']=[next(g for g in updated['glyphs'] if g['glyphname']==old['glyphname']) if old['glyphname'] in TEXTS else old for old in original_plist['glyphs']]
        gp.write_text(merge_glyphs_only(original_text,original_plist,set(TEXTS)))
    # The single-master Regular export uses legacy production names/format 4.
    gp=build.REGULAR;original_text=gp.read_text();obj=openstep_plist.loads(original_text,use_numbers=True)
    source=build.Source('Upr');font=TTFont(gp.with_suffix('.ttf'))
    for g in obj['glyphs']:
        match=next((n for n in TEXTS if build.output_name(source,n,font)==g['glyphname'] or n==g['glyphname']),None)
        if not match:continue
        l=GSLayer();recording('Upr',match,540,reverse=True).replay(l.getPen())
        kinds={'line':'l','curve':'c','offcurve':'o','qcurve':'q'}
        g['layers'][0]['shapes']=[{'closed':1,'nodes':[[round(n.position.x,6),round(n.position.y,6),kinds[n.type]] for n in p.nodes]} for p in l.paths]
        g['layers'][0].pop('hints',None)
    names={g['glyphname'] for g in obj['glyphs'] if g['glyphname'] in TEXTS or g['glyphname'] in {build.output_name(source,n,font) for n in TEXTS}}
    gp.write_text(merge_glyphs_only(original_text,obj,names))


def update_fonts():
    for style in ('Upr','Ita'):
        source=build.Source(style);directory=ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
        for label,design in build.WEIGHTS.items():
            label=label if style=='Upr' else ('Italic' if label=='Regular' else label+'Italic')
            for ext in ('ttf','otf'):
                path=directory/f'Lato26-{label}.{ext}';font=TTFont(path,recalcTimestamp=False);changed=[]
                for name in TEXTS:
                    out=build.output_name(source,name,font);rec=recording(style,name,design,exact=True)
                    width=font['hmtx'][out][0]
                    if ext=='ttf':
                        pen=TTGlyphPen(None);rec.replay(pen);font['glyf'][out]=pen.glyph()
                    else:
                        top=font['CFF '].cff.topDictIndex[0];pen=T2CharStringPen(width,None)
                        rec.replay(Qu2CuPen(ReverseContourPen(pen),max_err=.01,all_cubic=True))
                        top.CharStrings[out]=pen.getCharString(private=top.Private,globalSubrs=font['CFF '].cff.GlobalSubrs)
                    build.update_metrics(font,out,width,rec);changed.append(out)
                    if ext=='ttf':
                        font['glyf'][out].recalcBounds(font['glyf'])
                        font['hmtx'][out]=width,font['glyf'][out].xMin
                if ext=='ttf':selected_hinting(font,changed)
                font.save(path);print(path.name,flush=True)
        # Keep the legacy two endpoint TTFs point-compatible for downstream builds.
        suffix='Italic' if style=='Ita' else ''
        paths=[directory/'Lato26.~VF/master_ttf_interpolatable'/f'Lato26-{w}{suffix}.ttf' for w in ('Hairline','Black')]
        fonts=[TTFont(p,recalcTimestamp=False) for p in paths]
        for name in TEXTS:
            recs=[recording(style,name,d) for d in (0,1000)]
            pens=[TTGlyphPen(None),TTGlyphPen(None)];multi=Cu2QuMultiPen(pens,max_err=.5)
            for (op,a),(_,b) in zip(*(r.value for r in recs)):
                if op=='closePath':multi.closePath()
                else:getattr(multi,op)([a,b])
            for font,pen,rec in zip(fonts,pens,recs):
                out=build.output_name(source,name,font);font['glyf'][out]=pen.glyph()
                build.update_metrics(font,out,font['hmtx'][out][0],rec)
        for font,path in zip(fonts,paths):font.save(path)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--reference-dir',type=Path)
    ap.add_argument('--sources',action='store_true');ap.add_argument('--fonts',action='store_true');args=ap.parse_args()
    if args.reference_dir:import_references(args.reference_dir)
    if args.sources:update_sources()
    if args.fonts:update_fonts()

if __name__=='__main__':main()
