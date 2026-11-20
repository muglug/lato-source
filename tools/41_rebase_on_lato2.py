#!/usr/bin/env python3
"""Build Lato26 on the published Lato 2.015 binary sources.

The release TTFs are immutable inputs. Only the recorded lowercase edits and
pair spacing are applied. Unchanged glyph geometry, instructions and original
OpenType lookups are verified against those inputs on every build.
"""
import argparse
import array
import copy
import hashlib
import importlib
import json
import difflib
import tempfile
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildLookup, buildPairPosGlyphs, buildValue
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program

from lowercase_kerning import pair_advance
from modified_font_names import rename_font
from truetype_hinting import hint_font, bytecode

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'sources/vendor/Lato-2.015'
PATCHES=ROOT/'sources/data/lato2-rebase.json'
WEIGHTS=dict(Hairline=0,Thin=100,Light=250,Regular=540,Medium=600,Semibold=666,Bold=780,Heavy=880,Black=1000)

def label(style,weight):
    return ('Italic' if weight=='Regular' else weight+'Italic') if style=='Ita' else weight

def bounds(font,name):
    gs=font.getGlyphSet();p=BoundsPen(gs);gs[name].draw(p);return p.bounds

def capture(snapshot,name_map,original3):
    """One-time import of the reviewed edits; subsequent builds need no snapshot."""
    LEGACY=importlib.import_module('07_build_revised_lato')
    maps=json.loads(Path(name_map).read_text())
    config=json.loads((ROOT/'sources/data/lowercase-spacing.json').read_text())
    smaller=json.loads((ROOT/'sources/data/smaller-l.json').read_text())
    from connected_ligatures import TEXTS
    result={'base_version':'2.015','modified_version':'2.026',
            'edit_snapshot':'Lato26 at fe9eda744',
            'policy':'Keep release geometry and hint programs outside the edited glyphs. Preserve 2.015 composite accents. Carry the reviewed l-pair outline-edge gaps over to the release base.',
            'styles':{}}
    for style in ('Upr','Ita'):
        source=LEGACY.Source(style);mapping=maps[style]
        changed=[n for n in source.affected if n in mapping and n not in TEXTS]
        lefts=[n for n in config['styles'][style]['left'] if n in mapping]
        rights={n for v in config['styles'][style]['right'].values() for n in v if n in mapping}
        rights.update('abcdefghijklmnopqrstuvwxyz')
        punc=config['punctuation_allowance'];punc_lefts=set(punc['lefts'][style])
        weights={}
        for weight,design in WEIGHTS.items():
            suffix=label(style,weight);rel=Path(f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{suffix}.ttf')
            current=TTFont(snapshot/rel)
            old3=TTFont(original3/f'Lato3{style}2M/ds-ufo/masters/Lato-{suffix}.ttf')
            base=TTFont(REFERENCE/f'Lato-{suffix}.ttf')
            def current_name(n):return LEGACY.output_name(source,n,current)
            outlines={}
            for name in changed:
                n=current_name(name);g=current['glyf'][n]
                assert g.numberOfContours>0,(style,weight,name)
                delta=0
                if name in smaller['styles'][style]['glyphs']:
                    delta=current['hmtx'][n][0]-old3['hmtx'][LEGACY.output_name(source,name,old3)][0]
                outlines[mapping[name]]={'role':name,'points':list(g.coordinates),
                    'flags':list(g.flags),'ends':list(g.endPtsOfContours),'advance_delta':delta,
                    'left_side_bearing':current['hmtx'][n][1]}
            allnames=set(lefts)|rights|set(punc['rights'])
            resolved={n:current_name(n) for n in allnames}
            edge={n:bounds(current,resolved[n]) for n in allnames}
            gaps={}
            for left in lefts:
                row={}
                for right in sorted(rights|set(punc['rights']) if left in punc_lefts else rights):
                    a,z=resolved[left],resolved[right]
                    base_left=mapping[left]
                    base_right=mapping.get(right)
                    if base_right is None:base_right=LEGACY.output_name(source,right,base)
                    row[base_right]=current['hmtx'][a][0]+pair_advance(current,a,z)+edge[right][0]-edge[left][2]
                gaps[base_left]=row
            weights[weight]={'design':design,'outlines':outlines,'pair_gaps':gaps}
        result['styles'][style]={'source_names':mapping,'weights':weights}
    result['bold_simple_a_forms']=['a','aogonek','uni0430','uni2C65','uni1D8F']
    PATCHES.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print('Captured reviewed edits:',PATCHES,flush=True)

def glyph_record(g):
    return (g.numberOfContours, tuple(g.coordinates) if g.numberOfContours>0 else None,
            tuple(g.flags) if g.numberOfContours>0 else None,
            tuple(g.endPtsOfContours) if g.numberOfContours>0 else None,
            tuple(c.getComponentInfo() for c in g.components) if g.isComposite() else None)

def prepare(style,weight):
    data=json.loads(PATCHES.read_text())['styles'][style]['weights'][weight]
    path=REFERENCE/f'Lato-{label(style,weight)}.ttf'
    font=TTFont(path,recalcTimestamp=False);original=copy.deepcopy(font)
    changed=set(data['outlines'])
    # Keep actual release composites, including the original accent positions.
    # Their base components are replaced below, so they inherit the edited body.
    inherited=set()
    for name,p in data['outlines'].items():
        g=font['glyf'][name]
        if g.isComposite() and any(c.glyphName in changed for c in g.components):
            inherited.add(name)
        else:
            new=Glyph();new.numberOfContours=len(p['ends'])
            new.coordinates=GlyphCoordinates(p['points']);new.flags=array.array('B',p['flags'])
            new.endPtsOfContours=p['ends'];new.program=Program();new.program.fromBytecode(b'')
            font['glyf'][name]=new
            new.recalcBounds(font['glyf'])
            font['hmtx'][name]=(font['hmtx'][name][0],new.xMin)
        advance,lsb=font['hmtx'][name]
        font['hmtx'][name]=(advance+p['advance_delta'],lsb)
    # Also rehint descendants whose assembled outline changes through a base.
    while True:
        extra={n for n in font.getGlyphOrder() if font['glyf'][n].isComposite()
               and any(c.glyphName in changed for c in font['glyf'][n].components)}-changed
        if not extra:break
        changed.update(extra);inherited.update(extra)
    for name in inherited:
        g=font['glyf'][name];g.recalcBounds(font['glyf'])
        font['hmtx'][name]=(font['hmtx'][name][0],g.xMin)
    rename_font(font)
    font['head'].fontRevision=2.026
    for record in font['name'].names:
        if record.nameID==5:record.string='Version 2.026; Lato26 based on Lato 2.015'.encode(record.getEncoding())
    names=set(data['pair_gaps'])|{r for row in data['pair_gaps'].values() for r in row}
    edge={n:bounds(font,n) for n in names};pairs={};errors=[]
    for left,row in data['pair_gaps'].items():
        for right,gap in row.items():
            target=otRound(gap-font['hmtx'][left][0]-edge[right][0]+edge[left][2])
            delta=target-pair_advance(font,left,right)
            pairs[left,right]=(buildValue({'XAdvance':delta}),None)
            errors.append(abs(font['hmtx'][left][0]+target+edge[right][0]-edge[left][2]-gap))
    lookup=buildLookup(buildPairPosGlyphs(pairs,font.getReverseGlyphMap()),flags=8)
    table=font['GPOS'].table;idx=len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(lookup);table.LookupList.LookupCount=idx+1
    for rec in table.FeatureList.FeatureRecord:
        if rec.FeatureTag=='kern':
            rec.Feature.LookupListIndex.append(idx);rec.Feature.LookupCount+=1
    return font,original,changed,{'preserved_composites':len(inherited),
        'changed_glyphs':sorted(changed),'pair_count':len(pairs),'maximum_pair_gap_error':max(errors)}

def finish_hints(font,original,changed):
    donor=copy.deepcopy(font);hint_font(donor,[n for n in changed if donor['glyf'][n].numberOfContours>0])
    # Keep the release runtime so untouched programs retain their exact behavior.
    # Control files add only zone-pointer/delta-base resets in engine 1.3. The
    # edited programs must also execute identically against the release runtime.
    different=[]
    for tag in ('fpgm','prep','cvt ','gasp'):
        if original.getTableData(tag)==donor.getTableData(tag):continue
        if tag=='cvt ':
            # Edited e raises these measured x-height overshoot zones by 1-2
            # units in Heavy/Black Italic. Retain the release zones so edited
            # and untouched letters align to the same original measurements.
            actual={i:(a,b) for i,(a,b) in enumerate(zip(original[tag].values,donor[tag].values)) if a!=b}
            expected={'Lato26-HeavyItalic':{34:(1046,1047),110:(1046,1047)},
                      'Lato26-BlackItalic':{34:(1052,1053),110:(1051,1053)}}
            assert len(original[tag].values)==len(donor[tag].values)==115
            assert actual==expected.get(font['name'].getDebugName(6)),actual
            continue
        assert tag in ('fpgm','prep'), ('Changed shared hint data',tag)
        a=original[tag].program.getAssembly();b=donor[tag].program.getAssembly()
        expected=['PUSHB[ ]\t/* 1 value pushed */','1','SZPS[ ]\t/* SetZonePointerS */'] if tag=='fpgm' else ['PUSHB[ ]\t/* 1 value pushed */','6','SDB[ ]\t/* SetDeltaBaseInGState */']
        edits=[(op,i,j,k,l) for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if op!='equal']
        assert len(edits)==(3 if tag=='fpgm' else 1),(tag,edits)
        assert all(op=='insert' and b[k:l]==expected for op,i,j,k,l in edits),tag
        different.append(tag)
    for name in changed:
        font['glyf'][name].program=Program()
        font['glyf'][name].program.fromBytecode(bytecode(donor['glyf'][name]))
    font['maxp']=copy.deepcopy(donor['maxp'])
    for field in ('maxZones','maxTwilightPoints','maxStorage','maxFunctionDefs','maxInstructionDefs','maxStackElements','maxSizeOfInstructions'):
        setattr(font['maxp'],field,max(getattr(font['maxp'],field),getattr(original['maxp'],field)))
    if 'TTFA' in donor:font['TTFA']=copy.deepcopy(donor['TTFA'])
    for tag in ('hdmx','VDMX','LTSH'):
        if tag in font:del font[tag]
    if different: verify_shared_runtime(font,donor,changed)
    for name in font.getGlyphOrder():
        if name in changed:continue
        assert glyph_record(font['glyf'][name])==glyph_record(original['glyf'][name]),name
        assert bytecode(font['glyf'][name])==bytecode(original['glyf'][name]),name
        assert font['hmtx'][name]==original['hmtx'][name],name
    for tag in ('GSUB','GDEF','cmap','OS/2','hhea'):
        assert (font.getTableData(tag) if tag in font else None)==(original.getTableData(tag) if tag in original else None),tag

def verify_shared_runtime(font,donor,changed):
    """Check the patched programs with old/new runtimes at quarter-pixel sizes."""
    import lcd_font_proofs as ft
    with tempfile.TemporaryDirectory(prefix='lato2-runtime-') as directory:
        paths=[Path(directory)/n for n in ('release.ttf','donor.ttf')]
        for f,p in zip((font,donor),paths):f.save(p)
        faces=[ft.RasterFace(p) for p in paths]
        for size in [n/4 for n in range(32,201)]+[64,72,96,120,200]:
            for face in faces:assert ft.set_size(face.handle,0,round(size*64),72,72)==0
            for target in (0,2,3):
                for name in sorted(changed):
                    values=[]
                    for face in faces:
                        assert ft.load(face.handle,font.getGlyphID(name),(target<<16)|(1<<15)|(1<<7)|(1<<3))==0
                        outline=face.handle.contents.glyph.contents.outline
                        values.append(ft.C.string_at(outline.points,ft.C.sizeof(ft.Vector)*outline.n_points))
                    assert values[0]==values[1],('Shared hint runtime mismatch',name,size,target)
        print('Release hint runtime verified at 174 sizes in three rendering modes',flush=True)


def export_otf(font,path):
    result=copy.deepcopy(font);gs=font.getGlyphSet();strings={}
    for name in font.getGlyphOrder():
        pen=T2CharStringPen(font['hmtx'][name][0],gs)
        gs[name].draw(Qu2CuPen(ReverseContourPen(pen),max_err=.01,all_cubic=True))
        strings[name]=pen.getCharString()
    for tag in ('glyf','loca','fpgm','prep','cvt ','gasp','TTFA','hdmx','VDMX','LTSH'):
        if tag in result:del result[tag]
    result.sfntVersion='OTTO'
    builder=FontBuilder(font=result,isTTF=False)
    builder.setupCFF(result['name'].getDebugName(6),
        {'FullName':result['name'].getDebugName(4),'FamilyName':result['name'].getDebugName(1),
         'Weight':result['name'].getDebugName(2),'version':'2.026',
         'Notice':result['name'].getDebugName(0)},strings,{})
    builder.setupMaxp();result.save(path)

def build_one(style,weight,output_dir=None):
    font,original,changed,report=prepare(style,weight)
    finish_hints(font,original,changed)
    folder=Path(output_dir) if output_dir else ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'Lato26-{label(style,weight)}.ttf';font.save(path)
    export_otf(font,path.with_suffix('.otf'))
    report.update(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  unchanged_glyphs_verified=len(font.getGlyphOrder())-len(changed))
    print(path.name,'2.015 outlines/hints preserved outside',len(changed),'edited glyphs',flush=True)
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture',type=Path);ap.add_argument('--name-map',type=Path)
    ap.add_argument('--original3',type=Path)
    ap.add_argument('--style',choices=['Upr','Ita','all'],default='all')
    ap.add_argument('--weight',choices=list(WEIGHTS));ap.add_argument('--output-dir',type=Path)
    args=ap.parse_args()
    if args.capture:
        capture(args.capture,args.name_map,args.original3);return
    reports=[build_one(s,w,args.output_dir) for s in (('Upr','Ita') if args.style=='all' else (args.style,))
             for w in ([args.weight] if args.weight else WEIGHTS)]
    (ROOT/'build/proofs/lato2-rebase-validation.json').write_text(json.dumps({'status':'passed','fonts':reports},indent=2)+'\n')

if __name__=='__main__':main()
