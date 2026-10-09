import csv
from typing import NamedTuple


class Security(NamedTuple):
    secid: str
    sector: str


def load_securities(path: str) -> list[Security]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"Справочник бумаг пуст: {path}")

    return [Security(row["secid"].strip(), row["sector"].strip()) for row in rows]
