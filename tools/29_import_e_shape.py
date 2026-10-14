#!/usr/bin/env python3
"""Import the four authored upright e masters and propagate related forms.

The endpoint masters stay in VFJ; Regular/Bold layers are recorded separately
so builds preserve the authored, non-linear weight progression. Italics and
all advances are unchanged. Related small/turned/ligature forms receive the
same deltas scaled to their existing proportions, with ae joins realigned.
"""
import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import openstep_plist

build=importlib.import_module('07_build_revised_lato')
export=importlib.import_module('11_export_editable_glyphs')
narrow=importlib.import_module('27_propagate_smaller_l')
refine=importlib.import_module('10_refine_ae_and_l_spacing')
rev=build.revision
ROOT=build.ROOT
RECORD=build.E_SHAPE
DIRECT=('e','ie-cy','e.sups','emod','einferior','ecomb','ecomb.case',
        'eSign-myanmar','eSign-myanmar.case','schwa','schwa-cy','schwamod',
        'eturned','ereversed','ae','oe','aeTurned','aeTurnedmod','oeTurned')


def migrate(authored):
    if RECORD.exists():raise SystemExit('Already imported; use --build or --glyphs.')
    authored=authored.resolve()
    old=openstep_plist.loads((ROOT/'sources/Lato26-Upright.glyphs').read_text(),use_numbers=True)
    new=openstep_plist.loads(authored.read_text(),use_numbers=True)
    old_e=next(g for g in old['glyphs'] if g['glyphname']=='e')
    new_e=next(g for g in new['glyphs'] if g['glyphname']=='e')
    master_ids={int(m['axesValues'][0]):m['id'] for m in new['fontMaster']}
    source=build.Source('Upr');revised=copy.deepcopy(source.glyphs)
    record={'reference':str(authored.relative_to(ROOT)),
            'reference_sha256':hashlib.sha256(authored.read_bytes()).hexdigest(),
            'style':'Upr','method':__doc__,'direct_glyphs':list(DIRECT),
            'authored_layers':{},'intermediate_layers':{}}
    for design,mid in master_ids.items():
        before=next(l for l in old_e['layers'] if l['layerId']==mid)
        after=next(l for l in new_e['layers'] if l['layerId']==mid)
        assert before['width']==after['width']
        a,z=[np.array([n[:2] for n in l['shapes'][0]['nodes']],float) for l in (before,after)]
        assert a.shape==z.shape==(64,2)
        assert [n[2:] for n in before['shapes'][0]['nodes']]==[n[2:] for n in after['shapes'][0]['nodes']]
        record['authored_layers'][str(design)]=copy.deepcopy(after)
        # Glyphs rotates the VFJ start point to the end of its node array.
        ds=(z-a)[[63,*range(63)]]
        base=rev.contours(export.blended_layer(source.glyphs['e'],design))[0]
        base_points=narrow.flat(base)
        assert np.max(abs(base_points[[*range(1,64),0]]-a))<.001
        updated={}
        for name in DIRECT:
            layer=export.blended_layer(source.glyphs[name],design)
            if name=='ereversed':
                rev.contours(layer)[0]['nodes']=rev.transformed_contour(
                    rev.contours(updated['e'])[0],np.diag([-1.,1.]),
                    (updated['e']['advanceWidth'],0),reverse=True)['nodes']
            else:
                contour=next(c for c in rev.contours(layer) if len(c['nodes'])==25)
                points=narrow.flat(contour)
                if name in ('e','ie-cy'):
                    result=z[[63,*range(63)]]
                else:
                    sy=(rev.points(contour['nodes'][0])[-1,1]-rev.points(contour['nodes'][2])[-1,1])/(rev.points(base['nodes'][0])[-1,1]-rev.points(base['nodes'][2])[-1,1])
                    sx=np.ptp(points[:,0])/np.ptp(base_points[:,0])*np.sign(sy)
                    result=points+ds@np.diag([sx,sy])
                narrow.replace_flat(contour,result)
                if name in ('ae','aeTurned','aeTurnedmod'):refine.align_ae(layer,False)
            rev.clear_hints(layer);updated[name]=layer
            if design in (0,1000):
                target=rev.master(revised[name],design==1000)
                # Keep source components, transforms, anchors and metadata as saved.
                for a,b in zip(rev.contours(target),rev.contours(layer)):a['nodes']=b['nodes']
                rev.clear_hints(target)
            else:record['intermediate_layers'].setdefault(name,{})[str(design)]=layer
    changed=set(DIRECT)
    while True:
        dependents={name for name,g in source.glyphs.items() if any(
            e.get('component',{}).get('glyphName') in changed
            for l in g['layers'] for e in l.get('elements',[]))}-changed
        if not dependents:break
        changed.update(dependents)
    assert changed<=set(source.affected),sorted(changed-set(source.affected))
    record['glyphs']=sorted(changed)
    rev.save_changed_glyphs(ROOT/'sources/Lato3Upr2M.vfj',source.glyphs,revised,DIRECT)
    RECORD.write_text(json.dumps(record,indent=2)+'\n')
    print('Imported e: four masters;',len(changed),'upright glyphs; italics unchanged',flush=True)


def rebuild():
    source=build.Source('Upr');source.affected=json.loads(RECORD.read_text())['glyphs']
    directory=ROOT/'build/Lato3Upr2M/ds-ufo/masters'
    build.build_masters(source,directory)
    for weight,design in build.WEIGHTS.items():
        for extension in ('ttf','otf'):build.build_static(source,directory,weight,design,extension)
    build.update_glyphs(source,directory)
    update_static_e()


def update_static_e():
    # Keep the standalone editable Regular e in its authored cubic form.
    text=build.REGULAR.read_text();data=openstep_plist.loads(text,use_numbers=True)
    g=next(g for g in data['glyphs'] if g['glyphname']=='e')
    target=json.loads(RECORD.read_text())['authored_layers']['540']
    g['layers'][0]['shapes']=target['shapes']
    build.REGULAR.write_text(narrow.merge_glyphs_text(text,data,{'e'}))


def glyphs(snapshot):
    record=json.loads(RECORD.read_text());path=ROOT/'sources/Lato26-Upright.glyphs'
    text=path.read_text();before=openstep_plist.loads(text,use_numbers=True)
    generated=snapshot/'generated-Upright.glyphs';export.export('Upr',generated)
    after=openstep_plist.loads(generated.read_text(),use_numbers=True)
    by_name={g['glyphname']:g for g in after['glyphs']}
    ids={l['layerId']:l for l in record['authored_layers'].values()}
    for glyph in before['glyphs']:
        if glyph['glyphname'] not in record['glyphs']:continue
        for layer,new in zip(glyph['layers'],by_name[glyph['glyphname']]['layers']):
            layer['shapes']=copy.deepcopy(ids[layer['layerId']]['shapes'] if glyph['glyphname']=='e' else new['shapes'])
    # This shape edit keeps the spacing policy, advances and kerning intact.
    path.write_text(narrow.merge_glyphs_text(text,before,set(record['glyphs'])))
    print('Editable upright sources updated; unrelated glyph data preserved',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authored',type=Path,default=ROOT/'sources/Lato26-Upright-modified-e.glyphs')
    parser.add_argument('--snapshot',type=Path,default=Path('/tmp/lato-e-shape'))
    parser.add_argument('--build',action='store_true');parser.add_argument('--glyphs',action='store_true')
    args=parser.parse_args()
    if args.build:rebuild()
    elif args.glyphs:glyphs(args.snapshot)
    else:migrate(args.authored)


if __name__=='__main__':main()
