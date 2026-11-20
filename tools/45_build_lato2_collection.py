#!/usr/bin/env python3
"""Build, verify and package the complete Lato26 collection on Lato 2.015."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

base=importlib.import_module('41_rebase_on_lato2')
variable=importlib.import_module('42_build_lato2_variable_sources')
checks=importlib.import_module('43_check_lato2_rebase')
ROOT=base.ROOT


def verify_reference():
    manifest=json.loads((base.REFERENCE/'manifest.json').read_text())
    for item in manifest['files']:
        assert hashlib.sha256((base.REFERENCE/item['file']).read_bytes()).hexdigest()==item['sha256'],item['file']


def install(static_dir,variable_dir,source_dir):
    """Activate validated outputs and refresh local distribution copies."""
    for style in ('Upr','Ita'):
        destination=ROOT/f'build/Lato3{style}2M/ds-ufo/masters'
        for weight in base.WEIGHTS:
            for suffix in ('ttf','otf'):
                name=f'Lato26-{base.label(style,weight)}.{suffix}'
                shutil.copy2(static_dir/name,destination/name)
        name=f'Lato26-{"Italic" if style=="Ita" else "Upright"}.glyphs'
        shutil.copy2(source_dir/name,ROOT/'sources'/name)
    target=ROOT/'build/Lato26-Variable';target.mkdir(parents=True,exist_ok=True)
    for path in variable_dir.iterdir():
        if path.suffix in ('.ttf','.woff2','.json'):shutil.copy2(path,target/path.name)
    info=[{'path':f'build/Lato26-Variable/Lato26-Variable{"Italic" if style=="Ita" else ""}.ttf',
           'base':'Published Lato 2.015','version':'2.026','masters':9,'glyphs':3023,'unicode_characters':2164,
           'source':f'sources/Lato26-{"Italic" if style=="Ita" else "Upright"}.glyphs',
           'hinting':'unhinted','axis':{'wght':[100,400,900]},
           'reconstruction':'Exact curve subdivision, compatible quadratic conversion; missing variable mark anchors filled from nearest released weight.'}
          for style in ('Upr','Ita')]
    (target/'build-info.json').write_text(json.dumps(info,indent=2)+'\n')
    importlib.import_module('23_restore_l_bowl_spacing').package()
    importlib.import_module('32_build_variable_fonts').package(target)
    subprocess.run([sys.executable,str(ROOT/'.github/scripts/refresh_specimen_fonts.py')],check=True)


def build(stage):
    verify_reference();stage.mkdir(parents=True,exist_ok=True)
    statics=stage/'static';variants=stage/'variable';sources=stage/'sources';sources.mkdir(exist_ok=True)
    reports=[base.build_one(s,w,statics) for s in ('Upr','Ita') for w in base.WEIGHTS]
    for style in ('Upr','Ita'):
        fonts,report=variable.compatible_masters(style,statics,stage/'compatible')
        variable.export_variable(fonts,style,variants)
        variable.export_glyphs(fonts,style,sources/f'Lato26-{"Italic" if style=="Ita" else "Upright"}.glyphs')
        (ROOT/f'build/proofs/lato2-{style}-compatibility.json').write_text(json.dumps(report,indent=2)+'\n')
    validation={'status':'passed','static':checks.check_static(statics),'bold_joins':checks.check_bold(statics),
                'variable':checks.check_variable(variants,statics),'sources':checks.check_sources(sources,stage/'compatible'),'native_variable':checks.check_native_variables(variants)}
    (ROOT/'build/proofs/lato2-rebase-checks.json').write_text(json.dumps(validation,indent=2)+'\n')
    install(statics,variants,sources)
    for report in reports:
        name=Path(report['path']).name;style='Ita' if 'Italic' in name else 'Upr'
        report['path']=f'build/Lato3{style}2M/ds-ufo/masters/{name}'
    (ROOT/'build/proofs/lato2-rebase-validation.json').write_text(json.dumps({'status':'passed','fonts':reports},indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tools/44_proof_lato2_rebase.py')],check=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',type=Path,default=ROOT/'.cache/lato2-rebuild')
    args=ap.parse_args();build(args.stage)

if __name__=='__main__':main()
