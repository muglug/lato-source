Lato26 desktop fonts

Nine weights, each upright and italic, in TTF and OTF format.
Install either the TTF or OTF set.

Carlito26 Light and Light Italic retain the existing Carlito advance widths.

Modified lowercase l tails, enlarged double-storey a bowls, and lowered e bars,
including applicable related characters. The ae join is aligned with the
lowered e bar. Lato26 pair kerning adjusts the tailed l before curved and
diagonal left sides, with individual clearance exceptions.

The preceding spacing pass refined room for the l bowl using Fira Sans l/I
relationships, multiscale blurred-ink interaction, and mid-height gaps.
Compared with the first allowance pass, Regular upright lc/le/lo tighten
55 units and ly tightens 75; la tightens 55 and lw tightens 40. Heavy ld/lq
pairs gain room. Italics use separate curves; Regular italic ly is unchanged.
No pair becomes tighter than before the initial allowance pass.

The earlier a +20, w +8, y +14 breathing-room preferences are retained inside
this base spacing. lc and lo still match le.
Related accents and alternates follow their bases, retaining clearance
exceptions for hooks and marks. Native UPM is 2,000.

The updated PDF proofs and measurement files in the source repository include
all la-lz pairs, a multiscale unhinted Gaussian blur audit, and lower-bowl
contour clearance. These diagnose spacing relationships, not an objectively
optimal value. Both TTF and OTF kerning is current.

Smaller l bowl and advance

The authored Regular l now has a 537-unit advance (previously 591.3), with a
narrower, lower bowl. The same change is propagated through all weights,
including italics using the existing t-derived bowl transformation, and
35 related glyphs per style. The exact authored Regular layer is preserved
in the editable Glyphs source. Carlito26 keeps its original advances.

Special-pair edge gaps are preserved with compensating kerning, including
lc/le/lo, la, lw, ly, and ll, plus accent and hook exceptions. Ordinary
vertical-left pairs such as lh, li, and lj keep their kerning and use the
narrower advance. TTF and OTF compensation accounts for curve conversion
rounding, keeping prior special-pair edge gaps within half a font unit.
Only revised l instructions are regenerated. All unrelated glyphs and
hint programs, including the corrected Bold a, remain intact.

Original authorship and licensing are retained inside the fonts and in
LICENSE.txt.

TrueType hinting update

All 20 desktop TTFs use ttfautohint 1.3 with the engine settings of released
Lato 2.015, replacing the repository's 3.100 hinting. The recipe reproduces
the original glyph programs and global hint tables in all 18 reference
fonts exactly. Lato26 instructions are regenerated for the current outlines;
small design differences can still affect rendering.

The Bold upright a and 33 matching accented/Cyrillic forms have a focused
bowl-top hinting correction. The italic a outline remains unchanged.
The hinting pass preserved outline coordinates, advance widths, naming, and kerning.
Use the TTF set for Windows ClearType testing. Only TTF files contain these hints.

Hints use strong stem widths in all three render modes, x-height boost limit
14, Windows clipping zones, and Latin fallback. They are optimized for
8-50 ppem and enabled through 200 ppem. Standalone Glyphs exports use its
bundled autohinter; use the repository build for this pinned engine and the
Bold bowl-top control.

Bold a join correction

The Bold upright a and all 33 matching accented/Cyrillic forms now include
final point-link instructions. These preserve the overlap between the upper
arch and lower stem while retaining the thinner bowl-top hinting. At 14 px,
the former 0.95 px gap becomes a 0.11 px overlap; the bowl top remains 1.30 px.
Source outlines, spacing, and accent positions are unchanged. Validation
covers 34 forms in 32,946 size/render-target cases, including fractional sizes.
Standalone Glyphs exports do not include these final join instructions;
use the repository build or these packaged TTFs for the corrected result.
