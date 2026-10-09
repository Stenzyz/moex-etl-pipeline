import logging
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ingest.config import BOARD, ISS_BASE_URL, request_delay
from ingest.parse import block_to_records

logger = logging.getLogger(__name__)

# ISS отдаёт свечи страницами по 500 строк, дальше пагинация через start
CANDLES_PAGE_SIZE = 500


class SecurityNotFoundError(Exception):
    """ISS не знает такую бумагу на этом режиме торгов (404)."""


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code <= 599
    return isinstance(exc, httpx.TimeoutException | httpx.TransportError)


class IssClient:
    def __init__(
        self,
        base_url: str = ISS_BASE_URL,
        delay: float | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.delay = request_delay() if delay is None else delay
        self.client = httpx.Client(timeout=timeout)

    def __enter__(self) -> "IssClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception(is_retryable),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        time.sleep(self.delay)
        response = self.client.get(f"{self.base_url}{path}", params=params)
        if response.status_code == 404:
            raise SecurityNotFoundError(f"ISS вернул 404 на {path}")
        response.raise_for_status()
        return response.json()

    def get_board_securities(self, board: str = BOARD) -> list[dict[str, Any]]:
        payload = self._get(
            f"/engines/stock/markets/shares/boards/{board}/securities.json",
            {"iss.meta": "off", "iss.only": "securities"},
        )
        return block_to_records(payload, "securities")

    def iter_candle_pages(
        self,
        secid: str,
        date_from: date,
        date_till: date,
        interval: int = 1,
        board: str = BOARD,
    ) -> Iterator[list[dict[str, Any]]]:
        path = (
            f"/engines/stock/markets/shares/boards/{board}"
            f"/securities/{secid}/candles.json"
        )
        start = 0
        while True:
            payload = self._get(
                path,
                {
                    "iss.meta": "off",
                    "interval": interval,
                    "from": date_from.isoformat(),
                    "till": date_till.isoformat(),
                    "start": start,
                },
            )
            records = block_to_records(payload, "candles")
            if not records:
                return

            yield records

            # неполная страница означает, что данные кончились
            if len(records) < CANDLES_PAGE_SIZE:
                return
            start += len(records)
