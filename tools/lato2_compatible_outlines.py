"""Harmonize released quadratic outlines without changing master silhouettes.

Matching runs retain their semantic curve/line boundaries. Different point
counts are reconciled by exact Bezier subdivision, rather than resampling the
outline as a polygon. A contour-wide subdivision handles exceptional topology;
missing contours collapse to a point. All such cases are reported for review.
"""
from fractions import Fraction
import math
import numpy as np
from scipy.optimize import linear_sum_assignment
from fontTools.misc.bezierTools import splitCubicAtT
from fontTools.pens.basePen import decomposeQuadraticSegment
from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.boundsPen import BoundsPen

def grouped(value):
    contours=[];segments=[]
    for op,pts in value:
        if op=='moveTo':start=last=pts[0];segments=[]
        elif op=='closePath':
            if last!=start:segments.append(('lineTo',[last,start]))
            result=[]
            for kind,ps in segments:
                if kind=='lineTo' and result and result[-1][0]=='lineTo':result[-1][1].extend(ps[1:])
                else:result.append((kind,list(ps)))
            if len(result)>1 and result[0][0]==result[-1][0]=='lineTo':
                result[0][1][:0]=result[-1][1][:-1];result.pop()
            if result:contours.append(result)
        else:
            assert op in ('qCurveTo','lineTo','curveTo') and pts[-1] is not None
            segments.append((op,[last]+list(pts)));last=pts[-1]
    return contours

def recording(contour):
    p=RecordingPen();p.moveTo(contour[0][1][0])
    for op,pts in contour:
        if op=='lineTo':
            for pt in pts[1:]:p.lineTo(pt)
        else:getattr(p,op)(*pts[1:])
    p.closePath();return p

def feature(contour):
    p=np.array([p for _,ps in contour for p in ps],dtype=float)
    lo=p.min(axis=0);hi=p.max(axis=0)
    # Signed area from a fine sample is used only for matching, never geometry.
    vertices=[]
    for op,pts in contour:
        for s in cubic_segments(op,pts):
            vertices.extend(evaluate(s,t) for t in np.linspace(0,1,9)[:-1])
    v=np.asarray(vertices)
    area=np.sum(v[:,0]*np.roll(v[:,1],-1)-v[:,1]*np.roll(v[:,0],-1))/2
    return np.r_[((lo+hi)/2)/2000,(hi-lo)/2000,math.copysign(1,area) if area else 0],area

def cubic_segments(op,pts):
    if op=='curveTo':
        assert len(pts)==4
        return [tuple(pts)]
    if op=='lineTo':
        return [(a,lerp(a,b,1/3),lerp(a,b,2/3),b) for a,b in zip(pts,pts[1:])]
    result=[];a=pts[0]
    for control,end in decomposeQuadraticSegment(pts[1:]):
        result.append((a,lerp(a,control,2/3),lerp(end,control,2/3),end));a=end
    return result

def lerp(a,b,t):return tuple(x+(y-x)*t for x,y in zip(a,b))

def evaluate(p,t):
    a,b,c,d=p;u=1-t
    return tuple(u*u*u*a[i]+3*u*u*t*b[i]+3*u*t*t*c[i]+t*t*t*d[i] for i in (0,1))

def section(p,a,b):
    if a<1e-10 and b>1-1e-10:return p
    stops=[]
    if a>1e-10:stops.append(a)
    if b<1-1e-10:stops.append(b)
    pieces=splitCubicAtT(*p,*stops)
    return pieces[1 if a>1e-10 else 0]

def reverse(contour):
    p=RecordingPen();recording(contour).replay(ReverseContourPen(p))
    return grouped(p.value)[0]

def align_group_order(contour,reference):
    signature=[op for op,_ in reference]
    if len(contour)!=len(reference):return None
    target=np.array([ps[0] for _,ps in reference])
    # Translation and overall width changes should not alter matching.
    scale=np.maximum(np.ptp(target,axis=0),20)
    target=(target-target.mean(axis=0))/scale
    choices=[]
    for i in range(len(contour)):
        rotated=contour[i:]+contour[:i]
        if [op for op,_ in rotated]!=signature:continue
        points=np.array([ps[0] for _,ps in rotated]);points=(points-points.mean(axis=0))/np.maximum(np.ptp(points,axis=0),20)
        choices.append((float(np.sum((points-target)**2)),i,rotated))
    return min(choices,key=lambda x:x[:2])[2] if choices else None

def align_contours(values,default=1):
    all_contours=[grouped(v) for v in values]
    count=max(map(len,all_contours),default=0)
    if not count:return all_contours,False
    reference_index=default if len(all_contours[default])==count else next(i for i,c in enumerate(all_contours) if len(c)==count)
    reference=all_contours[reference_index]
    features=np.array([feature(c)[0] for c in reference])
    result=[];ghosts=False
    for contours in all_contours:
        actual=np.array([feature(c)[0] for c in contours])
        aligned=[None]*count
        if len(contours):
            cost=np.sum((features[:,None,:4]-actual[None,:,:4])**2,axis=2)
            cost+=10*(features[:,None,4]!=actual[None,:,4])
            rows,cols=linear_sum_assignment(cost)
            for row,col in zip(rows,cols):
                aligned[row]=contours[col]
                if features[row,4]!=actual[col,4]:aligned[row]=reverse(aligned[row])
        for i,c in enumerate(aligned):
            if c is None:
                ghosts=True
                center=tuple(features[i,:2]*2000)
                # A collapsed contour must stay inside the existing silhouette
                # bounds, otherwise it changes xMin/LSB despite carrying no ink.
                bounds=BoundsPen(None)
                for actual_contour in contours:recording(actual_contour).replay(bounds)
                if bounds.bounds:
                    x0,y0,x1,y1=bounds.bounds
                    center=(min(x1,max(x0,center[0])),min(y1,max(y0,center[1])))
                aligned[i]=[(op,[center]*len(ps)) for op,ps in reference[i]]
        result.append(aligned)
    return result,ghosts

def uniform_groups(groups,outs):
    """Split each same-role run on the union of its exact rational knots."""
    op=groups[0][0]
    assert all(g[0]==op for g in groups)
    segments=[cubic_segments(*g) for g in groups]
    knots=sorted({Fraction(k,len(ss)) for ss in segments for k in range(len(ss)+1)})
    for out,ss in zip(outs,segments):
        n=len(ss)
        for a,b in zip(knots,knots[1:]):
            middle=(a+b)/2;idx=min(n-1,int(middle*n))
            sub=section(ss[idx],max(0,float(a*n-idx)),min(1,float(b*n-idx)))
            if op=='lineTo':out.lineTo(sub[-1])
            else:out.curveTo(*sub[1:])

def curve_wide(contours,outs):
    """Exact fallback: use a common progression around every contour."""
    paths=[];lengths=[]
    # Stable geometric start: leftmost endpoint, then highest endpoint.
    for c in contours:
        ss=[s for op,ps in c for s in cubic_segments(op,ps)]
        idx=min(range(len(ss)),key=lambda i:(round(ss[i][0][0],3),-round(ss[i][0][1],3)))
        ss=ss[idx:]+ss[:idx];paths.append(ss)
        lens=[]
        for s in ss:
            points=np.array([evaluate(s,t) for t in np.linspace(0,1,17)])
            lens.append(max(float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum()),1e-7))
        cum=np.r_[0,np.cumsum(lens)];cum/=cum[-1];cum[-1]=1
        lengths.append(cum)
    knots=sorted({float(v) for cum in lengths for v in cum})
    for out,ss,cum in zip(outs,paths,lengths):
        out.moveTo(ss[0][0])
        for a,b in zip(knots,knots[1:]):
            if b-a<1e-12:continue
            idx=min(len(ss)-1,int(np.searchsorted(cum,(a+b)/2,side='right')-1))
            a=max(0,min(1,(a-cum[idx])/(cum[idx+1]-cum[idx])))
            b=max(0,min(1,(b-cum[idx])/(cum[idx+1]-cum[idx])))
            sub=section(ss[idx],a,b);out.curveTo(*sub[1:])
        out.closePath()

def compatible(values,default=1):
    contours,ghosts=align_contours(values,default)
    outs=[RecordingPen() for _ in values];fallbacks=0
    if not contours:return outs,{'fallback_contours':0,'ghost_contours':False}
    for ci in range(len(contours[0])):
        cs=[v[ci] for v in contours]
        ref=cs[default]
        aligned=[align_group_order(c,ref) for c in cs]
        if all(c is not None for c in aligned):
            for out,c in zip(outs,aligned):out.moveTo(c[0][1][0])
            for gi in range(len(ref)):uniform_groups([c[gi] for c in aligned],outs)
            for out in outs:out.closePath()
        else:
            fallbacks+=1;curve_wide(cs,outs)
    sig=lambda r:[(op,len(pts)) for op,pts in r.value]
    assert all(sig(r)==sig(outs[0]) for r in outs)
    return outs,{'fallback_contours':fallbacks,'ghost_contours':ghosts}

def font_recordings(fonts,name):
    result=[]
    for font in fonts:
        gs=font.getGlyphSet();p=DecomposingRecordingPen(gs);gs[name].draw(p);result.append(p.value)
    return result
