import io
from datetime import UTC, date, datetime
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from ingest.config import S3Settings

CANDLE_SCHEMA = pa.schema(
    [
        ("secid", pa.string()),
        ("interval", pa.int16()),
        # parquet хранит время с точностью до миллисекунд, секундный тип
        # он всё равно приведёт к ms, поэтому объявляем ms сразу
        ("begin", pa.timestamp("ms")),
        ("end", pa.timestamp("ms")),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("value", pa.float64()),
        ("volume", pa.int64()),
        ("loaded_at", pa.timestamp("ms", tz="UTC")),
    ]
)


def s3_client(settings: S3Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
    )


def raw_candles_key(interval: int, secid: str, day: date) -> str:
    return (
        f"raw/candles/interval={interval}/secid={secid}/date={day.isoformat()}.parquet"
    )


def rows_to_parquet(rows: list[dict[str, Any]], loaded_at: datetime) -> bytes:
    stamped = [row | {"loaded_at": loaded_at} for row in rows]
    table = pa.Table.from_pylist(stamped, schema=CANDLE_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


def put_candles(
    s3,
    bucket: str,
    key: str,
    rows: list[dict[str, Any]],
    loaded_at: datetime | None = None,
) -> None:
    """Кладёт свечи одного дня. Повторный вызов перезаписывает объект целиком,
    поэтому дублей не бывает и отдельная дедупликация на raw не нужна."""
    if loaded_at is None:
        loaded_at = datetime.now(UTC).replace(microsecond=0)
    s3.put_object(Bucket=bucket, Key=key, Body=rows_to_parquet(rows, loaded_at))
