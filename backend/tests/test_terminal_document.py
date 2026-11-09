from app.services.terminal_document import _manual_link_records, is_terminal_marker, seeded_records
from app.terminal_pair.document_records import reconcile_matches
from app.terminal_pair.numbering import ordered_point_ids, page_with_workflow_numbers


def line(identifier, y):
    return {"id": identifier, "bbox": [50, y - 5, 100, y + 5], "display_text": identifier, "revision": 0}


def test_includes_every_ocr_result_even_when_terminal_count_is_smaller():
    items = [line("A", 100), line("B", 105), line("C", 110)]
    records = seeded_records({"terminal_points": [{"id": "p", "x": 10, "y": 100}]}, items)
    assert len(records) == 3
    assert records[0]["sourceResultId"] == "A"
    assert [r["sourceResultId"] for r in records if r["terminalPointId"] is None] == ["B", "C"]


def test_no_terminal_points_still_shows_all_recognized_identifiers():
    records = seeded_records({"terminal_points": []}, [line("A", 100), line("B", 200)])
    assert len(records) == 2
    assert all(r["terminalPointId"] is None for r in records)


def test_keeps_empty_terminal_row_and_legacy_manual_record_without_duplicate():
    legacy = {**line("manual", 100), "attributes": {"terminal_point_id": "p"}}
    records = seeded_records({"terminal_points": [{"id": "p", "x": 10, "y": 100}, {"id": "q", "x": 10, "y": 300}]}, [legacy, line("OCR", 105)])
    assert {r["id"] for r in records} == {"terminal:p", "terminal:q"}
    assert [r["sourceResultId"] for r in records] == ["manual", "OCR"]

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
    assert {row['id'] for row in records} == {'terminal:p'}
    assert records[0]['sourceResultId'] == 'wire'
    assert not is_terminal_marker(bound)
    assert is_terminal_marker(marker)


def test_initial_pairs_survive_refresh_and_manual_reassignment():
    page = {'terminal_points': [{'id': 'p', 'x': 10, 'y': 100}, {'id': 'q', 'x': 10, 'y': 200}]}
    items = [line('A', 100), line('B', 200), line('C', 300)]
    records = seeded_records(page, items)
    moved = _manual_link_records(records, items, {'q': 'A'})
    assert reconcile_matches(moved, seeded_records(page, items), items, {'p', 'q'}) is False
    assert [r['sourceResultId'] for r in moved] == [None, 'A', 'B', 'C']
    # A newly detected line stays in the independent tail after pairing was saved.
    fresh = items + [line('new', 50)]
    assert reconcile_matches(moved, seeded_records(page, fresh), fresh, {'p', 'q'}) is True
    assert [r['sourceResultId'] for r in moved[:2]] == [None, 'A']
    assert [r['sourceResultId'] for r in moved[2:]] == ['new', 'B', 'C']


def test_numbering_runs_from_lower_start_up_to_upper_end():
    points = [{'id': str(i), 'x': 10, 'y': i * 100} for i in range(1, 5)]
    snapshot = {'points': points, 'start_point_id': '4', 'end_point_id': '2', 'ordering': {'start': 7}}
    assert ordered_point_ids(points, '4', '2') == ['4', '3', '2']
    page = page_with_workflow_numbers({'terminal_points': points}, snapshot)
    assert {p['id']: p.get('terminal_number') for p in page['terminal_points']} == {
        '1': None, '2': '9', '3': '8', '4': '7'}
