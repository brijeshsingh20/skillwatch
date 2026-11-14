"""Parse and validate an attendance CSV. Pure: no database, no framework."""
import csv
import io
from dataclasses import dataclass
from datetime import date

MAX_ROWS = 1000
MAX_COUNT = 5000


@dataclass(frozen=True)
class ParsedRow:
    batch_id: int
    session_date: date
    claimed_count: int


@dataclass(frozen=True)
class RowError:
    row: int
    error: str


def parse_claims_csv(text: str, batches: dict[int, str]) -> tuple[list[ParsedRow], list[RowError]]:
    """Columns: session_date, claimed_count, batch (id or name; optional when the centre has one batch)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    missing = {"session_date", "claimed_count"} - fields
    if missing:
        return [], [RowError(1, f"Missing required column(s): {', '.join(sorted(missing))}")]
    if "batch" not in fields and len(batches) != 1:
        return [], [RowError(1, "Column 'batch' is required when the centre has more than one batch")]

    by_name = {name.strip().lower(): bid for bid, name in batches.items()}
    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    seen: set[tuple[int, date]] = set()
    for line_no, raw in enumerate(reader, start=2):
        if line_no - 1 > MAX_ROWS:
            errors.append(RowError(line_no, f"Too many rows (max {MAX_ROWS}); remaining rows ignored"))
            break
        rec = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(rec.values()):
            continue
        try:
            session = date.fromisoformat(rec["session_date"])
        except ValueError:
            errors.append(RowError(line_no, f"Invalid session_date '{rec['session_date']}' (use YYYY-MM-DD)"))
            continue
        try:
            count = int(rec["claimed_count"])
        except ValueError:
            errors.append(RowError(line_no, f"claimed_count '{rec['claimed_count']}' is not a whole number"))
            continue
        if not 0 <= count <= MAX_COUNT:
            errors.append(RowError(line_no, f"claimed_count must be between 0 and {MAX_COUNT}"))
            continue
        label = rec.get("batch", "")
        if "batch" not in fields:
            batch_id = next(iter(batches))
        elif label.isdigit() and int(label) in batches:
            batch_id = int(label)
        elif label.lower() in by_name:
            batch_id = by_name[label.lower()]
        else:
            errors.append(RowError(line_no, f"Unknown batch '{label}'"))
            continue
        if (batch_id, session) in seen:
            errors.append(RowError(line_no, "Duplicate batch and date in this file; row skipped"))
            continue
        seen.add((batch_id, session))
        rows.append(ParsedRow(batch_id, session, count))
    return rows, errors
