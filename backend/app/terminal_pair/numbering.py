"""Terminal hole numbering, independent of wire-text naming rules."""
import re

MAX_ORDINAL = 2**53 - 1


def alphabet_index(text):
    if not isinstance(text, str) or not re.fullmatch(r'[A-Za-z]{1,10}', text):
        raise ValueError('起始字母须为 1–10 位英文字母，例如 A、Z、AA')
    value = 0
    for char in text.upper(): value = value * 26 + ord(char) - 64
    return value


def validate_numbering(rule, count=1):
    prefix = rule.get('number_prefix', '')
    if not isinstance(prefix, str) or len(prefix) > 40 or any(ord(c)<32 or ord(c)==127 for c in prefix):
        raise ValueError('端子孔编号前缀须为不超过 40 字符的单行文本')
    mode = rule.get('numbering_mode', 'numeric')
    if mode == 'numeric':
        start = rule.get('start')
        if isinstance(start, bool) or not isinstance(start, int) or start < 0 or start + max(0,count-1) > MAX_ORDINAL:
            raise ValueError('请填写有效的非负整数起始编号')
    elif mode == 'alpha':
        alphabet_index(rule.get('letter_start', 'A'))
        if rule.get('letter_case', 'upper') not in ('upper','lower'): raise ValueError('无效的字母大小写')
    else: raise ValueError('无效的端子编号方式')


def terminal_label(rule, offset):
    validate_numbering(rule, offset+1)
    if rule.get('numbering_mode', 'numeric') == 'numeric': return rule.get('number_prefix', '') + str(rule['start'] + offset)
    value = alphabet_index(rule.get('letter_start', 'A')) + offset
    text = ''
    while value:
        value, remainder = divmod(value-1,26)
        text = chr(65+remainder) + text
    return rule.get('number_prefix', '') + (text.lower() if rule.get('letter_case','upper') == 'lower' else text)

def ordered_point_ids(points, start_point_id, end_point_id=None):
    """Number the inclusive physical span in the direction selected by the user."""
    ids = [p['id'] for p in sorted(points, key=lambda p: (p['y'], p['x'], str(p['id'])))]
    if start_point_id not in ids:
        return []
    # Old workflow snapshots had no end point and numbered to the bottom.
    if end_point_id is None:
        end_point_id = ids[-1]
    if end_point_id not in ids:
        return []
    start, end = ids.index(start_point_id), ids.index(end_point_id)
    return ids[start:end + 1] if start <= end else list(reversed(ids[end:start + 1]))


def page_with_workflow_numbers(page, snapshot):
    """Recover confirmed labels for pages produced before labels were persisted."""
    if not snapshot or not snapshot.get('ordering') or not page.get('terminal_points'):
        return page
    ids = ordered_point_ids(snapshot.get('points', []), snapshot.get('start_point_id'), snapshot.get('end_point_id'))
    if not ids: return page
    labels = {point_id: terminal_label(snapshot['ordering'], index) for index, point_id in enumerate(ids)}
    return {**page, 'terminal_points': [{**p, **({'terminal_number': labels[p['id']]} if p['id'] in labels else {})} for p in page['terminal_points']]}
