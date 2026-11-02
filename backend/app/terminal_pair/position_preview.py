"""Geometry-only candidate assignment. No OCR text is required."""
from app.utils.common import uid


def generate_preview(points, positions):
    # Deduplicate overlap between ROI crops before one-to-one matching.
    candidates = []
    for position in sorted(positions, key=lambda p: (p['bbox'][1],p['bbox'][0])):
        box = position['bbox']
        def duplicate(other):
            a=other['bbox']; intersection=max(0,min(a[2],box[2])-max(a[0],box[0]))*max(0,min(a[3],box[3])-max(a[1],box[1]))
            return intersection/max(1,min((a[2]-a[0])*(a[3]-a[1]),(box[2]-box[0])*(box[3]-box[1]))) > .8
        if not any(duplicate(c) for c in candidates): candidates.append({'id':uid(),**position})
    pitches=[b['y']-a['y'] for a,b in zip(points,points[1:]) if b['y']>a['y']]
    pitch=sorted(pitches)[len(pitches)//2] if pitches else None
    edges=[]
    for p in points:
        for c in candidates:
            x1,y1,x2,y2=c['bbox']; y=(y1+y2)/2
            distance=abs(p['y']-y)
            if distance <= max((y2-y1)/2, pitch*.6 if pitch else 30):
                edges.append((distance,abs(p['x']-(x1+x2)/2),p['id'],c['id']))
    used=set(); matched={}; by_id={c['id']:c for c in candidates}
    for _,__,point_id,candidate_id in sorted(edges):
        if point_id not in matched and candidate_id not in used:
            matched[point_id]=candidate_id; used.add(candidate_id)
    bindings=[]
    for p in points:
        c=by_id.get(matched.get(p['id']))
        bindings.append({'point_id':p['id'],'empty':False, **({'candidate_id':c['id'],'bbox':c['bbox']} if c else {'unresolved':True})})
    return candidates, bindings
