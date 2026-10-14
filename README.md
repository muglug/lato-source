# Sources for Lato26 (modified Lato)

The modified family is named **Lato26** in font menus, PostScript names, source
metadata, and exported filenames. The metric-compatible Light derivative is
separate as **Carlito26**. Original designer, copyright, and license notices are
retained below and inside the fonts.

- Version 3.100.dev2; Latin+Cyrillic+Greek+IPA opensource
- Created by: tyPoland Lukasz Dziedzic
- Designed by: Łukasz Dziedzic with Adam Twardoch and Botio Nikoltchev
- Creation year: 2020
- Copyright (c) 2010-2020 by tyPoland Lukasz Dziedzic with Reserved Font Name “Lato”. Licensed under the Licensed under the [SIL Open Font License, Version 1.1](./LICENSE.txt).
- Lato is a trademark of tyPoland Lukasz Dziedzic.
- Website URL: http://www.latofonts.com/

Lato is a sanserif typeface family designed in the Summer 2010 and extended in the Summer 2013 by Warsaw-based designer Lukasz Dziedzic ("Lato" means "Summer" in Polish). It tries to carefully balance some potentially conflicting priorities: it should seem quite "transparent" when used in body text but would display some original traits when used in larger sizes. The classical proportions, particularly visible in the uppercase, give the letterforms familiar harmony and elegance. At the same time, its sleek sanserif look makes evident the fact that Lato was designed in the 2010s, even though it does not follow any current trend. The semi-rounded details of the letters give Lato a feeling of warmth, while the strong structure provides stability and seriousness. In 2013-2014, the family was greatly extended (with the help of Adam Twardoch and Botio Nikoltchev) to cover 3000+ glyphs over nine weights with italics. It now supports 100+ Latin-based languages, 50+ Cyrillic-based languages as well as Greek and IPA phonetics. The Lato fonts are available free of charge under the SIL Open Font License from https://www.latofonts.com/

## Contact

To contact the Lato team, create a Github account and open a [Github issue](https://github.com/latofonts/lato-source/issues) on this repository.

## Building

1. Download or clone this repo
2. Download and install most recent [FontLab 7](https://download.fontlab.com/)
3. Install Python 3
4. Run:

```
python3 -m pip install --user --upgrade git+https://github.com/fonttools/fonttools/@feaLib-STAT#egg=fonttools[interpolatable,lxml,plot,symfont,type1,ufo,unicode,woff] git+https://github.com/googlefonts/fontmake afdko psautohint
```

5. Go to the [`tools`](tools) folder
6. Run FontLab 7
7. In FontLab 7, open the [`01_export_fontlab_lato.vfpy`](tools/01_export_fontlab_lato.vfpy) script. Wait until it exports the fonts as DesignSpace + UFO and quits
8. In Terminal, go to the [`tools`](tools) folder and run:

```
python3 03_build_lato_fontmake.py
```

## Technical details

### October 2026 lowercase revision

The active upright and italic VFJ sources and all shipped Lato26/Carlito26 exports
include a right-facing `j` tail on `l`, its `ss05` alternate, accents, modifiers,
and `fl`/`ffl` ligatures. The italic bowl uses the narrowing and shear measured
from upright/italic `t`. Lato26 spacing accommodates the tail; Carlito26 retains
every existing advance width and its layout tables.

The enlarged double-storey `a` bowl and lowered `e` bar in
`build/Lato3Upr2M/ds-ufo/masters/Lato26-Regular.glyphs` are propagated through
applicable accents, Cyrillic counterparts, `ae`/`oe`, turned/reversed forms,
and smaller letterforms. Full-size italic `a` retains its distinct single-storey
design. Descending phonetic hooks and the connected `ls`/`lz` terminals retain
their characteristic forms. The dated `sources/240102` snapshots are archival.

Rebuild the existing exports from the revised sources with:

```sh
python tools/07_build_revised_lato.py
python tools/08_refresh_carlito_outlines.py
python tools/09_check_lowercase_revision.py
```

These tools require `fonttools`, `glyphsLib`, `numpy`, `openstep-plist`,
`skia-pathops`, `matplotlib`, and `Pillow` with RAQM shaping support. The Carlito refresh uses the existing Carlito
fonts and per-glyph reports as its metric reference, so it does not require the
original Calibri installation. The original interpolation weight is recovered
from the unchanged master advances and recorded in
`sources/data/lowercase-revision.json`.

`06_update_lato_outlines.py` records the one-time source transformation; it
requires the pre-revision VFJs and Regular TTF and refuses to apply twice.
The rebuild preserves the saved Regular `a` quadratics. The later four-master
`e` revision supersedes the earlier quadratic `e` override. Cubic source
edits use compatible subdivisions; stale hints referencing changed point
indexes are removed before the final desktop TrueType hinting pass.
Existing unrelated outlines and layout tables are kept.
Vector PDF proofs are in `output/pdf/`; validation reports are in `build/proofs/`. The checker accepts
`--baseline-dir PATH` to additionally verify unrelated outlines, layout,
metrics, and the authored Glyphs paths against a saved pre-revision build.

The follow-up revision aligns both edges of the `a` bowl in `ae` with the
lowered `e` crossbar, including accented and turned forms. The first spacing
pass offset most of the added `l` advance before round and diagonal left sides.
For `le` and accented forms it restored a quarter of the removed space through
Regular, and half from Bold onward. The later bowl-allowance pass below reduces
that compensation further so the wider `l` retains room for its bowl.
The `lo` and `lc` gaps now match `le`, including `fl`/`ffl` ligatures and accented
forms, with a small correction for the different left edges of `e`, `o`, and `c`.
The later optical-spacing review adds 20 units before `a`, 8 before `w`, and
14 before `y` after the revised `l` forms. These are constant across weights
and styles (1.0%, 0.4%, and 0.7% of the 2,000-unit em), with related accented
forms receiving the same additions.
This weight-dependent kerning curve is recorded in the spacing JSON and applied
by the rebuild tools. Tighter bowls, hooks, and
accents receive individual clearance exceptions. Doubled `ll` pairs tighten by
about 30 upright / 33 italic font units, with clearance exceptions for marks
and hooks. Other vertical-left pairs retain the spacing needed by the new tail.
The same treatment covers accented `l`,
`ss05`, and `fl`/`ffl` forms; Carlito26 already retains its original advances.

`10_refine_ae_and_l_spacing.py` records this one-time follow-up. The resulting
`sources/data/lowercase-spacing.json` is used automatically by the normal
rebuild. Native VFJ and Glyphs kerning is updated as well. Exported fonts add
one kerning lookup while retaining all original positioning lookups.
`13_match_lo_spacing.py` records the one-time `lo` alignment; the spacing
configuration and normal rebuild preserve it thereafter.
`14_refine_optical_spacing.py` records the later `lc` match and restrained
`la`/`lw`/`ly` additions. Rebuild and export Glyphs normally afterward.

The Fira Sans lowercase-l/capital-I review led to a bowl-allowance pass,
followed by a per-shape rhythm refinement. The first pass was too generous
for upright `lo` and `ly`. The current pass compares both multiscale ink
interaction (`lX / IX`) and the gap halfway up the x-height, using Fira as a
reference for shape relationships while retaining Lato's widths and incoming
spacing (`ol`, for example). It does not force every pair to a Fira target.

Changes from the first allowance pass, in native 2,000 UPM units:

| Style / pair | Hairline | Regular | Bold | Black |
| --- | ---: | ---: | ---: | ---: |
| Upright la | -30 | -55 | -10 | -5 |
| Upright lc/le/lo | -45 | -55 | -25 | -10 |
| Upright ld/lq | -5 | -20 | +30 | +45 |
| Upright ls | -10 | -50 | 0 | 0 |
| Upright lv | -50 | -60 | -25 | -5 |
| Upright lw | -35 | -40 | -5 | 0 |
| Upright lx | 0 | -20 | 0 | 0 |
| Upright ly | -60 | -75 | -35 | -15 |
| Italic la | 0 | 0 | +20 | +30 |
| Italic lc/le/lo | -20 | -25 | -5 | 0 |
| Italic ld/lq | 0 | 0 | +35 | +50 |
| Italic ls | 0 | -15 | 0 | 0 |
| Italic lv | -25 | -25 | +15 | +25 |
| Italic lw | -10 | -15 | +20 | +30 |
| Italic lx | -25 | -35 | -12 | 0 |
| Italic ly | 0 | 0 | +20 | +30 |

Intervening weights interpolate between these four Glyphs master positions.
Before the smaller-bowl edit below, Regular upright `la/lc/le/lo/lw/ly`
kerned at -46/-75/-74/-75/-61/-90.
`lc` and `lo` retain the `le` outline-edge gap. The earlier +20/+8/+14
`a/w/y` preferences remain inside these totals. Related accents, ligatures
such as `ae`, and alternates follow their base, preserving clearance
exceptions. Distinct turned/reversed shapes and `lg` are left alone where
the evidence does not support the same adjustment.

That spacing-only refinement kept the allowance at or above zero. It left
vertical-left pairs, `lh/lk/ll`, capital-I pairs, `fl/ffl`, and Carlito26
unchanged, preserving all outlines, advances, and corrected hint bytes.

`26_refine_l_rhythm.py` records this one-time refinement of the VFJ sources and
spacing JSON. The current per-glyph tables are in `bowl_allowance.additions`;
`initial_budgets` documents the superseded blanket pass, and
`rhythm_refinement` records the signed changes and method.

`23_restore_l_bowl_spacing.py` records the one-time VFJ migration. Its
`--refresh-only` mode updates built TTF/OTF positioning without rebuilding
outlines or hints, refreshes the static Regular Glyphs kerning, and packages
the desktop archive. Run `11_export_editable_glyphs.py` afterward for the two
four-master editable sources. Normal outline rebuilds also use this policy.
`24_check_l_bowl_spacing.py --snapshot PATH` compares every revision pair and
all other font tables against a saved before-build, checks shaping and source
preservation, and verifies the packaged fonts. Its report records the current
font hashes separately from the earlier hint-validation reports.

The subsequent authored Regular `l` edit reduces its advance from 591.3 to
537 units and narrows and lowers the bowl. `27_propagate_smaller_l.py`
transfers those exact control-point changes across upright weights. Shared
inner/outer movement stays constant; differential movement scales with stem
thickness, preserving thin strokes. Italics use the existing `t`-derived
narrowing/shear. The change covers 35 related forms per style, including
accents, alternates, small forms and ligatures. Carlito26 keeps all advances.

The special outgoing pairs retain their preceding horizontal outline-edge
gaps, including `lc/le/lo`, `la`, `lw`, `ly`, and `ll`. Kerning compensates for
the reduced advance and bowl extent, including actual TTF/OTF conversion
rounding. Ordinary vertical-left pairs such as `lh`, `li`, and `lj` keep
their kerning and use the narrower advance. The correction and old metrics
are recorded in `lowercase-spacing.json`; the authored edit and propagation
method are in `smaller-l.json`.

After the one-time migration, `27_propagate_smaller_l.py --snapshot PATH
--build` rebuilds only these forms. `--glyphs` merges their geometry and
kerning into the editable files while preserving the authored Regular layer
and all unrelated glyph data. Use this merge mode for the current sources;
a full `11_export_editable_glyphs.py` export replaces unrelated editor data.
`08_refresh_carlito_outlines.py --only-smaller-l` updates the matching Carlito
forms. `28_check_smaller_l.py --snapshot PATH` verifies the exact authored
layer, unchanged unrelated outlines/hints/layout, special-pair gaps within
half a unit, native hint execution, and packaged fonts. Only revised `l`
instructions are regenerated; the corrected Bold `a` instructions are intact.

The later `Lato26-Upright-modified-e.glyphs` edit refines the inner curve in
all four upright `e` masters and raises the crossbar in Bold and Black.
`29_import_e_shape.py` imports those exact masters and propagates them to 54
upright forms, including accents, small/turned forms, Cyrillic `е`, `ae`, and
`oe`. The `ae` bowl joins follow the bar. Italic fonts and sources are unchanged;
advances and kerning retain their preceding values.

`sources/data/e-shape-revision.json` retains the authored layers and the
Regular/Bold intermediate layers. Hairline and Black are also updated in VFJ.
The source reader and Glyphs exporter interpolate this four-master progression
for the affected forms. Regular `a` still uses its exact quadratic override;
Regular `e` now uses the authored cubic master and the normal TTF conversion.
Use `29_import_e_shape.py --build`, `08_refresh_carlito_outlines.py --only-e-shape`,
and `29_import_e_shape.py --glyphs --snapshot PATH` for repeatable exports.
`30_check_e_shape.py --snapshot PATH` checks the authored masters, related
joins, unchanged italic bytes, unrelated hints, advances, kerning, native
hint execution, and packaged fonts. The main PDF includes two focused upright
`e` pages after the spacing review.

`15_audit_optical_spacing.py --before-build PATH --reference-dir /Library/Fonts` measures every `la`-`lz`
pair at all 18 weights/styles against the saved build before that adjustment.
It uses unhinted masks at approximately 256 pixels per x-height. The audit uses
Gaussian blur at 6%, 12%, and 24% of x-height, measures the
overlap of the two ink fields between baseline and x-height, and normalizes
each scale to current `le` in the same font. The reported index is the
geometric mean of those three ratios. This approach is related to
[HalfKern's blurred-envelope audit](https://github.com/behdad/halfkern).
The implementation additionally requires `scipy`.

The index measures ink interaction, not an objectively optimal spacing or
reading performance. The report also measures original Lato 2.015 relative
to its own `le`, and samples horizontal contour clearance across the lower
third of the bowl. Both before/after Lato26 columns use current `le` as their
reference. It preserves all three scale ratios and checks selected Regular
pairs at double raster resolution. The 18 alphabet pages compare the previous
Lato26 build with the current one, covering all 468 pairs without fl ligatures.
Results are in `build/proofs/optical-spacing.json` and `.csv`; generated blur
images in `build/proofs/optical-blur/` are inputs to the PDF renderer.

`21_compare_fira_spacing.py` compares `la`-`lz` against the official
[Fira Sans 4.301 normal-width TTFs](https://github.com/bBoxType/FiraSans/tree/f54eeb3124c63fe9b5bcd36d09d1cd46788cd15e/Fira_Sans_4_3/Fonts/Fira_Sans_TTF_4301/Normal).
Place the reference fonts in `.cache/fira-sans-4.301/`, or supply
`--reference-dir PATH`. Weights match by nominal class: Lato26 Hairline/Thin
use Fira Thin/UltraLight, and Heavy/Black use Fira ExtraBold/Heavy.
The audit checks shaping, measures normalized kerning and horizontal edge
gaps, and applies the same three-scale blur heuristic to explicitly unhinted
coverage at equal x-height. It writes 936 measurements and resolution checks
to `build/proofs/fira-spacing-comparison.json` and `.csv`, plus the 20-page
vector comparison `output/pdf/Lato26-FiraSans-Spacing.pdf`. This is an audit;
it does not change the fonts. Use `--reuse-report` to redraw the PDF from
verified, unchanged font files without repeating the raster audit.

`22_compare_capital_i_spacing.py` extends that comparison to `Ia`-`Iz`, reusing
the lowercase measurements only when all font hashes still match. It writes
`fira-capital-i-comparison.json` and `.csv` alongside the earlier report, plus
`output/pdf/Lato26-FiraSans-Capital-I-Spacing.pdf`, with both left letters shown
side by side. Capital-I blur ratios use `Ie` as their own reference and also
record a common `le` reference. Direct overlap summation avoids FFT cancellation
when light capital-I pairs have very little interaction at the narrowest blur
scale. A zero overlap is allowed when the truncated blur fields do not meet.

`25_compare_rhythm.py --before-snapshot PATH` adds the `ly/Iy` and
`IoloIolo` comparison, including mid-height gaps and common-reference ink
interaction. With a snapshot containing the preceding report and fonts, its
three-page PDF also shows the direct before/after change and the current
`lj/Ij`, `li/Ii`, and `lh/Ih` relationships. It verifies the saved
font hashes and checks pair gaps against the shaped whole string.

### Editable Glyphs sources and proofs

`sources/Lato26-Upright.glyphs` and `sources/Lato26-Italic.glyphs` contain the
active collection in Glyphs 3 format: 3,055 upright / 3,053 italic glyphs and
nine instances per file.
Hairline and Black masters retain the source outlines; Regular and Bold
masters encode the kerning curve and the separate `e` edits. Components, anchors, kerning groups,
and OpenType feature definitions remain editable. A few legacy glyphs with
incompatible source topology use their compatible exported TTF contours;
their names are recorded in each file's user data. The separate static Regular
Glyphs file retains the authored `a` quadratics and current `e` cubics.

Merge this authored revision into the editable sources with the `--glyphs`
mode described above. Use `python tools/11_export_editable_glyphs.py` only
when a full replacement export is intended. Generate the vector
proof packet with `python tools/12_render_proofs.py --baseline-dir PATH
--previous-build PATH`; the two paths refer to saved original and previous
build directories. The output is `output/pdf/Lato26-Proofs.pdf`. Glyphs are
shaped with HarfBuzz and drawn as vector outlines, preserving kerning,
ligatures, and mark placement at any zoom level. PDF generation additionally
requires `reportlab` and a HarfBuzz shared library (including the one bundled
with Pillow). Use `--format png` for optional PNG proofs at twice their
original width and height.
The PDF includes the three overview/detail pages followed by one comparison
page for each of the 18 weight/style combinations. These pages show `la`
through `lz` in original Lato and current Lato26, with PDF bookmarks by style.
When an optical audit is present, each pair also shows its current blur
index, followed by a method/results page and two before/after blur pages.
For those pages, pass the same `--previous-build` path used for the audit.

### ClearType-style screen mockup

`tools/16_render_cleartype_mockup.py` creates a labelled RGB subpixel
approximation from the current TTF files: native-pixel PNGs and a local viewer
in `output/cleartype/`, plus `output/pdf/Lato26-ClearType-Mockup.pdf`.
It covers all nine upright/italic weights and display scales of 100%, 125%,
150%, and 200%, with enlarged RGB/grayscale comparisons.

This uses HarfBuzz positioning, FreeType rasterization with embedded native
hint instructions, a five-tap RGB filter, and blending gamma 1.8. It is not
a Windows 11 or Microsoft DirectWrite capture. The rasterizer does not apply
its own auto-hinter; it executes the desktop fonts' embedded hint bytecode.
Inspect native-pixel PNGs for screen judgments; PDF scaling resamples pixels.
Renderer settings, font hashes and validation are saved beside the images.
Pass `--before-hint-build PATH` with the previous Lato26 build to append a
before/after hinting comparison. `--bowl-before-build PATH` optionally supplies
the earlier build exhibiting the thick Bold `a`. Add `--reference-dir PATH
--original-hint-build PATH` for a three-way comparison with released Lato
2.015 and the repository's original 3.100 hint set.
`--join-before-build PATH` adds a focused 12-24 px join comparison and all
34 affected Bold forms at 14 and 16 px.

### Desktop TrueType hinting

Lato26 and Carlito26 use **ttfautohint 1.3**, the engine used by released Lato
2.015. The repository's 3.100 hinting is replaced throughout the desktop TTFs.
The chosen recipe reproduces every original glyph program and the `fpgm`,
`prep`, and `cvt ` tables byte-for-byte in all 18 user-supplied 2.015 fonts.
Current Lato26 instructions are regenerated for its own point topology,
including our revised glyphs; outline differences can still affect pixels.

Install the pinned macOS executable (Intel, runs under Rosetta on Apple
Silicon) into the ignored local cache with:

```sh
python tools/install_ttfautohint_13.py
python tools/17_hint_desktop_fonts.py
```

The installer verifies SHA-256 hashes of the official FreeType/SourceForge
[1.3 release archive](https://sourceforge.net/projects/freetype/files/ttfautohint/1.3/)
and executable. Use `--archive PATH` for an existing download. On other
platforms, build the same release and set `TTFAUTOHINT_13` to the executable;
the build refuses other engine versions. The executable is not bundled in
the desktop font ZIP. See the upstream release for the engine's licensing.

The recipe uses strong stem widths in grayscale, GDI ClearType and DirectWrite
modes (`-w gGD`), x-height increase limit 14 (`-x 14`), Windows clipping zones
(`-W`), and Latin fallback (`-f latn`). Hints are optimized for 8-50 ppem and
enabled through 200 ppem. The engine preserves naming (`-n`) and records its
settings in a `TTFA` table (`-t`). Outline coordinates, components, advance
widths, kerning, shaping and names are preserved by the hinting pass.

Bold upright `a` excludes overlapping contour cut edges and the short bowl
closure from stem detection. This prevents its bowl top from becoming about
2.23 pixels thick at 16 ppem in the earlier autohint build. With the 2.015
recipe and this control, the separation is 1.30 pixels, close to the outline's
1.21 pixels. Matching accented and Cyrillic forms share the correction.
No outline points are moved by these controls. The italic single-storey `a`
outline remains unchanged; its hints now use the released 2.015 recipe too.

After autohinting, a short TrueType instruction sequence links the upper end
of the Bold `a` stem to the upper arch, retaining at least their original
16-unit overlap. It moves only the two stem-end points in the rasterized
outline when needed; the source outline, bowl thickness, curve and accent
positions stay unchanged. This closes the seam exposed by the bowl control
at small sizes: the 14 px gap of 0.95 px becomes a 0.11 px overlap, while the
bowl-top thickness remains 1.30 px. All 34 matching forms receive the link.

`tools/20_check_bold_a_joins.py --before-build PATH` compares against the
preceding disconnected-join build. It checks all 34 forms at every integer
size from 6-201 ppem, quarter-pixel sizes from 8-50 ppem, and 256 ppem in
grayscale, monochrome and LCD modes. All 32,946 cases require connected
joins and exactly unchanged hinted bowl/curve/accent coordinates. The report
is `build/proofs/bold-a-join-validation.json`; it also checks idempotence.

`tools/19_check_lato_2015_hinting.py --reference-dir /Library/Fonts` verifies
the reference recipe exactly, records 16 px vertical bounds, and checks the
Bold bowl-top separation. Its report is
`build/proofs/lato-2015-hint-validation.json`.
`tools/18_check_truetype_hints.py --before-build PATH` verifies unchanged
geometry and layout, native grayscale/LCD bytecode execution, and idempotence.
Coverage and engine settings are recorded in `build/proofs/truetype-hinting.json`.

Hinting is applied after interpolation, not to the compatible source masters.
OTF/CFF exports are unaffected by this TrueType-only pass. Glyphs instances
use `--stem-width-mode=sss` (`-a sss`), the current spelling of strong widths
in all three render modes, to avoid the newer engine's `-w gGD` warning.
Their exports use Glyphs' own engine
and do not apply our Bold bowl control or final join instructions. Use the repository build for the
pinned 2.015 recipe and shipped results. Editable source outlines are unchanged.

### Selective building

With `python3 03_build_lato_fontmake.py -h` you can check additional build options. For example, `python3 03_build_lato_fontmake.py ttf` will only build static TTFs.

### Mark attachment

In this version, dynamic mark attachment (`mark` and `mkmk` is limited to combining marks, and to Latin and Cyrillic base glyphs that don’t have precomposed marks). In FontLab, in Glyph panel, OT Glyph Definition Class for those base glyphs is set to Simple, which translates to the `otsimp` virtual tag. The marks are set as Mark, which translates to the `otmark` virtual tag. The FEA code has a portion between `#> vtags` and `#< vtags` which includes the virtual tags as FEA classes. Then the portion:

```
table GDEF {
    GlyphClassDef @otsimp, @otliga, @otmark, [];
} GDEF;
```

ensures that `fontmake` only builds anchor-based mark attachment (`mark` and `mkmk` for the `@otsimp` base glyphs and `@otmark` marks).

## Changelog

### Version 3.100.dev2 (2020-08-16)

- The [`sources`](sources) are now [FontLab 7](https://www.fontlab.com/7) VFJ, with 2 masters (Hairline, Black) in 2 fonts (Upright, Italic)
- Added a few more `.ss05` glyphs
- Redesigned the `_i` ligatures to have a dot, and moved them to `liga`
- Added the `ss06` feature for Serbian localized glyphs
- Renamed glyphs in source to use `.glyphs`-compatible names
- Added scripted build system (see Building)
- Improved anchors for `mark` & `mkmk`, limiting them to non-accented Latin and Cyrillic base letters, and to combining marks.
- Added `table STAT` definition in FEA — note: for this reason, the features don’t compile in FontLab.
- **TODO** Automate `STAT` building either via statmake or FEA. Right now it’s done via FEA but it’s stupid since the statics get the STAT for the VF. Perhaps just remove STAT from the statics in a postprocessing step

### Version 3.002.dev1 (2019-10-14)

- Added the sources in FontLab VI VFC & VFJ format (`20-VFC-2M-designsource` folder has 2 masters, `30-VFC-3M-production` has 3 masters, needed for VF export)
- Renamed glyphs for more consistent experience
- Updated OpenType feature definitions
- Moved ligatures that involve `i` and `j` to `dlig` feature (by popular demand)
- Added accented “legible” `.ss05` forms

### Version 3.001.dev0 (2018-09-28)

- **Note: This is work in progress**
- Published the sources in FontLab Studio 5 VFB format
- Updated the design of the `Bsmall` glyph in Italic
- Updated the design of the `fourfifths` glyph
- Updated the design of the `aturned` glyph in Upright
- Updated the design of the `Ismall` glyph
- Added the glyphs `I.ss05` and `l.ss05` and the associated `ss05` “legible forms” feature

### Version 2.015 (2015-08-06)

- Initial implementation of mark positioning (should work for most glyphs)
- Autohinted using ttfautohint 1.3.

### Version 2.015 (2015-08-06)

- Initial implementation of mark positioning (should work for most glyphs)
- Autohinted using ttfautohint 1.3.

### Version 2.010 (2014-09-01)

- Improved some contour bugs and diacritics positioning.
- Improved outline quality.
- Revised OTL features so that they work in browsers (ot-sanitise).
- Autohinted using ttfautohint 1.1.
- Interpolated the Medium weight differently so it provides more visual - difference from Regular.

### Version 2.007 (2014-02-27)

- Greatly expanded character set, revised metrics, four additional weights.

### Version 1.104 (2011-11-08)

- Merged the distribution again
- Autohinted with updated ttfautohint 0.4 (which no longer causes Adobe and iOS problems) except the Hai and Lig weights which are hinted in FLS 5.1.

### Version 1.102 (2011-10-28)

- Added OpenType Layout features
- Split between desktop and web versions
- Desktop version: all weights autohinted with FontLab Studio
- Web version autohinted with ttfautohint 0.4 except the Hai and Lig weights

### Version 1.101 (2011-09-30)

- Fixed OS/2 table Unicode and codepage entries

### Version 1.100 (2011-09-12)

- Added Polish diacritics to the character set
- Weights Hai and Lig autohinted with FontLab Studio
- Other weights autohinted with ttfautohint 0.3

### Version 1.011 (2010-12-29)

- Added the soft hyphen glyph

### Version 1.010 (2010-12-13)

- Initial version released under SIL Open Font License
- Western character set
