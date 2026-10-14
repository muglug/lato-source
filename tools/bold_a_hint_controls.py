"""Stem analysis and contour-join instructions for the revised Bold a."""

from fontTools.ttLib.tables.ttProgram import Program


def bold_a_matches(font):
    """Find exact translated copies of the authored Bold a body.

These point references describe the shipped Bold outline. Check its geometry
before emitting them; find translated copies in accented/Cyrillic forms.
"""
    if font['name'].getDebugName(6) != 'Lato26-Bold':
        return []
    glyph = font['glyf']['a']
    assert list(glyph.endPtsOfContours) == [22, 30, 91]
    assert tuple(glyph.coordinates[57]) == (668, 609)
    assert tuple(glyph.coordinates[58]) == (699, 458)
    reference = list(glyph.coordinates[:60])
    matches = []
    for name in font.getGlyphOrder():
        other = font['glyf'][name]
        if other.numberOfContours <= 0:
            continue
        points = list(other.coordinates)
        for start in [0] + [end+1 for end in other.endPtsOfContours[:-1]]:
            if start+60 > len(points):
                continue
            dx, dy = points[start][0]-reference[0][0], points[start][1]-reference[0][1]
            if all((x+dx, y+dy) == point for (x,y),point in zip(reference,points[start:start+60])):
                assert tuple(points[start+2]) == (664+dx, 622+dy)
                assert tuple(points[start+29]) == (664+dx, 638+dy)
                assert tuple(points[start+1]) == (905+dx, 622+dy)
                assert tuple(points[start+30]) == (905+dx, 638+dy)
                matches.append((name, start))
                break
    assert len(matches) == 34
    return matches


def bold_a_controls(font):
    """Exclude overlapping cut edges and the short bowl closure from analysis."""
    return [f'{name} nodir {start}-{start+3},{start+29}-{start+30},{start+58}'
            for name, start in bold_a_matches(font)]


def join_program(start):
    """Extend the stem only when needed to retain its original join overlap.

The autohinter treats the arch and stem as separate contours. After it runs,
set each stem-end y to max(current y, hinted arch y + original overlap).
Read the scaled original overlap with GC[1], so fractional ppem works too.
Only two on-curve points on straight edges move; no IUP follows this footer,
so the bowl, arch curves, accents, x coordinates, and advances stay intact.

Instruction semantics: https://learn.microsoft.com/typography/opentype/spec/tt_instructions
"""
    assembly = ['SVTCA[0]', 'PUSHB[ ]', '1', 'SZP2[ ]']
    for lower, upper in ((start+29, start+2), (start+30, start+1)):
        assembly.extend(['PUSHW[ ]', str(lower),
                         'PUSHW[ ]', str(upper), 'GC[0]',
                         'PUSHW[ ]', str(lower), 'GC[1]',
                         'PUSHW[ ]', str(upper), 'GC[1]',
                         'SUB[ ]', 'ADD[ ]',
                         'PUSHW[ ]', str(lower), 'GC[0]',
                         'MAX[ ]', 'SCFS[ ]'])
    program = Program()
    program.fromAssembly(assembly)
    return bytes(program.getBytecode())


def link_bold_a_joins(font):
    """Append the join constraints after the regenerated autohint programs."""
    matches = bold_a_matches(font)
    for name, start in matches:
        program = font['glyf'][name].program
        original = bytes(program.getBytecode())
        footer = join_program(start)
        assert original and not original.endswith(footer), ('join constraints already installed', name)
        program.fromBytecode(original + footer)
    if matches:
        font['maxp'].maxSizeOfInstructions = max(
            len(g.program.getBytecode()) for g in font['glyf'].glyphs.values()
            if hasattr(g, 'program'))
        font['maxp'].maxStackElements = max(font['maxp'].maxStackElements, 4)
    return len(matches)
