import os
from typing import NamedTuple

ISS_BASE_URL = "https://iss.moex.com/iss"
BOARD = "TQBR"


class S3Settings(NamedTuple):
    endpoint_url: str
    region: str
    access_key: str
    secret_key: str
    bucket: str


def s3_settings() -> S3Settings:
    return S3Settings(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        region=os.environ["S3_REGION"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        bucket=os.environ["S3_BUCKET"],
    )


def securities_path() -> str:
    return os.environ.get("SECURITIES_CSV", "config/securities.csv")


def request_delay() -> float:
    return float(os.environ.get("ISS_REQUEST_DELAY", "0.1"))
