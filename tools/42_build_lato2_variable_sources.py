#!/usr/bin/env python3
"""Reconstruct nine compatible masters from the edited 2.015 release fonts."""
import argparse
import copy
import importlib
import json
import re
import hashlib
from collections import defaultdict
from pathlib import Path
import uuid

import glyphsLib.classes as gs
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor, InstanceDescriptor
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import build as build_variable
from lato2_compatible_outlines import compatible
from lato_vertical_metrics import GLYPHS_PARAMETERS, assert_published_metrics

base=importlib.import_module('41_rebase_on_lato2')
ROOT=base.ROOT
WEIGHTS=list(base.WEIGHTS)


def compatible_masters(style, input_dir, cache):
    fonts=[TTFont(input_dir/f'Lato26-{base.label(style,w)}.ttf',recalcTimestamp=False) for w in WEIGHTS]
    glyphsets=[f.getGlyphSet() for f in fonts]
    report={'style':style,'contour_fallbacks':{},'ghost_contours':[],'preserved_composites':0}
    replacements=[{} for _ in fonts]
    for index,name in enumerate(fonts[0].getGlyphOrder()):
        glyphs=[f['glyf'][name] for f in fonts]
        if all(g.isComposite() for g in glyphs) and all([c.glyphName for c in g.components]==[c.glyphName for c in glyphs[0].components] for g in glyphs):
            # Scale matrices must agree: gvar varies offsets, not component scales.
            transforms=[[c.getComponentInfo()[1][:4] for c in g.components] for g in glyphs]
            if all(v==transforms[0] for v in transforms):
                report['preserved_composites']+=1
                for target,g in zip(replacements,glyphs):
                    target[name]=copy.deepcopy(g);target[name].removeHinting()
                continue
        values=[]
        for glyphset in glyphsets:
            pen=DecomposingRecordingPen(glyphset);glyphset[name].draw(pen);values.append(pen.value)
        recordings,meta=compatible(values,default=3)
        if meta['fallback_contours']:report['contour_fallbacks'][name]=meta['fallback_contours']
        if meta['ghost_contours']:report['ghost_contours'].append(name)
        pens=[TTGlyphPen(None,outputImpliedClosingLine=True) for _ in fonts]
        multi=Cu2QuMultiPen(pens,max_err=.25)
        for commands in zip(*(r.value for r in recordings)):
            op=commands[0][0]
            if op in ('closePath','endPath'):getattr(multi,op)()
            else:getattr(multi,op)([args for _,args in commands])
        new=[p.glyph() for p in pens]
        signature=lambda g:(g.numberOfContours,tuple(g.endPtsOfContours) if g.numberOfContours>0 else (),tuple(g.flags) if g.numberOfContours>0 else ())
        assert all(signature(g)==signature(new[0]) for g in new),name
        for target,g in zip(replacements,new):target[name]=g
        if index%250==0:print(style,index,name,flush=True)
    cache.mkdir(parents=True,exist_ok=True)
    for weight,font,new in zip(WEIGHTS,fonts,replacements):
        font['glyf'].glyphs=new
        for name in font.getGlyphOrder():
            g=font['glyf'][name];g.recalcBounds(font['glyf'])
            advance,lsb=font['hmtx'][name]
            font['hmtx'][name]=(advance,getattr(g,'xMin',lsb))
        for tag in ('fpgm','prep','cvt ','gasp','TTFA','hdmx','VDMX','LTSH','DSIG'):
            if tag in font:del font[tag]
        font['head'].flags &= ~0x1c
        post_values={key:getattr(font['post'],key) for key in ('italicAngle','underlinePosition','underlineThickness','isFixedPitch','minMemType42','maxMemType42','minMemType1','maxMemType1')}
        FontBuilder(font=font).setupPost(keepGlyphNames=True,**post_values)
        font.save(cache/f'Lato26-{base.label(style,weight)}.ttf')
    (cache/f'{style}-compatibility.json').write_text(json.dumps(report,indent=2)+'\n')
    return fonts,report


def designspace(fonts,style):
    doc=DesignSpaceDocument();axis=AxisDescriptor()
    axis.name='Weight';axis.tag='wght';axis.minimum=100;axis.default=400;axis.maximum=900
    # Master coordinates use standard CSS weights; all nine released designs
    # are retained, so no additional non-linear weight mapping is necessary.
    doc.addAxis(axis)
    for i,(weight,font) in enumerate(zip(WEIGHTS,fonts)):
        source=SourceDescriptor();source.name=weight;source.font=font
        source.location={'Weight':100*(i+1)};source.familyName='Lato26 Variable';source.styleName=weight
        if weight=='Regular':source.copyInfo=source.copyLib=source.copyFeatures=True
        doc.addSource(source)
        inst=InstanceDescriptor();inst.name=base.label(style,weight)
        inst.familyName='Lato26 Variable';inst.styleName=inst.name;inst.location=source.location
        doc.addInstance(inst)
    return doc


def complete_variable_anchors(fonts):
    """Fill release coverage holes only in reconstructed variable masters.

    The released mark-to-base coverage grows with weight. Variable GPOS cannot
    interpolate from an absent default anchor. Use the nearest released anchor
    for missing entries; existing entries remain exact. Static fonts keep the
    original coverage unchanged. Record every reconstructed entry.
    """
    additions=[]
    for li,lookup in enumerate(fonts[3]['GPOS'].table.LookupList.Lookup):
        for si,sub in enumerate(lookup.SubTable):
            if lookup.LookupType!=9 or sub.ExtensionLookupType!=4:continue
            tables=[f['GPOS'].table.LookupList.Lookup[li].SubTable[si].ExtSubTable for f in fonts]
            for role in ('Base','Mark'):
                mappings=[dict(zip(getattr(t,role+'Coverage').glyphs,getattr(getattr(t,role+'Array'),role+'Record'))) for t in tables]
                names=sorted(set().union(*(m.keys() for m in mappings)),key=fonts[3].getGlyphID)
                available={name:[i for i,m in enumerate(mappings) if name in m] for name in names}
                for i,(table,mapping) in enumerate(zip(tables,mappings)):
                    for name in names:
                        if name not in mapping:
                            nearest=min(available[name],key=lambda j:abs(j-i))
                            mapping[name]=copy.deepcopy(mappings[nearest][name])
                            additions.append({'weight':WEIGHTS[i],'glyph':name,'lookup':li,'role':role,'from':WEIGHTS[nearest]})
                    getattr(table,role+'Coverage').glyphs=names.copy()
                    setattr(getattr(table,role+'Array'),role+'Record',[mapping[n] for n in names])
                    setattr(getattr(table,role+'Array'),role+'Count',len(names))
    return additions


def compensate_variable_gaps(variable,style):
    """Add exact integer corrections at named weights with triangular supports.

    A second varLib merge can round model deltas again. A private variation
    store instead retains each measured correction directly at its own stop.
    """
    from fontTools.misc.roundTools import otRound
    from fontTools.otlLib.builder import buildLookup,buildPairPosGlyphs,buildValue
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.varLib.builder import buildVarDevTable
    from fontTools.varLib.varStore import OnlineVarStoreBuilder
    from variable_font_support import PairValues
    config=json.loads(base.PATCHES.read_text())['styles'][style]['weights']
    values=defaultdict(list);locations=[];maximum=0
    for i,weight in enumerate(WEIGHTS):
        location=100*(i+1);locations.append(variable.normalizeLocation({'wght':location})['wght'])
        glyphs=variable.getGlyphSet(location={'wght':location});kern=PairValues(variable,location)
        gaps=config[weight]['pair_gaps'];edges={}
        for name in set(gaps)|{r for row in gaps.values() for r in row}:
            pen=BoundsPen(glyphs);glyphs[name].draw(pen);edges[name]=pen.bounds
        for left,row in gaps.items():
            for right,gap in row.items():
                actual=glyphs[left].width+kern(left,right)+edges[right][0]-edges[left][2]
                delta=otRound(gap-actual);maximum=max(maximum,abs(delta))
                values[left,right].append(delta)
    default=3;indices=[i for i in range(9) if i!=default]
    supports=[{'wght':(locations[max(i-1,0)],locations[i],locations[min(i+1,8)])} for i in indices]
    builder=OnlineVarStoreBuilder(['wght']);builder.setSupports(supports)
    old_store=variable['GDEF'].table.VarStore;outer_offset=len(old_store.VarData);pairs={}
    for key,stops in values.items():
        fields={'XAdvance':stops[default]};deltas=[stops[i]-stops[default] for i in indices]
        if any(deltas):fields['XAdvDevice']=buildVarDevTable(builder.storeDeltas(deltas)+(outer_offset<<16))
        pairs[key]=(buildValue(fields),None)
    additions=builder.finish();region_offset=len(old_store.VarRegionList.Region)
    old_store.VarRegionList.Region.extend(additions.VarRegionList.Region)
    old_store.VarRegionList.RegionCount=len(old_store.VarRegionList.Region)
    for data in additions.VarData:
        data.VarRegionIndex=[i+region_offset for i in data.VarRegionIndex];old_store.VarData.append(data)
    old_store.VarDataCount=len(old_store.VarData)
    lookup=buildLookup(buildPairPosGlyphs(pairs,variable.getReverseGlyphMap()))
    table=variable['GPOS'].table;index=len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(lookup);table.LookupList.LookupCount=index+1
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag=='kern':record.Feature.LookupListIndex.append(index);record.Feature.LookupCount+=1
    return maximum


def export_variable(fonts,style,output):
    variable_masters=copy.deepcopy(fonts)
    anchors=complete_variable_anchors(variable_masters)
    font,_,_=build_variable(designspace(variable_masters,style),optimize=True)
    compensation=compensate_variable_gaps(font,style)
    print(style,'maximum variable spacing compensation',compensation,flush=True)
    importlib.import_module('32_build_variable_fonts').normalize_names(font,style=='Ita')
    assert_published_metrics(font)
    output.mkdir(parents=True,exist_ok=True)
    path=output/('Lato26-VariableItalic.ttf' if style=='Ita' else 'Lato26-Variable.ttf')
    font.save(path)
    (output/f'{style}-anchor-reconstruction.json').write_text(json.dumps(anchors,indent=2)+'\n')
    font.flavor='woff2';font.save(path.with_suffix('.woff2'))
    print('Variable:',path,flush=True)
    return path


def export_glyphs(fonts,style,path):
    from fontFeatures.ttLib import unparse
    from truetype_hinting import GLYPHS_OPTIONS
    fonts=copy.deepcopy(fonts);complete_variable_anchors(fonts)
    font=gs.GSFont();font.format_version=3;font.familyName='Lato26'
    font.upm=2000;font.versionMajor=2;font.versionMinor=26
    font.axes=[gs.GSAxis('Weight','wght')]
    font.disablesAutomaticAlignment=True;font.disablesNiceNames=True
    font.customParameters["Don't use Production Names"]=True
    font.customParameters['Use Extension Kerning']=True
    for key,value in GLYPHS_PARAMETERS.items():font.customParameters[key]=value
    for attr,nid in [('copyright',0),('designer',9),('designerURL',12),('manufacturer',8),('manufacturerURL',11)]:
        setattr(font,attr,fonts[3]['name'].getDebugName(nid) or '')
    for key,nid in [('license',13),('licenseURL',14),('trademark',7)]:font.customParameters[key]=fonts[3]['name'].getDebugName(nid) or ''
    font.userData['Lato26.base']='Published Lato 2.015 TTFs; reconstructed quadratic masters, nine named weights.'
    for i,(weight,source) in enumerate(zip(WEIGHTS,fonts)):
        master=gs.GSFontMaster();master.id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'Lato26/2.015/{style}/{weight}')).upper()
        master.name=base.label(style,weight);master.axes=[100*(i+1)]
        master.ascender=source['OS/2'].sTypoAscender;master.descender=source['OS/2'].sTypoDescender
        master.xHeight=source['OS/2'].sxHeight;master.capHeight=source['OS/2'].sCapHeight
        master.italicAngle=-source['post'].italicAngle
        for key in ('underlinePosition','underlineThickness'):master.customParameters[key]=getattr(source['post'],key)
        font.masters.append(master)
        instance=gs.GSInstance();instance.name=master.name;instance.axes=master.axes.copy()
        instance.isItalic=style=='Ita';instance.isBold=weight=='Bold'
        instance.customParameters['weightClass']=100*(i+1)
        instance.customParameters['Autohint']=True;instance.customParameters['TTFAutohint options']=GLYPHS_OPTIONS
        font.instances.append(instance)
    font.customParameters['Variable Font Origin']=font.masters[3].id
    cmaps={}
    for code,name in fonts[3].getBestCmap().items():cmaps.setdefault(name,[]).append(f'{code:04X}')
    for name in fonts[3].getGlyphOrder():
        glyph=gs.GSGlyph(name);glyph.unicodes=cmaps.get(name,[]);font.glyphs.append(glyph)
        for master,source in zip(font.masters,fonts):
            layer=gs.GSLayer();layer.layerId=layer.associatedMasterId=master.id
            glyph.layers.append(layer);layer.width=source['hmtx'][name][0]
            source['glyf'][name].draw(layer.getPen(),source['glyf'])
    # Recover the original substitutions. The native GPOS data are imported as
    # editable per-master pairs and anchors, rather than frozen Regular values.
    substitutions=copy.deepcopy(fonts[3]);del substitutions['GPOS']
    if 'GDEF' in substitutions:del substitutions['GDEF']
    feature_text=re.sub(r'table GDEF \{\s*GlyphClassDef \[\], \[\], \[\], \[\];\s*\} GDEF;', '', unparse(substitutions).asFea())
    feature_lines=[line.rstrip() for line in feature_text.splitlines()]
    language_lines=[line for line in feature_lines if line.startswith('languagesystem ')]
    language_lines.sort(key=lambda line:line!='languagesystem DFLT dflt;')
    feature_code='\n'.join(language_lines+[line for line in feature_lines if not line.startswith('languagesystem ')])
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    feature_test=TTFont();feature_test.setGlyphOrder(fonts[3].getGlyphOrder())
    addOpenTypeFeaturesFromString(feature_test,feature_code)
    prefix=gs.GSFeaturePrefix('Lato 2.015 substitutions',feature_code)
    font.featurePrefixes.append(prefix)
    pairs=[import_positioning(font,master,source) for master,source in zip(font.masters,fonts)]
    compress_kerning(font,pairs)
    mark=gs.GSFeature('mark','');mark.automatic=True;font.features.append(mark)
    font.save(path)
    print('Editable:',path,Path(path).stat().st_size,flush=True)


def import_positioning(font,master,source):
    # Flatten lookup precedence before dropping zero values. No class kerning
    # remains, so individual zero exceptions no longer need explicit records.
    order=source.getGlyphOrder();kerning={}
    indices={i for rec in source['GPOS'].table.FeatureList.FeatureRecord if rec.FeatureTag=='kern' for i in rec.Feature.LookupListIndex}
    for lookup_index,lookup in enumerate(source['GPOS'].table.LookupList.Lookup):
        handled=set();covered_lefts=set()
        for sub in lookup.SubTable:
            kind=lookup.LookupType
            if kind==9:kind=sub.ExtensionLookupType;sub=sub.ExtSubTable
            if kind==2 and lookup_index in indices:
                if sub.Format==1:
                    for left,pairset in zip(sub.Coverage.glyphs,sub.PairSet):
                        for record in pairset.PairValueRecord:
                            key=(left,record.SecondGlyph)
                            if left in covered_lefts or key in handled:continue
                            handled.add(key);value=getattr(record.Value1,'XAdvance',0) if record.Value1 else 0
                            kerning[key]=kerning.get(key,0)+value
                else:
                    classes=defaultdict(list)
                    for right in order:classes[sub.ClassDef2.classDefs.get(right,0)].append(right)
                    for left in sub.Coverage.glyphs:
                        if left in covered_lefts:continue
                        row=sub.Class1Record[sub.ClassDef1.classDefs.get(left,0)]
                        for ci,record in enumerate(row.Class2Record):
                            value=getattr(record.Value1,'XAdvance',0) if record.Value1 else 0
                            if not value:continue
                            for right in classes[ci]:
                                key=(left,right)
                                if key not in handled:kerning[key]=kerning.get(key,0)+value
                        covered_lefts.add(left)
            elif kind==4:
                for name,record in zip(sub.MarkCoverage.glyphs,sub.MarkArray.MarkRecord):
                    anchor=record.MarkAnchor;tag=f'attach{lookup_index}c{record.Class}'
                    glyph=font.glyphs[name];glyph.category='Mark'
                    if not source['hmtx'][name][0]:glyph.subCategory='Nonspacing'
                    glyph.layers[master.id].anchors.append(gs.GSAnchor('_'+tag,(anchor.XCoordinate,anchor.YCoordinate)))
                for name,record in zip(sub.BaseCoverage.glyphs,sub.BaseArray.BaseRecord):
                    for i,anchor in enumerate(record.BaseAnchor):
                        if anchor:
                            font.glyphs[name].layers[master.id].anchors.append(gs.GSAnchor(f'attach{lookup_index}c{i}',(anchor.XCoordinate,anchor.YCoordinate)))
            else:assert kind==2,('Unexpected original positioning lookup',kind)
    kerning={k:v for k,v in kerning.items() if v}
    print(master.name,'effective kerning pairs',len(kerning),flush=True)
    return kerning


def compress_kerning(font,pairs):
    """Group only glyphs whose complete kerning profiles agree in all masters."""
    left_hash=defaultdict(hashlib.sha256);right_hash=defaultdict(hashlib.sha256)
    for mi,values in enumerate(pairs):
        for (left,right),value in sorted(values.items()):
            left_hash[left].update(f'{mi}:{right}:{value};'.encode())
            right_hash[right].update(f'{mi}:{left}:{value};'.encode())
    mappings=[]
    for side,hashes,attribute in [('L',left_hash,'rightKerningGroup'),('R',right_hash,'leftKerningGroup')]:
        groups=defaultdict(list);mapping={}
        for name,h in hashes.items():groups[h.digest()].append(name)
        for i,names in enumerate(groups.values()):
            # Keep singleton profiles as classes too. Glyphs otherwise expands
            # glyph/class pairs into individual exceptions, overflowing the
            # variable Text Preview's Latin positioning subtable.
            group=f'{side}{i:04d}'
            for name in names:
                setattr(font.glyphs[name],attribute,group);mapping[name]=f'@MMK_{side}_{group}'
        mappings.append(mapping)
    for master,values in zip(font.masters,pairs):
        compressed={}
        for (left,right),value in values.items():
            key=(mappings[0].get(left,left),mappings[1].get(right,right))
            assert key not in compressed or compressed[key]==value,key
            compressed[key]=value
        for (left,right),value in compressed.items():font.setKerningForPair(master.id,left,right,value)
        print(master.name,'grouped kerning records',len(compressed),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir',type=Path,default=ROOT/'build/Lato26-Desktop/Lato26/TTF')
    ap.add_argument('--cache',type=Path,default=ROOT/'.cache/lato2-compatible')
    ap.add_argument('--output-dir',type=Path,default=ROOT/'build/Lato26-Variable')
    ap.add_argument('--source-dir',type=Path,default=ROOT/'sources')
    ap.add_argument('--style',choices=['Upr','Ita','all'],default='all')
    ap.add_argument('--reuse',action='store_true');ap.add_argument('--skip-glyphs',action='store_true')
    args=ap.parse_args()
    for style in (('Upr','Ita') if args.style=='all' else [args.style]):
        if args.reuse:fonts=[TTFont(args.cache/f'Lato26-{base.label(style,w)}.ttf') for w in WEIGHTS]
        else:fonts,_=compatible_masters(style,args.input_dir,args.cache)
        export_variable(fonts,style,args.output_dir)
        if not args.skip_glyphs:
            args.source_dir.mkdir(parents=True,exist_ok=True)
            export_glyphs(fonts,style,args.source_dir/f'Lato26-{"Italic" if style=="Ita" else "Upright"}.glyphs')

if __name__=='__main__':main()
