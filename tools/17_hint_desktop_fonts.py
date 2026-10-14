#!/usr/bin/env python3
"""Rehint all 20 desktop TTFs without rebuilding or changing their outlines."""
import importlib
import json
from fontTools.ttLib import TTFont
from truetype_hinting import hint_font, engine_version, OPTIONS, configure_glyphs_instances

build = importlib.import_module('07_build_revised_lato')
ROOT = build.ROOT


def main():
    report = {'engine':engine_version(), 'options':OPTIONS, 'fonts':[]}
    for style in ('Upr','Ita'):
        source = build.Source(style)
        directory = ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
        paths = sorted(directory.glob('Lato26-*.ttf'))
        paths.append(ROOT/'build/Carlito26'/('Carlito26-LightItalic.ttf' if style=='Ita' else 'Carlito26-Light.ttf'))
        for path in paths:
            font = TTFont(path, recalcTimestamp=False)
            required = [build.output_name(source,n,font) for n in source.affected]
            counts = hint_font(font, required)
            temporary = path.with_suffix('.hinted.tmp')
            font.save(temporary)
            temporary.replace(path)
            counts['file'] = str(path.relative_to(ROOT))
            report['fonts'].append(counts)
            print(counts['file'], counts['revised_glyphs_with_instructions'], 'revised glyphs hinted', flush=True)
    report['status'] = 'passed'
    report['desktop_fonts'] = len(report['fonts'])
    report['revised_glyph_instances'] = sum(r['revised_glyphs_with_instructions'] for r in report['fonts'])
    path=ROOT/'build/proofs/truetype-hinting.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    build.REGULAR.write_bytes(configure_glyphs_instances(build.REGULAR.read_bytes().decode()).encode())
    print(path,flush=True)


if __name__=='__main__':main()
