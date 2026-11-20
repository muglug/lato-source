#!/usr/bin/env python3
"""Refine the first bowl allowance using l/I blur and mid-height comparisons.

Run once after 23_restore_l_bowl_spacing.py. Values are deliberate, bounded
design choices in native 2000 UPM, not automatic fits to Fira Sans. Export
fonts with 23 --refresh-only and Glyphs with 11 after migrating the sources.
"""
import copy
import importlib
import json

from lowercase_kerning import CONFIG

restore = importlib.import_module('23_restore_l_bowl_spacing')
DESIGNS = (0, 540, 780, 1000)
# Changes from the first allowance pass: Hairline, Regular, Bold, Black.
# Conflicting evidence (notably g) is left alone. The a/w/y preference
# offsets are separate and remain intact. c/e/o share one adjustment.
DELTAS = {
    'Upr': {'a': (-30, -55, -10, -5), 'e': (-45, -55, -25, -10),
            'd': (-5, -20, 30, 45), 'q': (-5, -20, 30, 45),
            's': (-10, -50, 0, 0), 'v': (-50, -60, -25, -5),
            'w': (-35, -40, -5, 0), 'x': (0, -20, 0, 0),
            'y': (-60, -75, -35, -15)},
    'Ita': {'a': (0, 0, 20, 30), 'e': (-20, -25, -5, 0),
            'd': (0, 0, 35, 50), 'q': (0, 0, 35, 50),
            's': (0, -15, 0, 0), 'v': (-25, -25, 15, 25),
            'w': (-10, -15, 20, 30), 'x': (-25, -35, -12, 0),
            'y': (0, 0, 20, 30)},
}


def make_policy(old):
    assert 'bowl_allowance' in old, 'Apply the initial bowl allowance first.'
    assert 'rhythm_refinement' not in old, 'Rhythm refinement already applied.'
    config = copy.deepcopy(old)
    policy = config['bowl_allowance']
    policy['initial_budgets'] = policy.pop('budgets')
    policy['description'] = ('Per-shape l bowl allowance refined with l/I blurred-ink '
                             'interaction and mid-xheight gaps; preserve vertical pairs, ll, and fl ligatures.')
    changes = {}
    for style, additions in policy['additions'].items():
        changes[style] = {}
        for right, stops in additions.items():
            if right in old['e_rights'] or right in old['match_e_spacing_rights']:
                base = 'e'
            elif right.startswith(('schwa', 'eopen', 'ereversed', 'eturned', 'eth')):
                continue  # Distinct left contours; no evidence for the same correction.
            else:
                base = next((b for b in DELTAS[style] if right.startswith(b)), None)
            if base is None:
                continue
            delta = DELTAS[style][base]
            assert [d for d, _ in stops] == list(DESIGNS)
            for stop, amount in zip(stops, delta):
                stop[1] += amount
                # Never remove more than the preceding blanket allowance.
                assert stop[1] >= 0, (style, right, stop)
            changes[style][right] = list(delta)
    config['rhythm_refinement'] = {
        'description': 'Reduce excessive upright lo/ly spacing; selective related-shape and italic corrections. Preserve existing a/w/y preferences.',
        'designs': list(DESIGNS), 'base_deltas': DELTAS,
        'applied_deltas': changes,
        'method': 'Compare lX/IX at three Gaussian radii and mid-xheight contour gaps against Fira Sans 4.301; use conservative changes where the metrics disagree.',
        'unchanged': ['capital-I pairs', 'incoming pairs such as ol', 'vertical-left pairs', 'll', 'fl/ffl', 'g', 'Carlito26'],
    }
    return config


def main():
    old = json.loads(CONFIG.read_text())
    updated = make_policy(old)
    restore.migrate_sources(old, updated)
    print('Refined per-shape allowance in both VFJ sources and spacing policy.', flush=True)


if __name__ == '__main__':
    main()
