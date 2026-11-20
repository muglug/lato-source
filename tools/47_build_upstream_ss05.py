#!/usr/bin/env python3
"""Build upstream Lato 3 with Lato26 lowercase forms and spacing in ss05.

Pinned Git objects are the reproducible inputs. Default glyphs, features and
kerning come from upstream; only alternate glyphs and pairs involving them are
customized. No Lato 2.015 rebase or connected-ligature replacement is applied.
"""
import argparse
import copy
import importlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from glyphsLib import GSFont, to_designspace
from glyphsLib import classes as gs
from fontmake.font_project import FontProject

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = '83bd714f5'  # latofonts/lato-source master, fetched November 2026
DONOR = 'fe9eda744'  # last reviewed Lato26 3.100 shapes and spacing
CARLITO = '70ca4aaee'  # original Carlito Light, before lowercase revisions
CACHE = ROOT / '.cache/ss05'
SS05_LO_SPACING = 25  # A 0.0125 em increase, at every weight.
SS05_CAPITAL_SPACING = {'J': 60, 'I.ss05': 40}
HINT_OPTIONS = ('--no-info', '--ttfa-table', '--stem-width-mode=qsq', '--fallback-script=latn')
GLYPHS_HINT_OPTIONS = ' '.join(option for option in HINT_OPTIONS if option != '--ttfa-table')
export = importlib.import_module('11_export_editable_glyphs')
build = importlib.import_module('07_build_revised_lato')


def git_bytes(revision, path):
    return subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=ROOT)


def upstream_reference(style):
    label = 'Italic' if style == 'Ita' else 'Regular'
    return TTFont(io.BytesIO(git_bytes(UPSTREAM, f'build/Lato3{style}2M/ds-ufo/masters/Lato-{label}.ttf')))


def preserve_vertical_metrics(font, style):
    reference = upstream_reference(style)
    for tag, fields in [('hhea', ('ascent','descent','lineGap')),
                        ('OS/2', ('sTypoAscender','sTypoDescender','sTypoLineGap','usWinAscent','usWinDescent'))]:
        for field in fields:
            setattr(font[tag], field, getattr(reference[tag], field))
    font['OS/2'].fsSelection = (font['OS/2'].fsSelection & ~128) | (reference['OS/2'].fsSelection & 128)


def load_donor(style):
    suffix = 'Italic' if style == 'Ita' else 'Upright'
    path = CACHE / f'donor-{style}.glyphs'
    path.write_bytes(git_bytes(DONOR, f'sources/Lato26-{suffix}.glyphs'))
    return GSFont(path)


def upstream_source(style, donor):
    """Convert upstream VFJ without any of the historical revision hooks."""
    data = json.loads(git_bytes(UPSTREAM, f'sources/Lato3{style}2M.vfj'))['font']
    font = copy.deepcopy(donor)
    font.glyphs = []
    font.classes = []
    font.features = []
    font.featurePrefixes = []
    font.kerning = {}
    font.userData = {}
    font.note = f'Upstream {UPSTREAM}; custom lowercase forms are available only through ss05.'
    # Use upstream vertical metrics, including in the editable sources.
    ma, mb = [m['fontMaster'] for m in data['masters']]
    reference = upstream_reference(style)
    hhea, os2 = reference['hhea'], reference['OS/2']
    metrics = {'hheaAscender':hhea.ascent, 'hheaDescender':hhea.descent,
               'hheaLineGap':hhea.lineGap, 'typoAscender':os2.sTypoAscender,
               'typoDescender':os2.sTypoDescender, 'typoLineGap':os2.sTypoLineGap,
               'winAscent':os2.usWinAscent, 'winDescent':os2.usWinDescent}
    for key, value in metrics.items():
        font.customParameters[key] = value
    font.customParameters['Use Typo Metrics'] = bool(os2.fsSelection & 128)
    font.customParameters['Use Extension Kerning'] = True
    originals = {g['name']: g for g in data['glyphs']}
    source = SimpleNamespace(glyphs=originals, style=style)
    def width(name, design):
        a, b, t = build.layer_pair(originals[name], design)
        return a['advanceWidth']*(1-t)+b['advanceWidth']*t
    source.width = width
    suffix = 'Italic' if style == 'Ita' else ''
    masters = [TTFont(io.BytesIO(git_bytes(UPSTREAM,
        f'build/Lato3{style}2M/ds-ufo/masters/Lato.~VF/master_ttf_interpolatable/Lato-{w}{suffix}.ttf')))
        for w in ('Hairline', 'Black')]
    fallback = []
    for original in data['glyphs']:
        name = original['name']
        glyph = gs.GSGlyph(name)
        glyph.unicodes = ([original['unicode'].upper()] if 'unicode' in original
                          else [f'{u:04X}' for u in original.get('unicodes', [])])
        font.glyphs.append(glyph)
        layers = [export.normalize_layer(build.revision.master(original, black)) for black in (False, True)]
        incompatible = export.topology(layers[0]) != export.topology(layers[1])
        if incompatible:
            fallback.append(name)
        for master in font.masters:
            layer = gs.GSLayer()
            layer.layerId = layer.associatedMasterId = master.id
            glyph.layers.append(layer)
            if incompatible:
                export.fallback_layer(layer, name, master.axes[0], source, masters)
                from glyphsLib.types import Point
                t = master.axes[0]/1000
                aa = {a['name']: a for a in layers[0].get('anchors', [])}
                bb = {a['name']: a for a in layers[1].get('anchors', [])}
                for key, value in aa.items():
                    point = export.pts(value.get('point', '0 0'))*(1-t)+export.pts(bb.get(key, value).get('point', '0 0'))*t
                    layer.anchors.append(gs.GSAnchor(key, Point(*map(float, point[0]))))
            else:
                export.fill_layer(layer, export.blended_layer(original, master.axes[0]))
    prefix = data['openTypeFeatures'][0]['feature']
    for cls in data['classes']:
        if not re.search(r'@'+re.escape(cls['name'])+r'\s*=', prefix):
            font.classes.append(gs.GSClass(cls['name'], ' '.join(cls['names'])))
    font.featurePrefixes.append(gs.GSFeaturePrefix('FontLab layout', prefix))
    for feature in data['openTypeFeatures'][1:]:
        tag = feature['name']
        match = re.fullmatch(r'\s*feature\s+'+tag+r'\s*\{(.*)\}\s*'+tag+r';\s*', feature['feature'], re.S)
        assert match, tag
        font.features.append(gs.GSFeature(tag, match[1].strip()))
    for cls in ma['kerning']['kerningClasses']:
        for name in cls['names']:
            if cls.get('1st'):
                font.glyphs[name].rightKerningGroup = cls['name']
            if cls.get('2nd'):
                font.glyphs[name].leftKerningGroup = cls['name']
    pa, pb = ma['kerning']['pairs'], mb['kerning']['pairs']
    for master in font.masters:
        t = master.axes[0]/1000
        for left in sorted(set(pa)|set(pb)):
            for right in sorted(set(pa.get(left, {}))|set(pb.get(left, {}))):
                value = round(float(pa.get(left, {}).get(right, 0))*(1-t)+float(pb.get(left, {}).get(right, 0))*t)
                font.setKerningForPair(master.id,
                    '@MMK_L_'+left[1:] if left.startswith('@') else left,
                    '@MMK_R_'+right[1:] if right.startswith('@') else right, value)
    font.userData['Lato26.compatibleOutlineFallbacks'] = fallback
    configure_hinting(font)
    return font


def configure_hinting(font):
    for instance in font.instances:
        instance.customParameters['Autohint'] = True
        instance.customParameters['TTFAutohint options'] = GLYPHS_HINT_OPTIONS


def effective(font, master_id, left, right):
    pairs = font.kerning[master_id]
    if not hasattr(font, "_ss05_glyphs"):
        font._ss05_glyphs = {g.name: g for g in font.glyphs}
    gl, gr = font._ss05_glyphs[left], font._ss05_glyphs[right]
    # Glyphs stores glyph-specific keys as IDs (names in this generated font).
    lk = '@MMK_L_'+gl.rightKerningGroup if gl.rightKerningGroup else left
    rk = '@MMK_R_'+gr.leftKerningGroup if gr.leftKerningGroup else right
    for a, b in ((left, right), (left, rk), (lk, right), (lk, rk)):
        if a in pairs and b in pairs[a]:
            return pairs[a][b]
    return 0


def add_alternates(font, donor, style):
    manifest = json.loads(git_bytes(DONOR, 'sources/data/lowercase-revision.json'))
    names = [n for n in manifest['styles'][style]['glyphs'] if not n.endswith('.ss05')]
    mapping = {name: name+'.ss05' for name in names}
    # The existing l.ss05 slot receives OUR normal tailed l, not upstream's tail.
    for name, alternate in mapping.items():
        if font.glyphs[alternate]:
            del font.glyphs[alternate]
        glyph = copy.deepcopy(donor.glyphs[name], {id(donor): None})
        glyph.name = alternate
        glyph.unicodes = []
        glyph.leftKerningGroup = font.glyphs[name].leftKerningGroup
        glyph.rightKerningGroup = font.glyphs[name].rightKerningGroup
        for layer in glyph.layers:
            for component in layer.components:
                component.name = mapping.get(component.name, component.name)
        font.glyphs.append(glyph)
    feature = font.features['ss05']
    existing = set(re.findall(r'sub\s+(\S+)\s+by\s+\S+;', feature.code))
    feature.code += '\n'+'\n'.join(f'sub {name} by {alt};' for name, alt in mapping.items() if name not in existing)
    # Preserve explicit and class-based Lato26 spacing, but only on alternate
    # pairs. Keeping the original groups supplies upstream's unmodified pairs.
    all_names = [g.name for g in donor.glyphs if not g.name.endswith('.ss05')]
    changed = 0
    for master in font.masters:
        for left in all_names:
            rights = all_names if left in mapping else names
            for right in rights:
                a, b = mapping.get(left, left), mapping.get(right, right)
                value = effective(donor, master.id, left, right)
                if value != effective(font, master.id, a, b):
                    font.setKerningForPair(master.id, a, b, value)
                    changed += 1
    for master in font.masters:
        font.setKerningForPair(master.id, 'l.ss05', 'o',
            effective(donor, master.id, 'l', 'o') + SS05_LO_SPACING)
    font.userData['Lato26.ss05'] = {'upstream': UPSTREAM, 'donor': DONOR,
                                  'alternates': mapping, 'loSpacingAddition': SS05_LO_SPACING}
    return mapping, changed


def designspace(font):
    ds = to_designspace(font)
    axis = ds.axes[0]
    axis.minimum, axis.default, axis.maximum = 100, 400, 900
    axis.map = [(100+i*100, design) for i, design in enumerate(build.WEIGHTS.values())]
    return ds


def add_capital_spacing(font):
    pairs = {}
    for master in font.masters:
        pairs[master.id] = {}
        for right, extra in SS05_CAPITAL_SPACING.items():
            before = effective(font, master.id, 'l.ss05', right)
            font.setKerningForPair(master.id, 'l.ss05', right, before+extra)
            pairs[master.id][right] = {'before': before, 'after': before+extra}
    font.userData['Lato26.ss05']['capitalSpacingAddition'] = SS05_CAPITAL_SPACING
    font.userData['Lato26.ss05']['capitalSpacingPairs'] = pairs
    return pairs


def compile_variable(font, path):
    font.customParameters['Variable Font Origin'] = next(m.id for m in font.masters if m.axes[0] == 540)
    ds = designspace(font)
    spec = font.userData.get('Lato26.ss05')
    policy = None
    if spec:
        from punctuation_kerning import adjustment
        style = 'Ita' if font.masters[0].italicAngle else 'Upr'
        policy = json.loads(git_bytes(DONOR, 'sources/data/lowercase-spacing.json'))['punctuation_allowance']
        mapping = spec['alternates']
        policy['lefts'][style] = [mapping[n] for n in policy['lefts'][style] if n in mapping]
        for descriptor in ds.sources:
            if descriptor.layerName:
                continue
            design = descriptor.location[ds.axes[0].name]
            master = next(m for m in font.masters if m.axes[0] == design)
            for left in policy['lefts'][style]:
                for right in policy['rights']:
                    descriptor.font.kerning[left, right] = effective(font, master.id, left, right)-adjustment(policy, right, design)
    FontProject().run_from_designspace(ds, output=['variable'],
        output_path=str(path), use_production_names=False, filters=[])
    if policy:
        from punctuation_kerning import append_variable_adjustments
        result = TTFont(path)
        append_variable_adjustments(result, style, policy)
        result.save(path)


def export_otf(font, path):
    """Make CFF from the same static outlines and preserve all layout tables."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.qu2cuPen import Qu2CuPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    result = copy.deepcopy(font)
    glyph_set = font.getGlyphSet()
    strings = {}
    for name in font.getGlyphOrder():
        pen = T2CharStringPen(font['hmtx'][name][0], glyph_set)
        glyph_set[name].draw(Qu2CuPen(ReverseContourPen(pen), max_err=.01, all_cubic=True))
        strings[name] = pen.getCharString()
    for tag in ('glyf','loca','fpgm','prep','cvt ','gasp','TTFA','hdmx','VDMX','LTSH'):
        if tag in result:
            del result[tag]
    result.sfntVersion = 'OTTO'
    builder = FontBuilder(font=result, isTTF=False)
    builder.setupCFF(result['name'].getDebugName(6),
        {'FullName':result['name'].getDebugName(4), 'FamilyName':result['name'].getDebugName(1),
         'Weight':result['name'].getDebugName(2), 'version':'3.100',
         'ItalicAngle':result['post'].italicAngle,
         'UnderlinePosition':result['post'].underlinePosition,
         'UnderlineThickness':result['post'].underlineThickness,
         'Notice':result['name'].getDebugName(0)}, strings, {})
    builder.setupMaxp()
    result.save(path)


def hint_current(font):
    """Hint the current topology with the native ttfautohint-py engine."""
    import sys
    from truetype_hinting import assert_same_outlines
    unhinted, hinted = CACHE/'static-unhinted.ttf', CACHE/'static-hinted.ttf'
    font.save(unhinted)
    font = TTFont(unhinted)  # Compare the rounded serialized outlines.
    subprocess.run([sys.executable, '-m', 'ttfautohint', *HINT_OPTIONS,
        str(unhinted), str(hinted)], check=True)
    result = TTFont(hinted)
    assert_same_outlines(font, result)
    assert font['hmtx'].metrics == result['hmtx'].metrics
    for tag in ('GPOS', 'GSUB', 'GDEF', 'cmap', 'OS/2', 'hhea', 'name'):
        assert font[tag].compile(font) == result[tag].compile(result), tag
    return result


def rehint_existing(styles, skip_carlito):
    import hashlib
    from truetype_hinting import assert_same_outlines
    report = {'options': HINT_OPTIONS, 'fonts': [], 'status': 'passed'}
    paths = []
    for style in styles:
        suffix = 'Italic' if style == 'Ita' else ''
        source_path = ROOT/f'sources/Lato26-{"Italic" if suffix else "Upright"}.glyphs'
        source = GSFont(source_path)
        configure_hinting(source)
        source.save(source_path)
        for name in build.WEIGHTS:
            label = 'Italic' if suffix and name == 'Regular' else name+suffix
            path = ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{label}.ttf'
            paths.append((path, ROOT/'build/Lato26-Desktop/Lato26/TTF'/path.name))
        if not skip_carlito:
            path = ROOT/f'build/Carlito26/Carlito26-Light{suffix}.ttf'
            paths.append((path, ROOT/'build/Lato26-Desktop/Carlito26'/path.name))
    for path, desktop in paths:
        before_bytes = path.read_bytes()
        before = TTFont(io.BytesIO(before_bytes))
        hinted = hint_current(before)
        assert_same_outlines(before, hinted)
        hinted.save(path)
        desktop.write_bytes(path.read_bytes())
        report['fonts'].append({
            'path': str(path.relative_to(ROOT)),
            'before_sha256': hashlib.sha256(before_bytes).hexdigest(),
            'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'outlines_metrics_layout_names_preserved': True,
            'ttfa': hinted['TTFA'].data.decode(),
        })
        print('Rehinted', path.name, flush=True)
    package(('Desktop',))
    report_path = ROOT/'build/proofs/default-latin-hinting.json'
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    build_report_path = ROOT/'build/proofs/upstream-ss05-build.json'
    build_report = json.loads(build_report_path.read_text())
    build_report['static_hinting_options'] = HINT_OPTIONS
    build_report_path.write_text(json.dumps(build_report, indent=2)+'\n')


def restore_carlito():
    from modified_font_names import rename_font
    report = {}
    for style, suffix in [('Upr', ''), ('Ita', 'Italic')]:
        original = TTFont(io.BytesIO(git_bytes(CARLITO, f'build/Carlito/Carlito-Light{suffix}.ttf')))
        path = ROOT/f'build/Carlito26/Carlito26-Light{suffix}.ttf'
        current = TTFont(path)
        affected = json.loads(git_bytes(DONOR, 'sources/data/lowercase-revision.json'))['styles'][style]['glyphs']
        before = {tag: current[tag].compile(current) for tag in ('GPOS','GSUB','GDEF')}
        for name in affected:
            assert current['hmtx'][name][0] == original['hmtx'][name][0]
            current['glyf'][name] = copy.deepcopy(original['glyf'][name])
            current['hmtx'][name] = original['hmtx'][name]
        current = hint_current(current)
        for tag, data in before.items():
            assert data == current[tag].compile(current), tag
        for name in affected:
            a, b = current['glyf'][name], original['glyf'][name]
            assert a.getCoordinates(current['glyf'])[:2] == b.getCoordinates(original['glyf'])[:2], name
        rename_font(current)
        current.save(path)
        desktop = ROOT/'build/Lato26-Desktop/Carlito26'/path.name
        desktop.parent.mkdir(parents=True, exist_ok=True)
        current.save(desktop)
        path.with_name('report-'+path.stem+'.tsv').write_bytes(git_bytes(CARLITO, f'build/Carlito/report-Carlito-Light{suffix}.tsv'))
        report[style] = {'restored_glyphs':len(affected), 'layout_preserved':True}
        print('Restored', path, flush=True)
    return report


def package(kinds=('Desktop', 'Variable')):
    for kind in kinds:
        directory = ROOT/f'build/Lato26-{kind}'
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'README.txt').write_bytes((ROOT/f'sources/data/{kind.lower()}-readme.txt').read_bytes())
        with zipfile.ZipFile(directory.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(directory.rglob('*')):
                if path.is_file() and path.name != 'LICENSE.txt' and not path.name.startswith('.') and path.suffix in {'.ttf', '.otf', '.woff2', '.txt'}:
                    archive.write(path, str(path.relative_to(directory)))
            archive.write(ROOT/'LICENSE.txt', 'LICENSE.txt')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sources-only', action='store_true')
    ap.add_argument('--style', choices=['Upr', 'Ita', 'all'], default='all')
    ap.add_argument('--skip-carlito', action='store_true')
    ap.add_argument('--rehint-only', action='store_true',
                    help='Rehint existing static TTFs and refresh the desktop archive without rebuilding outlines')
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    if args.rehint_only:
        if args.sources_only:
            ap.error('--rehint-only cannot be combined with --sources-only')
        rehint_existing(['Upr', 'Ita'] if args.style == 'all' else [args.style], args.skip_carlito)
        return
    report = {'upstream': subprocess.check_output(['git','rev-parse',UPSTREAM],cwd=ROOT,text=True).strip(),
              'donor': DONOR, 'static_hinting_options': HINT_OPTIONS, 'styles': {}}
    previous_report = ROOT/'build/proofs/upstream-ss05-build.json'
    if args.skip_carlito and previous_report.exists():
        previous = json.loads(previous_report.read_text())
        if 'carlito' in previous:
            report['carlito'] = previous['carlito']
    for style in (['Upr','Ita'] if args.style == 'all' else [args.style]):
        print('Loading', style, flush=True)
        donor = load_donor(style)
        font = upstream_source(style, donor)
        print('Converted upstream', style, flush=True)
        baseline = copy.deepcopy(font)
        mapping, pairs = add_alternates(font, donor, style)
        capital_pairs = add_capital_spacing(font)
        suffix = 'Italic' if style == 'Ita' else 'Upright'
        path = ROOT/f'sources/Lato26-{suffix}.glyphs'
        font.save(path)
        baseline.save(CACHE/f'upstream-{style}.glyphs')
        report['styles'][style] = {'alternates':mapping, 'kerning_overrides':pairs,
                                    'ss05_lo_spacing_addition':SS05_LO_SPACING,
                                    'ss05_capital_spacing_addition':SS05_CAPITAL_SPACING,
                                    'capital_spacing_pairs':capital_pairs}
        print(path, len(mapping), 'alternates;', pairs, 'pair overrides', flush=True)
        if args.sources_only:
            continue
        directory = ROOT/'build/Lato26-Variable'
        directory.mkdir(parents=True, exist_ok=True)
        italic = 'Italic' if style == 'Ita' else ''
        output = directory/f'Lato26-Variable{italic}.ttf'
        compile_variable(font, output)
        compile_variable(baseline, CACHE/f'upstream-{style}.ttf')
        variable = TTFont(output)
        importlib.import_module('32_build_variable_fonts').normalize_names(variable, bool(italic))
        variable.save(output)
        web = copy.deepcopy(variable); web.flavor = 'woff2'; web.save(output.with_suffix('.woff2'))
        for weight, name in enumerate(build.WEIGHTS, 1):
            label = 'Italic' if italic and name == 'Regular' else name+italic
            static = instantiateVariableFont(variable, {'wght':weight*100}, inplace=False)
            family = 'Lato26'
            for nid, value in {1:family,2:label,4:family+' '+label,6:family+'-'+label,16:family,17:label}.items():
                static['name'].setName(value,nid,3,1,0x409)
                static['name'].setName(value,nid,1,0,0)
            static['OS/2'].fsSelection = (static['OS/2'].fsSelection & ~0x61) | (1 if italic else 0) | (0x20 if weight == 7 else (0x40 if not italic else 0))
            static['head'].macStyle = (1 if weight == 7 else 0) | (2 if italic else 0)
            # Fresh hints use this font's own topology; historical Bold-a point
            # controls refer to the former default a and must not be reused.
            static = hint_current(static)
            dest = ROOT/f'build/Lato3{style}2M/ds-ufo/masters/Lato26-{label}.ttf'
            static.save(dest)
            desktop = ROOT/f'build/Lato26-Desktop/Lato26/TTF/Lato26-{label}.ttf'
            desktop.parent.mkdir(parents=True,exist_ok=True); static.save(desktop)
            export_otf(static, dest.with_suffix('.otf'))
            desktop_otf = ROOT/f'build/Lato26-Desktop/Lato26/OTF/Lato26-{label}.otf'
            desktop_otf.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(dest.with_suffix('.otf'), desktop_otf)
            print('Built', label, flush=True)
    if not args.sources_only:
        if not args.skip_carlito:
            report['carlito'] = restore_carlito()
        (ROOT/'build/Lato26-Variable/build-info.json').write_text(json.dumps(report, indent=2)+'\n')
        package()
    (ROOT/'build/proofs/upstream-ss05-build.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
