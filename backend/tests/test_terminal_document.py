from app.services.terminal_document import _manual_link_records, is_terminal_marker, seeded_records


def line(identifier, y):
    return {"id": identifier, "bbox": [50, y - 5, 100, y + 5], "display_text": identifier, "revision": 0}


def test_includes_every_ocr_result_even_when_terminal_count_is_smaller():
    items = [line("A", 100), line("B", 105), line("C", 110)]
    records = seeded_records({"terminal_points": [{"id": "p", "x": 10, "y": 100}]}, items)
    assert len(records) == 4
    assert {r["sourceResultId"] for r in records} == {None, "A", "B", "C"}
    assert sum(r["terminalPointId"] is None for r in records) == 3


def test_no_terminal_points_still_shows_all_recognized_identifiers():
    records = seeded_records({"terminal_points": []}, [line("A", 100), line("B", 200)])
    assert len(records) == 2
    assert all(r["terminalPointId"] is None for r in records)


def test_keeps_empty_terminal_row_and_legacy_manual_record_without_duplicate():
    legacy = {**line("manual", 100), "attributes": {"terminal_point_id": "p"}}
    records = seeded_records({"terminal_points": [{"id": "p", "x": 10, "y": 100}, {"id": "q", "x": 10, "y": 300}]}, [legacy, line("OCR", 105)])
    assert {r["id"] for r in records} == {"terminal:p", "terminal:q", "ocr:OCR", "ocr:manual"}

def test_confirmed_point_number_is_independent_of_ocr_sequence():
    page={'terminal_points':[{'id':'p','x':10,'y':100,'terminal_number':'Z'},{'id':'q','x':10,'y':200,'terminal_number':'AA'}]}
    item={**line('ocr',100),'terminal_number':'1','table_revision':0}
    assert [r['terminalNumber'] for r in seeded_records(page,[item]) if r['terminalPointId']]==['Z','AA']
    manual={**item,'terminal_number':'USER-A','table_revision':1}
    assert seeded_records(page,[manual])[0]['terminalNumber']=='Z'


def test_manual_links_move_source_without_creating_duplicate():
    items = [line('A', 100), line('B', 200)]
    records = seeded_records({'terminal_points': [{'id': 'p', 'x': 10, 'y': 100}, {'id': 'q', 'x': 10, 'y': 200}]}, items)
    linked = _manual_link_records(records, items, {'q': 'A'})
    assert next(r for r in linked if r['terminalPointId'] == 'q')['sourceResultId'] == 'A'
    assert next(r for r in linked if r['terminalPointId'] == 'p')['sourceResultId'] is None
    assert [r['sourceResultId'] for r in linked if r['sourceResultId'] == 'A'] == ['A']
    assert next(r for r in linked if r['id'] == 'ocr:B')['sourceResultId'] == 'B'


def test_workflow_provenance_does_not_hide_actual_ocr_line():
    bound = {**line('wire', 100), 'terminal_number': '7', 'attributes': {'terminal_point_id': 'p', 'workflow_confirmed': True}}
    marker = {**line('marker', 100), 'display_text': '', 'attributes': {'terminal_point_id': 'p'}}
    records = seeded_records({'terminal_points': [{'id': 'p', 'x': 10, 'y': 100}]}, [bound, marker])
    assert {row['id'] for row in records} == {'terminal:p', 'ocr:wire'}
    assert next(row for row in records if row['id'] == 'terminal:p')['sourceResultId'] is None
    assert next(row for row in records if row['id'] == 'ocr:wire')['terminalNumber'] == ''
    assert not is_terminal_marker(bound)
    assert is_terminal_marker(marker)
