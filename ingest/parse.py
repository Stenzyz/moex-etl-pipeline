from collections import defaultdict
from datetime import date, datetime
from typing import Any

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def block_to_records(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    """ISS отдаёт данные как columns + data, склеиваем обратно в словари."""
    if block not in payload:
        raise ValueError(f"в ответе ISS нет блока {block}: {sorted(payload)}")

    raw = payload[block]
    columns = raw["columns"]
    return [dict(zip(columns, row, strict=True)) for row in raw["data"]]


def _to_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _to_int(value: Any) -> int | None:
    # volume ISS иногда отдаёт как 1.0, поэтому через float
    return None if value is None else int(float(value))


def _to_ts(value: Any) -> datetime:
    # время московское и без таймзоны, в UTC не переводим (см. docs/scope.md)
    return datetime.strptime(value, TS_FORMAT)


def candle_to_row(secid: str, interval: int, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "secid": secid,
        "interval": interval,
        "begin": _to_ts(record["begin"]),
        "end": _to_ts(record["end"]),
        "open": _to_float(record["open"]),
        "high": _to_float(record["high"]),
        "low": _to_float(record["low"]),
        "close": _to_float(record["close"]),
        "value": _to_float(record["value"]),
        "volume": _to_int(record["volume"]),
    }


def candles_to_rows(
    secid: str, interval: int, records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [candle_to_row(secid, interval, record) for record in records]


def group_by_date(rows: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["begin"].date()].append(row)
    return dict(grouped)
