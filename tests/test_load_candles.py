from datetime import date

import boto3
import httpx
import pytest
import respx
from moto import mock_aws

from ingest.iss import IssClient
from ingest.load_candles import filter_known_secids, load_security, month_ranges


def test_single_month_stays_whole():
    assert month_ranges(date(2026, 3, 5), date(2026, 3, 20)) == [
        (date(2026, 3, 5), date(2026, 3, 20))
    ]


def test_splits_on_month_borders():
    assert month_ranges(date(2026, 1, 20), date(2026, 3, 2)) == [
        (date(2026, 1, 20), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 2)),
    ]


def test_crosses_new_year():
    assert month_ranges(date(2026, 12, 30), date(2027, 1, 2)) == [
        (date(2026, 12, 30), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 2)),
    ]


def test_same_day():
    assert month_ranges(date(2026, 5, 7), date(2026, 5, 7)) == [
        (date(2026, 5, 7), date(2026, 5, 7))
    ]


def test_reversed_range_fails():
    with pytest.raises(ValueError):
        month_ranges(date(2026, 5, 7), date(2026, 5, 1))


CANDLES_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR"
    "/securities/SBER/candles.json"
)
BUCKET = "test-lake"


def candles_payload(day: str, count: int) -> dict:
    return {
        "candles": {
            "columns": [
                "open",
                "close",
                "high",
                "low",
                "value",
                "volume",
                "begin",
                "end",
            ],
            "data": [
                [
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1,
                    f"{day} 10:{minute:02d}:00",
                    f"{day} 10:{minute:02d}:59",
                ]
                for minute in range(count)
            ],
        }
    }


@respx.mock
def test_load_security_writes_one_file_per_day():
    respx.get(CANDLES_URL).mock(
        side_effect=[
            httpx.Response(200, json=candles_payload("2026-09-01", 3)),
            httpx.Response(200, json=candles_payload("2026-10-01", 2)),
        ]
    )

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)

        with IssClient(delay=0) as client:
            written = load_security(
                client, s3, BUCKET, "SBER", date(2026, 9, 1), date(2026, 10, 1)
            )

        keys = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]]

    assert written == 5
    assert keys == [
        "raw/candles/interval=1/secid=SBER/date=2026-09-01.parquet",
        "raw/candles/interval=1/secid=SBER/date=2026-10-01.parquet",
    ]


SECURITIES_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
)


def board_payload(*secids: str) -> dict:
    return {
        "securities": {
            "columns": ["SECID", "BOARDID"],
            "data": [[secid, "TQBR"] for secid in secids],
        }
    }


@respx.mock
def test_filter_known_secids_drops_unknown():
    respx.get(SECURITIES_URL).mock(
        return_value=httpx.Response(200, json=board_payload("SBER", "GAZP"))
    )

    with IssClient(delay=0) as client:
        known = filter_known_secids(client, ["SBER", "ZZZZ", "GAZP"])

    assert known == ["SBER", "GAZP"]


@respx.mock
def test_filter_known_secids_fails_when_nothing_matches():
    respx.get(SECURITIES_URL).mock(
        return_value=httpx.Response(200, json=board_payload("SBER"))
    )

    with IssClient(delay=0) as client, pytest.raises(RuntimeError):
        filter_known_secids(client, ["ZZZZ"])
