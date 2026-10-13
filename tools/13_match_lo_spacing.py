#!/usr/bin/env python3
"""One-time native source update: match l/o-family gaps to l/e gaps."""
import copy
import importlib
import json

from lowercase_kerning import CONFIG, correction

build = importlib.import_module('07_build_revised_lato')
refine = importlib.import_module('10_refine_ae_and_l_spacing')


def main():
    old_config = json.loads(CONFIG.read_text())
    if old_config.get('match_e_spacing_rights'):
        raise SystemExit('Already applied; rebuild with 07 and export Glyphs with 11.')
    config = copy.deepcopy(old_config)
    config['match_e_spacing_rights'] = sorted({
        n for spec in config['styles'].values() for n in spec['right']
        if n.startswith('o')})
    for style in ('Upr', 'Ita'):
        source = build.Source(style)
        path = build.ROOT/f'sources/Lato3{style}2M.vfj'
        text = path.read_text()
        data = json.loads(text)['font']
        for wrapped in data['masters']:
            master = wrapped['fontMaster']
            design = 1000 if master['name'].startswith('Black') else 0
            kerning = master['kerning']
            before = copy.deepcopy(kerning)
            for left in config['styles'][style]['left']:
                # The original e/o kerns must agree for the shared correction.
                base = [refine.effective(before['pairs'], before['kerningClasses'], left, right)
                        - correction(source, left, right, design, old_config)
                        for right in ('e', 'o')]
                assert base[0] == base[1], (style, left, base)
                row = kerning['pairs'].setdefault(left, {})
                for right in config['match_e_spacing_rights']:
                    if right not in config['styles'][style]['right']:
                        continue
                    delta = (correction(source, left, right, design, config)
                             - correction(source, left, right, design, old_config))
                    row[right] = str(refine.effective(before['pairs'], before['kerningClasses'], left, right)+delta)
            text = refine.patch_json_block(text, before, kerning, 10)
        path.write_text(text)
        print(style, 'native o-family spacing matched to e')
    CONFIG.write_text(json.dumps(config, indent=2)+'\n')


if __name__ == '__main__':
    main()
