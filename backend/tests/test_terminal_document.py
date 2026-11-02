from app.services.terminal_document import seeded_records


def line(identifier, y):
    return {"id": identifier, "bbox": [50, y - 5, 100, y + 5], "display_text": identifier, "revision": 0}


def test_includes_every_ocr_result_even_when_terminal_count_is_smaller():
    items = [line("A", 100), line("B", 105), line("C", 110)]
    records = seeded_records({"terminal_points": [{"id": "p", "x": 10, "y": 100}]}, items)
    assert len(records) == 3
    assert {r["sourceResultId"] for r in records} == {"A", "B", "C"}
    assert sum(r["terminalPointId"] is None for r in records) == 2


def test_no_terminal_points_still_shows_all_recognized_identifiers():
    records = seeded_records({"terminal_points": []}, [line("A", 100), line("B", 200)])
    assert len(records) == 2
    assert all(r["terminalPointId"] is None for r in records)


def test_keeps_empty_terminal_row_and_legacy_manual_record_without_duplicate():
    legacy = {**line("manual", 100), "attributes": {"terminal_point_id": "p"}}
    records = seeded_records({"terminal_points": [{"id": "p", "x": 10, "y": 100}, {"id": "q", "x": 10, "y": 300}]}, [legacy, line("OCR", 105)])
    assert {r["id"] for r in records} == {"terminal:p", "terminal:q", "ocr:OCR"}

def test_confirmed_point_number_wins_over_automatic_ocr_sequence():
    page={'terminal_points':[{'id':'p','x':10,'y':100,'terminal_number':'Z'},{'id':'q','x':10,'y':200,'terminal_number':'AA'}]}
    item={**line('ocr',100),'terminal_number':'1','table_revision':0}
    assert [r['terminalNumber'] for r in seeded_records(page,[item])]==['Z','AA']
    manual={**item,'terminal_number':'USER-A','table_revision':1}
    assert seeded_records(page,[manual])[0]['terminalNumber']=='USER-A'
