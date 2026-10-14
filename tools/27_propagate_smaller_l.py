#!/usr/bin/env python3
"""Propagate the author's Regular l edit, retaining established special-pair gaps.

One-time source migration, followed by repeatable --build and --glyphs modes.
The Regular control points are authoritative. Across weight, shared motion
of corresponding inner/outer points stays constant; differential motion
scales with stem thickness so Hairline keeps its thin stroke. Italic uses
its existing t-derived bowl transform and l-derived stem shear.
"""
import argparse
import copy
import importlib
import json
import re
from pathlib import Path

import numpy as np
import openstep_plist
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from lowercase_kerning import CONFIG, correction, source_edges

build = importlib.import_module('07_build_revised_lato')
revision = build.revision
export = importlib.import_module('11_export_editable_glyphs')
refine = importlib.import_module('10_refine_ae_and_l_spacing')
ROOT = build.ROOT
RECORD = ROOT/'sources/data/smaller-l.json'
DESIGNS = tuple(build.WEIGHTS.values())
DIRECT = ('l','l.ss05','l.sups','lmod','lbelt','f_l','f_f_l')


def flat(contour):
    return np.vstack([revision.points(n) for n in contour['nodes']])


def replace_flat(contour, points):
    cursor = 0
    for i, node in enumerate(contour['nodes']):
        count = len(revision.points(node))
        suffix = ' c' if count == 2 else ' s' if ' s' in node else ''
        contour['nodes'][i] = revision.node_text(points[cursor:cursor+count],suffix)
        cursor += count
    assert cursor == len(points)


def compiled_spacing_references(config, record, sources, snapshot):
    for filename,metadata in config['fonts'].items():
        style='Ita' if 'Ita2M' in filename else 'Upr'
        font=TTFont(snapshot/'before-build'/Path(filename).relative_to('build'))
        gs=font.getGlyphSet();metrics={}
        for name in record['styles'][style]['glyphs']:
            out=build.output_name(sources[style],name,font)
            pen=BoundsPen(gs);gs[out].draw(pen)
            metrics[out]=[font['hmtx'][out][0],pen.bounds[0],pen.bounds[2]]
        metadata['outline_reference_metrics']=metrics


def italic_matrices(upr, ita, black):
    # Derivative of the original t-bowl transform (06_update_lato_outlines).
    t = revision.contours(revision.master(upr.glyphs['t'],black))[0]
    ti = revision.contours(revision.master(ita.glyphs['t'],black))[0]
    a=[revision.points(t['nodes'][2])[-1]];b=[revision.points(ti['nodes'][3])[-1]]
    for i,j in ((3,4),(4,5),(5,6),(6,7)):
        a.extend(revision.points(t['nodes'][i]));b.extend(revision.points(ti['nodes'][j]))
    a,b=np.array(a),np.array(b)
    fit=np.linalg.lstsq(np.column_stack((a,np.ones(len(a)))),b[:,0],rcond=None)[0]
    u=flat(revision.contours(revision.master(upr.glyphs['l'],black))[0])
    it=flat(revision.contours(revision.master(ita.glyphs['l'],black))[0])
    # Flattened path begins at the inner ascender, outer ascender, outer join.
    shear=(it[1,0]-it[2,0])/(it[1,1]-it[2,1])
    scale=(it[0,0]-it[1,0])/(u[0,0]-u[1,0])
    return np.array([[scale,shear],[0,1.]]), np.array([[fit[0],fit[1]],[0,1.]])


def migrate(snapshot):
    if RECORD.exists():raise SystemExit('Already migrated; use --build / --glyphs.')
    authored_path=ROOT/'sources/Lato26-Upright.glyphs'
    authored=openstep_plist.loads(authored_path.read_text(),use_numbers=True)
    glyph=next(g for g in authored['glyphs'] if g['glyphname']=='l')
    master=next(m for m in authored['fontMaster'] if float(m['axesValues'][0])==540)
    layer=next(l for l in glyph['layers'] if l['layerId']==master['id'])
    target=np.array([n[:2] for n in layer['shapes'][0]['nodes']],float)
    sources={s:build.Source(s) for s in ('Upr','Ita')}
    old=copy.deepcopy(json.loads(CONFIG.read_text()));config=copy.deepcopy(old)
    regular=export.blended_layer(sources['Upr'].glyphs['l'],540)
    original_flat=flat(revision.contours(regular)[0])
    original=original_flat[[*range(1,16),0]]
    assert len(target)==16
    delta=target-original
    width_delta=layer['width']-regular['advanceWidth']
    reference_stem=original[15,0]-original[0,0]
    config['outline_spacing_reference']={}
    record={'authored_glyph':'l','authored_design':540,'advance_delta':width_delta,
            'authored_nodes':layer['shapes'][0]['nodes'],'node_deltas':delta.tolist(),
            'method':__doc__,'styles':{}}
    revised={s:copy.deepcopy(source.glyphs) for s,source in sources.items()}
    for style,source in sources.items():
        changed=set(DIRECT);widths={}
        for black in (False,True):
            base=flat(revision.contours(revision.master(source.glyphs['l'],black))[0])
            upright=flat(revision.contours(revision.master(sources['Upr'].glyphs['l'],black))[0])
            ratio=(upright[0,0]-upright[1,0])/reference_stem
            ds=delta.copy()
            for i in range(8):
                j=15-i;center=(delta[i]+delta[j])/2;difference=(delta[i]-delta[j])/2*ratio
                ds[i]=center+difference;ds[j]=center-difference
            ds=ds[[15,*range(15)]]
            wd=width_delta
            if style=='Ita':
                stem,bowl=italic_matrices(sources['Upr'],source,black)
                ds=np.array([d@(stem if i in (0,1,2,3,14,15) else bowl).T for i,d in enumerate(ds)])
                wd*=bowl[0,0]
            for name in DIRECT:
                old_layer=revision.master(source.glyphs[name],black)
                new_layer=revision.master(revised[style][name],black)
                candidates=[]
                for index,c in enumerate(revision.contours(old_layer)):
                    p=flat(c)
                    if p.shape!=base.shape:continue
                    transform=np.linalg.lstsq(np.column_stack((base,np.ones(len(base)))),p,rcond=None)[0]
                    error=np.max(np.abs(np.column_stack((base,np.ones(len(base))))@transform-p))
                    if error<.002:candidates.append((index,p,transform))
                assert len(candidates)==1,(style,name,black,candidates)
                index,p,matrix=candidates[0]
                replace_flat(revision.contours(new_layer)[index],p+ds@matrix[:2])
                new_layer['advanceWidth']+=wd*matrix[0,0]
                revision.clear_hints(new_layer)
                widths.setdefault(name,{})[old_layer['name']]=new_layer['advanceWidth']-old_layer['advanceWidth']
        # Component forms retain their accent placement. Following letters in
        # precomposed lj move with the new first-letter advance.
        pending=True
        while pending:
            pending=False
            for name,g in revised[style].items():
                if name in changed:continue
                refs={e['component']['glyphName'] for l in g['layers'] for e in l.get('elements',[]) if 'component' in e}
                if not refs.intersection(changed):continue
                assert refs.intersection(changed)<=widths.keys(),(name,refs)
                changed.add(name);pending=True
                for black in (False,True):
                    l=revision.master(g,black);total=0
                    for e in l.get('elements',[]):
                        child=e.get('component',{}).get('glyphName')
                        if child in widths:total+=widths[child][l['name']]*build.transform(e)[0]
                    l['advanceWidth']+=total;widths.setdefault(name,{})[l['name']]=total
                    if name in ('lj','lj.ss05'):
                        for e in l['elements']:
                            if e.get('component',{}).get('glyphName')=='j':
                                e.setdefault('transform',{})['xOffset']+=total
                    revision.clear_hints(l)
        assert changed<=set(source.affected),sorted(changed-set(source.affected))
        record['styles'][style]={'glyphs':sorted(changed),'width_deltas':widths}
        names=set(config['styles'][style]['left']) | (set(config['l_rights']) & changed)
        config['outline_spacing_reference'][style]={
            'widths':{n:[revision.master(source.glyphs[n],b)['advanceWidth'] for b in (False,True)] for n in sorted(names)},
            'edges':{n:[[d,*source_edges(source,n,d)] for d in DESIGNS] for n in sorted(names)}}
    # Persist only the intended glyph blocks, retaining other VFJ fields.
    for style,source in sources.items():
        revision.save_changed_glyphs(ROOT/f'sources/Lato3{style}2M.vfj',source.glyphs,revised[style],record['styles'][style]['glyphs'])
    new_sources={s:build.Source(s) for s in sources}
    for style in sources:
        path=ROOT/f'sources/Lato3{style}2M.vfj';text=path.read_text();data=json.loads(text)['font']
        for wrapped in data['masters']:
            m=wrapped['fontMaster'];design=1000 if m['name'].startswith('Black') else 0
            before=copy.deepcopy(m['kerning']);after=copy.deepcopy(before)
            for left in config['styles'][style]['left']:
                for right in config['styles'][style]['right']:
                    difference=correction(new_sources[style],left,right,design,config)-correction(sources[style],left,right,design,old)
                    if difference:
                        value=refine.effective(before['pairs'],before['kerningClasses'],left,right)
                        after['pairs'].setdefault(left,{})[right]=str(value+difference)
            text=refine.patch_json_block(text,before,after,10)
        path.write_text(text)
    compiled_spacing_references(config,record,sources,snapshot)
    CONFIG.write_text(json.dumps(config,indent=2)+'\n')
    manifest=json.loads(build.MANIFEST.read_text())
    for style,entry in record['styles'].items():
        for name,masters in entry['width_deltas'].items():
            for label,amount in masters.items():
                changes=manifest['styles'][style]['width_changes'].setdefault(name,{})
                changes[label]=round(changes.get(label,0)+amount,4)
    build.MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n')
    RECORD.write_text(json.dumps(record,indent=2)+'\n')
    print('Migrated smaller l:',{s:len(r['glyphs']) for s,r in record['styles'].items()},flush=True)


def rebuild():
    record=json.loads(RECORD.read_text())
    for style in ('Upr','Ita'):
        source=build.Source(style);source.affected=record['styles'][style]['glyphs']
        directory=ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
        build.build_masters(source,directory)
        for weight,design in build.WEIGHTS.items():
            for extension in ('ttf','otf'):
                build.build_static(source,directory,weight,design,extension)
        if style=='Upr':build.update_glyphs(source,directory)


def balanced_end(text,start):
    """Find an OpenStep container end without interpreting quoted contents."""
    depth=0;quoted=False;escaped=False
    for i in range(start,len(text)):
        char=text[i]
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '({':depth+=1
        elif char in ')}':
            depth-=1
            if not depth:return i+1
    raise ValueError('Unclosed OpenStep container')


def merge_glyphs_text(text,updated,changed):
    """Retain original formatting and editor data outside the edited blocks."""
    original=openstep_plist.loads(text,use_numbers=True)
    replacements=[]
    start=re.search(r'^glyphs = \(',text,re.M).end()
    by_name={g['glyphname']:g for g in updated['glyphs']}
    for glyph in original['glyphs']:
        start=text.index('{',start);end=balanced_end(text,start)
        if glyph['glyphname'] in changed:
            replacements.append((start,end,openstep_plist.dumps(by_name[glyph['glyphname']],indent=0,sort_keys=False)))
        start=end
    for key in ('kerningLTR','userData'):
        start=re.search(r'^'+key+r' = \{',text,re.M).end()-1
        replacements.append((start,balanced_end(text,start),openstep_plist.dumps(updated[key],indent=0,sort_keys=False)))
    for start,end,replacement in sorted(replacements,reverse=True):
        text=text[:start]+replacement+text[end:]
    assert openstep_plist.loads(text,use_numbers=True)==updated
    return text


def glyphs(snapshot):
    record=json.loads(RECORD.read_text())
    for style,label in (('Upr','Upright'),('Ita','Italic')):
        path=ROOT/f'sources/Lato26-{label}.glyphs'
        text=path.read_text();before=openstep_plist.loads(text,use_numbers=True)
        generated=snapshot/f'generated-{label}.glyphs';export.export(style,generated)
        after=openstep_plist.loads(generated.read_text(),use_numbers=True)
        updated={g['glyphname']:g for g in after['glyphs']}
        changed=set(record['styles'][style]['glyphs'])
        for glyph in before['glyphs']:
            if glyph['glyphname'] not in changed:continue
            for layer,new in zip(glyph['layers'],updated[glyph['glyphname']]['layers']):
                if style=='Upr' and glyph['glyphname']=='l' and layer['layerId']=='7E34DB9F-A80D-501A-A57E-0A6D858088AF':
                    # Retain the user's exact saved Regular control points.
                    assert abs(new['width']-layer['width'])<.001
                    continue
                layer['shapes']=new['shapes'];layer['width']=new['width']
        before['kerningLTR']=after['kerningLTR']
        before.setdefault('userData',{})['Lato26.spacing']=after['userData']['Lato26.spacing']
        path.write_text(merge_glyphs_text(text,before,changed))
        print(path,'updated; unrelated glyph data preserved',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--build',action='store_true');parser.add_argument('--glyphs',action='store_true')
    args=parser.parse_args()
    if args.build:rebuild()
    elif args.glyphs:glyphs(args.snapshot)
    else:migrate(args.snapshot)


if __name__=='__main__':main()
