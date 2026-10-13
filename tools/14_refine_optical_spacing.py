#!/usr/bin/env python3
"""One-time l/a, l/c, l/w and l/y refinement following the spacing review.

The small positive additions encode the designer's requested ordering.
15_audit_optical_spacing.py measures their effect without treating its
blur-overlap index as a perceptually validated optimum.
"""
import copy
import importlib
import json

from lowercase_kerning import CONFIG, correction

build = importlib.import_module('07_build_revised_lato')
refine = importlib.import_module('10_refine_ae_and_l_spacing')


def main():
    old = json.loads(CONFIG.read_text())
    if old.get('optical_adjustments'):
        raise SystemExit('Already applied; rebuild with 07 and export Glyphs with 11.')
    config = copy.deepcopy(old)
    rights = {n for spec in config['styles'].values() for n in spec['right']}
    c_rights = sorted(n for n in rights if n.startswith('c'))
    config['match_e_spacing_bases'] = {n: 'o' for n in config['match_e_spacing_rights']}
    config['match_e_spacing_bases'].update({n: 'c' for n in c_rights})
    config['match_e_spacing_rights'] = sorted(set(config['match_e_spacing_rights']) | set(c_rights))
    config['optical_adjustments'] = {
        base: {'units': units, 'rights': sorted(n for n in rights if n.startswith(base))}
        for base, units in [('a', 20), ('w', 8), ('y', 14)]}
    changed = set(c_rights) | {n for item in config['optical_adjustments'].values() for n in item['rights']}
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        path = build.ROOT/f'sources/Lato3{style}2M.vfj'
        text = path.read_text()
        data = json.loads(text)['font']
        for wrapped in data['masters']:
            master = wrapped['fontMaster']
            design = 1000 if master['name'].startswith('Black') else 0
            kerning = master['kerning']; before = copy.deepcopy(kerning)
            for left in config['styles'][style]['left']:
                base = [refine.effective(before['pairs'], before['kerningClasses'], left, right)
                        - correction(source, left, right, design, old) for right in ('e', 'c')]
                assert base[0] == base[1], (style, left, base)
                row = kerning['pairs'].setdefault(left, {})
                for right in sorted(changed & set(config['styles'][style]['right'])):
                    delta = correction(source, left, right, design, config)-correction(source, left, right, design, old)
                    row[right] = str(refine.effective(before['pairs'], before['kerningClasses'], left, right)+delta)
            text = refine.patch_json_block(text, before, kerning, 10)
        path.write_text(text)
        print(style, 'la +20, lw +8, ly +14; lc matched to le', flush=True)
    CONFIG.write_text(json.dumps(config, indent=2)+'\n')


if __name__ == '__main__':
    main()
