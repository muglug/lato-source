"""Append the optical-spacing method and before/after blur comparisons."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ['Hairline','Thin','Light','Regular','Medium','Semibold','Bold','Heavy','Black']


def append_optical_proofs(document, font, before_build, report):
    rows={(r['style'],r['weight'],r['pair']):r for r in report['rows']}
    reshaped=any(r.get('left_outline_changed',r.get('outline_changed')) for r in report['rows'])
    e_reshaped=any(r.get('e_outline_changed') for r in report['rows'])
    arial='/System/Library/Fonts/Supplemental/Arial.ttf'
    title=font(arial,32);label=font(arial,21);text=font(arial,18);small=font(arial,16)
    page=document.page(1200,1553)
    document.canvas.bookmarkPage('optical-method')
    document.canvas.addOutlineEntry('Optical spacing measurements','optical-method',level=0)
    page.text((54,40),'Lato26 · measurable spacing review',font=title,fill='#151d29')
    lines=[
        'Blur each glyph at 6%, 12%, and 24% of x-height, keeping its actual kerned position.',
        'Measure the overlap of the two blurred ink fields from the baseline to x-height.',
        'At each scale, divide by current le overlap. Average the three ratios',
        'geometrically: le = 1.00; a higher index means stronger interaction between the ink fields.',
        'Use the index as an ink-interaction diagnostic; different shapes need not have equal values.',
        ('The e shape changes; l outlines, advances and kerning retain their preceding values.' if e_reshaped and not reshaped else
         'Smaller l: preserve special-pair edge gaps; ordinary pairs follow the narrower advance.' if reshaped else
         'Refine bowl spacing using l/I interaction and mid-height gaps, retaining Lato advances.'),
        ('Index differences also reflect the revised le reference. Italic forms are unchanged.' if e_reshaped and not reshaped else
         'The Regular edit is propagated through upright and italic weights and related forms.' if reshaped else
         'Upright and italic use separate weight curves; keep lh, lk, ll and fl ligatures unchanged.'),
    ]
    for i,line in enumerate(lines):page.text((54,100+i*32),line,font=text,fill='#394354')
    density=lambda style,char:rows[style,'Regular','l'+char]['lower_right_ink_percent']
    page.text((54,322),f"Lower third, right half ink: upright a {density('Upr','a'):.0f}% / e {density('Upr','e'):.0f}%; italic a {density('Ita','a'):.0f}% / e {density('Ita','e'):.0f}%.",font=text,fill='#394354')
    changes=' / '.join(f"{p} {rows['Upr','Regular',p]['added_units']:+d}" for p in ('la','le','lo','ly'))
    page.text((54,350),('Regular upright kern changes: ' if reshaped else 'Regular upright changes: ')+changes+' units. lc and lo match le.',font=label,fill='#151d29')
    page.text((54,386),'2,000 units/em. Preserve the existing a +20, w +8, y +14 breathing-room preferences.',font=text,fill='#69707a')
    page.text((54,420),'Related approach: HalfKern - github.com/behdad/halfkern',font=small,fill='#69707a')
    document.canvas.linkURL(report['inspiration_url'],(54,1553-444,670,1553-420),relative=1)
    maximum=max(r['relative_difference'] for r in report['resolution_checks'])*100
    page.text((54,450),f'Regular resolution check: doubling the raster size changes the sampled indices by at most {maximum:.1f}%.',font=small,fill='#69707a')
    page.text((54,494),'Blur index: Lato 2.015 / previous Lato26 / current Lato26',font=label,fill='#151d29')
    for x,caption in [(54,'Style'),(390,'la'),(580,'lh'),(770,'lw'),(960,'ly')]:
        page.text((x,537),caption,font=label,fill='#69707a')
    for i,(style,weight) in enumerate((s,w) for s in ('Upr','Ita') for w in WEIGHTS):
        y=574+i*43
        name=weight+(' Italic' if style=='Ita' else '')
        page.text((54,y),name,font=text,fill='#151d29')
        for x,pair in [(390,'la'),(580,'lh'),(770,'lw'),(960,'ly')]:
            row=rows[style,weight,pair]
            value=f"{row['before']['blur_index']:.2f} / {row['after']['blur_index']:.2f}"
            if 'original' in row:value=f"{row['original']['blur_index']:.2f} / "+value
            page.text((x,y),value,font=small,fill='#151d29')
        page.line((54,y+36,1146,y+36),fill='#e3e1dc')
    page.text((54,1428),'Lato 2.015 uses its own le = 1; both Lato26 columns use current le = 1.',font=small,fill='#69707a')
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
        page.text((54,128),'Blur: 12% of x-height, shared scale within each row. Indices combine all three scales.',font=text,fill='#69707a')
        for x,caption in [(100,'Before: previous Lato26'),(680,'After: current Lato26')]:
            page.text((x,182),caption,font=label,fill='#69707a')
        for i,char in enumerate('acwy'):
            row=rows[style,'Regular','l'+char];y=235+i*294
            caption=(f"l{char} · advance {row['advance_change_units']:+d}u; kerning {row['added_units']:+d}u" if reshaped else
                     f"l{char} · change {row['added_units']:+d} units")
            page.text((54,y),caption,font=label,fill='#151d29')
            paths={v:ROOT/f'build/proofs/optical-blur/{style}-{char}-{v}.png' for v in ('before','after')}
            sizes={}
            for variant,path in paths.items():
                with Image.open(path) as im:sizes[variant]=im.size
            scale=min(245/max(s[0] for s in sizes.values()),220/max(s[1] for s in sizes.values()))
            for x,variant,proof_font in [(100,'before',old),(680,'after',new)]:
                page.text((x,y+34),'l'+char,font=proof_font,fill='#111827')
                page.text((x,y+150),f"Index {row[variant]['blur_index']:.2f}",font=text,fill='#69707a')
                if 'lower_bowl_clearance' in row[variant]:
                    page.text((x,y+177),f"Lower gap {row[variant]['lower_bowl_clearance']:.0f}u",font=small,fill='#69707a')
                width,height=(v*scale for v in sizes[variant])
                page.image(paths[variant],(x+180,y+24+(220-height)/2,width,height))
            page.line((54,y+271,1146,y+271),fill='#dddcd7')
        page.text((54,1479),'Reference: le = 1.00. Exact outlines stay vector; blur panels are intentionally rasterized.',font=small,fill='#69707a')
        page.save(None)
