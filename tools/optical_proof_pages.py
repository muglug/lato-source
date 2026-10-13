"""Append the optical-spacing method and before/after blur comparisons."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ['Hairline','Thin','Light','Regular','Medium','Semibold','Bold','Heavy','Black']


def append_optical_proofs(document, font, before_build, report):
    rows={(r['style'],r['weight'],r['pair']):r for r in report['rows']}
    arial='/System/Library/Fonts/Supplemental/Arial.ttf'
    title=font(arial,32);label=font(arial,21);text=font(arial,18);small=font(arial,16)
    page=document.page(1200,1553)
    document.canvas.bookmarkPage('optical-method')
    document.canvas.addOutlineEntry('Optical spacing measurements','optical-method',level=0)
    page.text((54,40),'Lato26 · measurable spacing review',font=title,fill='#151d29')
    lines=[
        'Blur each glyph at 6%, 12%, and 24% of x-height, keeping its actual kerned position.',
        'Measure the overlap of the two blurred ink fields from the baseline to x-height.',
        'At each scale, divide by the overlap of le in the same font. Average the three ratios',
        'geometrically: le = 1.00; a higher index means stronger interaction between the ink fields.',
        'Use the index as an ink-interaction diagnostic; different shapes need not have equal values.',
        'la and lc show stronger interaction than le. Regular lw/ly are already below le under',
        'this model; their small additions follow the requested rhythm, not an automatic optimum.',
    ]
    for i,line in enumerate(lines):page.text((54,100+i*32),line,font=text,fill='#394354')
    density=lambda style,char:rows[style,'Regular','l'+char]['lower_right_ink_percent']
    page.text((54,322),f"Lower third, right half ink: upright a {density('Upr','a'):.0f}% / e {density('Upr','e'):.0f}%; italic a {density('Ita','a'):.0f}% / e {density('Ita','e'):.0f}%.",font=text,fill='#394354')
    page.text((54,350),'Applied: la +20 units; lw +8; ly +14. lc matches the le outline-edge gap.',font=label,fill='#151d29')
    page.text((54,386),'2,000 units/em. Additions: 1.0%, 0.4%, 0.7% of an em; constant across weights.',font=text,fill='#69707a')
    page.text((54,420),'Related approach: HalfKern - github.com/behdad/halfkern',font=small,fill='#69707a')
    document.canvas.linkURL(report['inspiration_url'],(54,1553-444,670,1553-420),relative=1)
    maximum=max(r['relative_difference'] for r in report['resolution_checks'])*100
    page.text((54,450),f'Regular resolution check: doubling the raster size changes the sampled indices by at most {maximum:.1f}%.',font=small,fill='#69707a')
    page.text((54,494),'Blur index: previous Lato26 / current Lato26',font=label,fill='#151d29')
    for x,caption in [(54,'Style'),(390,'la'),(580,'lc'),(770,'lw'),(960,'ly')]:
        page.text((x,537),caption,font=label,fill='#69707a')
    for i,(style,weight) in enumerate((s,w) for s in ('Upr','Ita') for w in WEIGHTS):
        y=574+i*43
        name=weight+(' Italic' if style=='Ita' else '')
        page.text((54,y),name,font=text,fill='#151d29')
        for x,pair in [(390,'la'),(580,'lc'),(770,'lw'),(960,'ly')]:
            row=rows[style,weight,pair]
            value=f"{row['before']['blur_index']:.2f} / {row['after']['blur_index']:.2f}"
            page.text((x,y),value,font=text,fill='#151d29')
        page.line((54,y+36,1146,y+36),fill='#e3e1dc')
    page.text((54,1428),'The a/w/y amounts are restrained design choices; the audit reports their measured effects.',font=small,fill='#69707a')
    page.text((54,1453),'Per-scale values and all 468 l/a-z measurements are saved in optical-spacing.json and .csv.',font=small,fill='#69707a')
    page.save(None)
    for style,name in [('Upr','Regular'),('Ita','Italic')]:
        rel=Path(f'Lato3{style}2M/ds-ufo/masters/Lato26-{name}.ttf')
        old=font(str(before_build/rel),80);new=font(str(ROOT/'build'/rel),80)
        page=document.page(1200,1553)
        key=f'blur-{style}'
        document.canvas.bookmarkPage(key)
        document.canvas.addOutlineEntry('Regular '+('Upright' if style=='Upr' else 'Italic')+' blur comparison',key,level=1)
        page.text((54,40),'Lato26 · outlines and blurred shapes',font=title,fill='#151d29')
        page.text((54,90),'Regular '+('Upright' if style=='Upr' else 'Italic'),font=label,fill='#151d29')
        page.text((54,128),'The blur panels use 12% of x-height. Indices combine all three blur scales.',font=text,fill='#69707a')
        for x,caption in [(100,'Before: previous Lato26'),(680,'After: current Lato26')]:
            page.text((x,182),caption,font=label,fill='#69707a')
        for i,char in enumerate('acwy'):
            row=rows[style,'Regular','l'+char];y=235+i*294
            page.text((54,y),f"l{char} · added {row['added_units']} units",font=label,fill='#151d29')
            for x,variant,proof_font in [(100,'before',old),(680,'after',new)]:
                page.text((x,y+34),'l'+char,font=proof_font,fill='#111827')
                page.text((x,y+150),f"Index {row[variant]['blur_index']:.2f}",font=text,fill='#69707a')
                page.image(ROOT/f'build/proofs/optical-blur/{style}-{char}-{variant}.png',
                           (x+180,y+24,245,220))
            page.line((54,y+271,1146,y+271),fill='#dddcd7')
        page.text((54,1479),'Reference: le = 1.00. Exact outlines stay vector; blur panels are intentionally rasterized.',font=small,fill='#69707a')
        page.save(None)
