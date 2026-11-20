#!/usr/bin/env python3
"""Regroup ungrouped kerning keys without changing values or outline text.

The reconstructed Lato 2.015 sources have no exceptions to their profile-based
groups. Leaving one-member profiles ungrouped makes Glyphs expand mixed
glyph/class pairs into a large exception lookup in variable Text Preview.
Singleton classes retain exactly the same pair coverage and values.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re

from glyphsLib.parser import Parser
from glyphsLib.writer import Writer

ROOT = Path(__file__).resolve().parents[1]
GLYPH_HEADER = re.compile(
    r'^glyphname = ([^;\n]+);\n((?:kern(?:Left|Right) = [^;\n]+;\n)*)', re.M
)
EXTENSION = '{\nname = "Use Extension Kerning";\nvalue = 1;\n},\n'


def kerning_span(text):
    start = text.index('\nkerningLTR = {') + 1
    # This dictionary contains no arrays or multiline quoted strings. Find
    # its closing brace rather than relying on the next font-info field.
    depth = 0
    for match in re.finditer(r'[{}]', text[start:]):
        depth += 1 if match.group() == '{' else -1
        if depth == 0:
            end = start + match.end()
            assert text[end:end + 2] == ';\n'
            return start, end + 2
    raise ValueError('Unclosed kerningLTR dictionary')


def fix(path):
    original = path.read_text()
    start, end = kerning_span(original)
    before = Parser().parse('{\n' + original[start:end] + '}')['kerningLTR']
    headers = {m[1]: m[2] for m in GLYPH_HEADER.finditer(original)}
    used = [set(before_key for rows in before.values() for before_key in rows),
            set(key for rows in before.values() for row in rows.values() for key in row)]
    mappings = []
    additions = {}
    for side, keys, field in [('L', used[0], 'kernRight'), ('R', used[1], 'kernLeft')]:
        mapping = {}
        existing = set(re.findall(r'^' + field + r' = ([^;]+);$', original, re.M))
        for name in sorted(keys):
            if name.startswith('@'):
                continue
            assert name in headers, ('Unknown kerning glyph', name)
            # Preserve actual authored exceptions on already-grouped glyphs.
            if re.search(r'^' + field + ' = ', headers[name], re.M):
                continue
            group = 'single_' + name
            while group in existing:
                group += '_'
            existing.add(group)
            mapping[name] = f'@MMK_{side}_{group}'
            additions.setdefault(name, []).append(f'{field} = {group};\n')
        mappings.append(mapping)
    after = {
        master: {
            mappings[0].get(left, left): {
                mappings[1].get(right, right): value for right, value in row.items()
            } for left, row in rows.items()
        } for master, rows in before.items()
    }
    inverse = [{new: old for old, new in mapping.items()} for mapping in mappings]
    restored = {
        master: {
            inverse[0].get(left, left): {
                inverse[1].get(right, right): value for right, value in row.items()
            } for left, row in rows.items()
        } for master, rows in after.items()
    }
    assert restored == before, 'Kerning values or coverage changed'
    stream = io.StringIO()
    Writer(stream, format_version=3).writeKeyValue('kerningLTR', after)
    replacement = stream.getvalue()
    updated = original[:start] + replacement + original[end:]
    updated = GLYPH_HEADER.sub(
        lambda m: m[0] + ''.join(additions.get(m[1], [])), updated
    )
    if 'name = "Use Extension Kerning";' not in updated:
        updated = updated.replace('customParameters = (\n',
                                  'customParameters = (\n' + EXTENSION, 1)
    else:
        updated = re.sub(r'(name = "Use Extension Kerning";\nvalue = )[^;]+;',
                         r'\g<1>1;', updated, count=1)

    def unrelated(text):
        a, b = kerning_span(text)
        text = text[:a] + text[b:]
        text = re.sub(r'^kern(?:Left|Right) = [^;\n]+;\n', '', text, flags=re.M)
        return re.sub(r'\{\nname = "Use Extension Kerning";\nvalue = [^;]+;\n\},\n', '', text)

    assert unrelated(original) == unrelated(updated), 'Unrelated source data changed'
    check_start, check_end = kerning_span(updated)
    assert Parser().parse('{\n' + updated[check_start:check_end] + '}')['kerningLTR'] == after
    path.write_text(updated)
    return {
        'file': path.name,
        'new_left_classes': len(mappings[0]),
        'new_right_classes': len(mappings[1]),
        'masters': len(before),
        'records': sum(len(row) for rows in before.values() for row in rows.values()),
        'kerning_values_and_coverage_unchanged': True,
        'unrelated_source_text_sha256': hashlib.sha256(unrelated(original).encode()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path,
                        default=[ROOT / 'sources' / f'Lato26-{style}.glyphs'
                                 for style in ('Upright', 'Italic')])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    results = [fix(path) for path in args.files]
    report = json.dumps(results, indent=2) + '\n'
    print(report, end='')
    if args.report:
        args.report.write_text(report)


if __name__ == '__main__':
    main()
