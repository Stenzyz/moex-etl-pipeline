import csv
from pathlib import Path

SECURITIES_PATH = Path(__file__).parent.parent / "config" / "securities.csv"


def _read_securities() -> list[dict[str, str]]:
    with SECURITIES_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_securities_have_expected_columns():
    rows = _read_securities()
    assert rows, "справочник пустой"
    assert set(rows[0].keys()) == {"secid", "sector"}


def test_secids_are_unique():
    secids = [row["secid"] for row in _read_securities()]
    assert len(secids) == len(set(secids))


def test_every_security_has_sector():
    for row in _read_securities():
        assert row["secid"].strip(), "пустой secid"
        assert row["sector"].strip(), f"у {row['secid']} не указан сектор"
