#!/usr/bin/env python3
"""Export active VFJs as editable Glyphs 3 files with the revised spacing curve.

Hairline/Black outlines are retained as cubic paths and components. Regular
and Bold masters are interpolated to retain the piecewise kerning curve.
A few incompatible legacy glyphs use the compatible exported TTF contours.
"""
import copy
import importlib
import json
import re
import uuid
from pathlib import Path

import numpy as np
from glyphsLib import classes as gs
from glyphsLib.types import Point
from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

from lowercase_kerning import CONFIG, correction
build = importlib.import_module('07_build_revised_lato')
refine = importlib.import_module('10_refine_ae_and_l_spacing')
ROOT = build.ROOT
DESIGNS = ((0, 'Hairline'), (540, 'Regular'), (780, 'Bold'), (1000, 'Black'))


def pts(node):
    numbers = []
    for part in node.split('{')[0].split():
        try: numbers.append(float(part))
        except ValueError: break
    return np.array(numbers).reshape(-1, 2)


def normalize_layer(layer):
    result = copy.deepcopy(layer)
    for element in result.get('elements', []):
        data = element.get('elementData')
        if isinstance(data, str):
            contours = []
            for hint in layer.get('hints', []):
                record = hint.get('node0', {}).get('nodeNode', {})
                if isinstance(record.get('contour'), dict):
                    contours.append(record['contour'])
            assert len(contours) == 1, (layer['name'], data)
            element['elementData'] = {'contours': contours}
        elif isinstance(data, dict) and 'component' in data:
            element['component'] = data['component']
            element.pop('elementData')
    return result


def topology(layer):
    return [(('component', e['component']['glyphName']) if 'component' in e else
             tuple(tuple(len(pts(n)) for n in c['nodes']) for c in e['elementData'].get('contours', [])))
            for e in layer.get('elements', [])]


def blended_layer(glyph, design):
    a, b = [normalize_layer(build.revision.master(glyph, black)) for black in (False, True)]
    assert topology(a) == topology(b)
    t = design/1000
    result = copy.deepcopy(a)
    result['advanceWidth'] = a['advanceWidth']*(1-t)+b['advanceWidth']*t
    for e, ea, eb in zip(result.get('elements', []), a.get('elements', []), b.get('elements', [])):
        tr = tuple(x*(1-t)+y*t for x, y in zip(build.transform(ea), build.transform(eb)))
        e['transform'] = dict(xScale=tr[0], yScale=tr[3], xOffset=tr[4], yOffset=tr[5])
        if 'component' not in e:
            for c, ca, cb in zip(e['elementData'].get('contours', []), ea['elementData'].get('contours', []), eb['elementData'].get('contours', [])):
                c['nodes'] = [build.revision.node_text(pts(na)*(1-t)+pts(nb)*t,
                               ' s' if ' s' in na else ' c' if ' c' in na else '') for na, nb in zip(ca['nodes'], cb['nodes'])]
    aa = {v['name']: v for v in a.get('anchors', [])}; bb = {v['name']: v for v in b.get('anchors', [])}
    result['anchors'] = [{'name': name, 'point': build.revision.node_text(
        pts(value.get('point','0 0'))*(1-t)+pts(bb.get(name, value).get('point','0 0'))*t)} for name, value in aa.items()]
    return result


def fill_layer(layer, source_layer):
    layer.width = source_layer['advanceWidth']
    for element in source_layer.get('elements', []):
        transform = build.transform(element)
        if 'component' in element:
            component = gs.GSComponent(element['component']['glyphName'], transform=transform)
            component.alignment = -1
            layer.components.append(component)
        else:
            pen = layer.getPointPen()
            for contour in element['elementData'].get('contours', []):
                nodes = contour['nodes']; start = pts(nodes[0])[0]
                pen.beginPath()
                incoming = 'curve' if len(pts(nodes[-1])) == 2 else 'line'
                pen.addPoint((start[0]*transform[0]+transform[4], start[1]*transform[3]+transform[5]),
                             segmentType=incoming, smooth=' s' in nodes[0])
                for text in nodes[1:]:
                    points = pts(text)
                    for i, p in enumerate(points):
                        endpoint = i == len(points)-1 and len(points) != 2
                        kind = ('curve' if len(points) == 3 else 'line') if endpoint else None
                        pen.addPoint((p[0]*transform[0]+transform[4], p[1]*transform[3]+transform[5]),
                                     segmentType=kind, smooth=endpoint and ' s' in text)
                pen.endPath()
    for anchor in source_layer.get('anchors', []):
        layer.anchors.append(gs.GSAnchor(anchor['name'], Point(*map(float,pts(anchor.get('point','0 0'))[0]))))


def fallback_layer(layer, name, design, source, masters):
    recordings = []
    for font in masters:
        glyph_set = font.getGlyphSet(); out = build.output_name(source, name, font)
        pen = DecomposingRecordingPen(glyph_set); glyph_set[out].draw(pen); recordings.append(pen.value)
    t = design/1000; pen = layer.getPen()
    for (op, a), (other, b) in zip(*recordings):
        assert op == other and len(a) == len(b), name
        coordinates = [tuple(x*(1-t)+y*t for x,y in zip(pa,pb)) if pa is not None else None for pa,pb in zip(a,b)]
        getattr(pen, op)(*coordinates)
    layer.width = source.width(name, design)


def export(style, output_path=None):
    data = json.loads((ROOT/f'sources/Lato3{style}2M.vfj').read_text())['font']
    source = build.Source(style); spacing = json.loads(CONFIG.read_text()); spec = spacing['styles'][style]
    font = gs.GSFont(); font.format_version = 3; font.familyName = 'Lato26'
    font.upm = data['upm']; font.versionMajor = 3; font.versionMinor = 100
    font.disablesAutomaticAlignment = True; font.disablesNiceNames = True
    font.axes = [gs.GSAxis('Weight','wght')]
    for key in ('copyright','designer','designerURL','manufacturer','manufacturerURL'):
        setattr(font,key,data['info'][key])
    for key in ('license','licenseURL','trademark','description'):
        font.customParameters[key] = data['info'][key]
    font.customParameters['vendorID'] = data['info']['vendorID']
    font.customParameters['Use Typo Metrics'] = data['info']['useTypoMetrics']
    font.customParameters["Don't use Production Names"] = True
    font.userData['Lato26.spacing'] = {'eSpacingStrength': spacing['e_spacing_strength'], 'lPairTightening': spacing['l_pair_tightening']}
    if 'bowl_allowance' in spacing:
        font.userData['Lato26.spacing']['bowlAllowance'] = spacing['bowl_allowance']['additions'][style]
    if 'outline_spacing_reference' in spacing:
        font.userData['Lato26.spacing']['outlineSpacingReference'] = spacing['outline_spacing_reference'][style]
    originals = {m['fontMaster']['name']: m['fontMaster'] for m in data['masters']}
    ma, mb = list(originals.values())
    assert ma['name'].startswith('Hairline') and mb['name'].startswith('Black')
    for design, name in DESIGNS:
        master = gs.GSFontMaster(); master.id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'Lato26/{style}/{design}')).upper()
        master.name = name+(' Italic' if style == 'Ita' else ''); master.axes = [design]
        t=design/1000
        for attr,key in [('ascender','ascender'),('descender','descender'),('xHeight','xHeight'),('capHeight','capsHeight')]:
            setattr(master,attr,ma[key]*(1-t)+mb[key]*t)
        master.italicAngle = 7 if style=='Ita' else 0
        font.masters.append(master)
    for instance_data in data['instances']:
        instance = gs.GSInstance(); instance.name = instance_data['name']; instance.axes = [instance_data['location']['wt']]
        instance.isItalic = style=='Ita'; instance.isBold = instance_data['weight']==700
        from truetype_hinting import GLYPHS_OPTIONS
        instance.customParameters['Autohint'] = True
        instance.customParameters['TTFAutohint options'] = GLYPHS_OPTIONS
        instance.customParameters['weightClass'] = instance_data['weight']
        instance.customParameters['styleMapFamilyName'] = instance_data['sgn']
        font.instances.append(instance)
    suffix = 'Italic' if style=='Ita' else ''
    master_fonts = [TTFont(ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26.~VF/master_ttf_interpolatable/Lato26-{w}{suffix}.ttf') for w in ('Hairline','Black')]
    fallback = []
    for original in data['glyphs']:
        name=original['name']; glyph=gs.GSGlyph(name)
        glyph.unicodes = ([original['unicode'].upper()] if 'unicode' in original else [f'{u:04X}' for u in original.get('unicodes',[])])
        glyph.note = original.get('note',''); font.glyphs.append(glyph)
        layers = [normalize_layer(build.revision.master(original,black)) for black in (False,True)]
        incompatible = topology(layers[0]) != topology(layers[1])
        if incompatible: fallback.append(name)
        for master,(design,_) in zip(font.masters,DESIGNS):
            layer=gs.GSLayer();layer.layerId=master.id;layer.associatedMasterId=master.id;glyph.layers.append(layer)
            if incompatible:
                fallback_layer(layer,name,design,source,master_fonts)
                t=design/1000
                anchors0={a['name']:a for a in layers[0].get('anchors',[])};anchors1={a['name']:a for a in layers[1].get('anchors',[])}
                for an,a in anchors0.items():
                    p=pts(a.get('point','0 0'))*(1-t)+pts(anchors1.get(an,a).get('point','0 0'))*t
                    layer.anchors.append(gs.GSAnchor(an,Point(*map(float,p[0]))))
            else:fill_layer(layer,blended_layer(original,design))
    # Preserve named OpenType classes only when the prefix doesn't define them.
    prefix=data['openTypeFeatures'][0]['feature']
    for cls in data['classes']:
        if not re.search(r'@'+re.escape(cls['name'])+r'\s*=',prefix):
            font.classes.append(gs.GSClass(cls['name'],' '.join(cls['names'])))
    font.featurePrefixes.append(gs.GSFeaturePrefix('FontLab layout',prefix))
    for feature in data['openTypeFeatures'][1:]:
        tag=feature['name'];code=feature['feature']
        match=re.fullmatch(r'\s*feature\s+'+tag+r'\s*\{(.*)\}\s*'+tag+r';\s*',code,re.S)
        assert match,tag
        font.features.append(gs.GSFeature(tag,match[1].strip()))
    classes=ma['kerning']['kerningClasses']
    for cls in classes:
        for name in cls['names']:
            glyph=font.glyphs[name]
            if cls.get('1st'):glyph.rightKerningGroup=cls['name']
            if cls.get('2nd'):glyph.leftKerningGroup=cls['name']
    pa,pb=ma['kerning']['pairs'],mb['kerning']['pairs']
    def left_key(key):return '@MMK_L_'+key[1:] if key.startswith('@') else key
    def right_key(key):return '@MMK_R_'+key[1:] if key.startswith('@') else key
    for master,(design,_) in zip(font.masters,DESIGNS):
        t=design/1000;pairs={}
        for left in sorted(set(pa)|set(pb)):
            row={}
            for right in sorted(set(pa.get(left,{}))|set(pb.get(left,{}))):
                row[right_key(right)] = round(float(pa.get(left,{}).get(right,0))*(1-t)+float(pb.get(left,{}).get(right,0))*t)
            pairs[left_key(left)]=row
        for left,item in spec['left'].items():
            for right in spec['right']:
                base=[]
                for i,k in enumerate((ma['kerning'],mb['kerning'])):
                    base.append(refine.effective(k['pairs'],classes,left,right)-correction(source,left,right,i*1000,spacing))
                pairs.setdefault(left,{})[right]=round(base[0]*(1-t)+base[1]*t)+correction(source,left,right,design,spacing)
        font.kerning[master.id]=pairs
    font.userData['Lato26.compatibleOutlineFallbacks'] = fallback
    font.note = 'Converted from active FontLab sources. Regular and Bold masters preserve the weight-dependent kerning curve. The separate Lato26-Regular.glyphs export retains the hand-edited Regular a/e quadratics exactly.'
    path=Path(output_path) if output_path else ROOT/f'sources/Lato26-{ "Italic" if style=="Ita" else "Upright"}.glyphs';font.save(path)
    read=gs.GSFont(path)
    assert len(read.glyphs)==len(font.glyphs)==len(data['glyphs']) and len(read.masters)==4 and len(read.instances)==9
    for before,after in zip(font.glyphs,read.glyphs):
        assert before.name==after.name and before.unicodes==after.unicodes
        for la,lb in zip(before.layers,after.layers):
            assert abs(la.width-lb.width)<.001
            assert len(la.paths)==len(lb.paths) and len(la.components)==len(lb.components)
            for a,b in zip(la.paths,lb.paths):
                assert len(a.nodes)==len(b.nodes)
                for x,y in zip(a.nodes,b.nodes):
                    assert x.type==y.type and np.max(np.abs(np.array(x.position)-np.array(y.position)))<.0011,(before.name,x.position,y.position)
            for a,b in zip(la.components,lb.components):assert a.name==b.name and np.allclose(tuple(a.transform),tuple(b.transform),atol=.001)
            assert len(la.anchors)==len(lb.anchors)
            for a,b in zip(la.anchors,lb.anchors):assert a.name==b.name and np.allclose(tuple(a.position),tuple(b.position),atol=.001)
    assert font.kerning==read.kerning
    feature_code='\n'.join('@'+c.name+' = ['+c.code+'];' for c in font.classes)+'\n'+prefix+'\n'+'\n'.join(f['feature'] for f in data['openTypeFeatures'][1:])
    test=TTFont();test.setGlyphOrder([g.name for g in font.glyphs]);addOpenTypeFeaturesFromString(test,feature_code)
    print(path,f'{len(read.glyphs)} glyphs, 4 masters, 9 instances; round-trip and features verified; compatible fallbacks',fallback,flush=True)


if __name__=='__main__':
    for style in ('Upr','Ita'):export(style)
