import json
from datetime import date, datetime
from pathlib import Path

import pytest

from ingest.parse import block_to_records, candles_to_rows, group_by_date

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


def test_block_to_records_joins_columns_and_data():
    payload = load_fixture("iss_securities_page.json")

    records = block_to_records(payload, "securities")

    assert len(records) == 2
    assert records[0] == {
        "SECID": "SBER",
        "BOARDID": "TQBR",
        "SHORTNAME": "Сбербанк",
        "LOTSIZE": 10,
    }


def test_block_to_records_fails_on_missing_block():
    with pytest.raises(ValueError, match="candles"):
        block_to_records({"securities": {"columns": [], "data": []}}, "candles")


def test_candles_to_rows_converts_types():
    records = block_to_records(load_fixture("iss_candles_page.json"), "candles")

    rows = candles_to_rows("SBER", 1, records)

    assert rows[0]["secid"] == "SBER"
    assert rows[0]["interval"] == 1
    assert rows[0]["begin"] == datetime(2026, 9, 1, 9, 59)
    assert rows[0]["end"] == datetime(2026, 9, 1, 9, 59, 59)
    assert rows[0]["open"] == pytest.approx(309.5)
    assert rows[0]["volume"] == 50800
    assert isinstance(rows[0]["volume"], int)


def test_candles_to_rows_keeps_nulls():
    records = [
        {
            "open": None,
            "close": 1.0,
            "high": 1.0,
            "low": 1.0,
            "value": None,
            "volume": None,
            "begin": "2026-09-01 10:00:00",
            "end": "2026-09-01 10:00:59",
        }
    ]

    row = candles_to_rows("SBER", 1, records)[0]

    assert row["open"] is None
    assert row["volume"] is None


def test_group_by_date_splits_days():
    records = block_to_records(load_fixture("iss_candles_page.json"), "candles")
    rows = candles_to_rows("SBER", 1, records)

    grouped = group_by_date(rows)

    assert sorted(grouped) == [date(2026, 9, 1), date(2026, 9, 2)]
    assert len(grouped[date(2026, 9, 1)]) == 2
    assert len(grouped[date(2026, 9, 2)]) == 1
