
def bind_results(items, snapshot):
    """Bind only to confirmed wire locations; preserve unmatched OCR text."""
    from app.terminal_pair.numbering import ordered_point_ids
    ids = ordered_point_ids(snapshot['points'], snapshot['start_point_id'], snapshot.get('end_point_id'))
    for item in items:
        x1,y1,x2,y2 = item['bbox']
        x,y = (x1+x2)/2,(y1+y2)/2
        candidates = [b for b in snapshot['bindings'] if not b.get('empty') and b['bbox'][0] <= x <= b['bbox'][2] and b['bbox'][1] <= y <= b['bbox'][3]]
        # Final crops use the confirmed point ID as their ROI ID. Prefer that
        # provenance when neighboring candidate boxes overlap.
        roi_id = item['attributes'].get('roi_id')
        explicit = [b for b in candidates if b['point_id'] == roi_id]
        if explicit:
            candidates = explicit
        item['attributes']['workflow_confirmed'] = True
        if len(candidates) == 1:
            point_id = candidates[0]['point_id']
            item['attributes']['terminal_point_id'] = point_id
            from app.terminal_pair.numbering import terminal_label
            item['terminal_number'] = terminal_label(snapshot['ordering'], ids.index(point_id))
        else:
            item['attributes']['binding_review_required'] = True
        naming = snapshot['ordering']['naming']
        if naming == 'numeric' and not item['text'].isdigit() or naming == 'prefix' and not item['text'].startswith(snapshot['ordering'].get('prefix','')):
            item['attributes']['naming_review_required'] = True

    # Several OCR fragments in one confirmed location need review rather than
    # silently retaining only the last text fragment.
    counts = {}
    for item in items:
        key = item['attributes'].get('terminal_point_id')
        if key: counts[key] = counts.get(key, 0) + 1
    for item in items:
        key = item['attributes'].get('terminal_point_id')
        if key and counts[key] > 1:
            item['attributes'].pop('terminal_point_id')
            item.pop('terminal_number', None)
            item['attributes']['binding_review_required'] = True
