from datetime import date

from backend.app.services.attendance_csv import parse_claims_csv

BATCHES = {1: "Morning Batch", 2: "Evening Batch"}


def test_valid_rows_by_name_and_id():
    text = "session_date,claimed_count,batch\n2026-11-02,20,Morning Batch\n2026-11-02,15,2\n"
    rows, errors = parse_claims_csv(text, BATCHES)
    assert errors == []
    assert [(r.batch_id, r.session_date, r.claimed_count) for r in rows] == [(1, date(2026, 11, 2), 20), (2, date(2026, 11, 2), 15)]


def test_bad_rows_are_reported_not_fatal():
    text = ("session_date,claimed_count,batch\n"
            "2026-11-03,abc,Morning Batch\n"      # bad count
            "03/11/2026,10,Morning Batch\n"        # bad date
            "2026-11-03,10,Night Batch\n"          # unknown batch
            "2026-11-03,-4,Morning Batch\n"        # negative
            "2026-11-04,12,Morning Batch\n"        # good
            "2026-11-04,13,Morning Batch\n")       # duplicate
    rows, errors = parse_claims_csv(text, BATCHES)
    assert len(rows) == 1 and rows[0].claimed_count == 12
    assert [e.row for e in errors] == [2, 3, 4, 5, 7]


def test_missing_columns_and_ambiguous_batch():
    assert parse_claims_csv("date,count\n1,2\n", BATCHES)[1][0].row == 1
    _, errors = parse_claims_csv("session_date,claimed_count\n2026-11-02,5\n", BATCHES)
    assert "batch" in errors[0].error


def test_batch_column_optional_for_single_batch_centre():
    rows, errors = parse_claims_csv("session_date,claimed_count\n2026-11-02,5\n", {7: "Only"})
    assert errors == [] and rows[0].batch_id == 7


def test_bom_blank_lines_and_headers_with_spaces():
    text = "\ufeff Session_Date , Claimed_Count ,Batch\n\n2026-11-02,9,Morning Batch\n"
    rows, errors = parse_claims_csv(text, BATCHES)
    assert errors == [] and rows[0].claimed_count == 9
