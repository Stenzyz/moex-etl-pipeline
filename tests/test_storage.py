import io
from datetime import UTC, date, datetime

import boto3
import pyarrow.parquet as pq
import pytest
from moto import mock_aws

from ingest.storage import CANDLE_SCHEMA, put_candles, raw_candles_key

BUCKET = "test-lake"
LOADED_AT = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def make_rows(count: int) -> list[dict]:
    return [
        {
            "secid": "SBER",
            "interval": 1,
            "begin": datetime(2026, 9, 1, 10, minute),
            "end": datetime(2026, 9, 1, 10, minute, 59),
            "open": 300.0,
            "high": 301.0,
            "low": 299.0,
            "close": 300.5,
            "value": 1000.0,
            "volume": 10,
        }
        for minute in range(count)
    ]


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_key_layout():
    key = raw_candles_key(1, "SBER", date(2026, 9, 1))

    assert key == "raw/candles/interval=1/secid=SBER/date=2026-09-01.parquet"


def test_put_candles_writes_readable_parquet(s3):
    key = raw_candles_key(1, "SBER", date(2026, 9, 1))

    put_candles(s3, BUCKET, key, make_rows(3), loaded_at=LOADED_AT)

    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    table = pq.read_table(io.BytesIO(body))
    assert table.num_rows == 3
    assert table.schema == CANDLE_SCHEMA
    assert table.column("loaded_at")[0].as_py() == LOADED_AT


def test_rerun_overwrites_instead_of_duplicating(s3):
    key = raw_candles_key(1, "SBER", date(2026, 9, 1))

    put_candles(s3, BUCKET, key, make_rows(3), loaded_at=LOADED_AT)
    put_candles(s3, BUCKET, key, make_rows(3), loaded_at=LOADED_AT)

    objects = s3.list_objects_v2(Bucket=BUCKET)["Contents"]
    assert len(objects) == 1

    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    assert pq.read_table(io.BytesIO(body)).num_rows == 3
