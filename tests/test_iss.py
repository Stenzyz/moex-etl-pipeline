from datetime import date

import httpx
import pytest
import respx

from ingest.iss import CANDLES_PAGE_SIZE, IssClient, SecurityNotFoundError

CANDLES_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR"
    "/securities/SBER/candles.json"
)
DAY = date(2026, 9, 1)


def candles_payload(count: int) -> dict:
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
                    "2026-09-01 10:00:00",
                    "2026-09-01 10:00:59",
                ]
                for _ in range(count)
            ],
        }
    }


@pytest.fixture
def client():
    with IssClient(delay=0) as c:
        yield c


@respx.mock
def test_single_page_stops_after_one_request(client):
    route = respx.get(CANDLES_URL).mock(
        return_value=httpx.Response(200, json=candles_payload(3))
    )

    pages = list(client.iter_candle_pages("SBER", DAY, DAY))

    assert route.call_count == 1
    assert len(pages) == 1
    assert len(pages[0]) == 3


@respx.mock
def test_full_page_triggers_pagination(client):
    respx.get(CANDLES_URL).mock(
        side_effect=[
            httpx.Response(200, json=candles_payload(CANDLES_PAGE_SIZE)),
            httpx.Response(200, json=candles_payload(7)),
        ]
    )

    pages = list(client.iter_candle_pages("SBER", DAY, DAY))

    assert [len(page) for page in pages] == [CANDLES_PAGE_SIZE, 7]


@respx.mock
def test_empty_page_ends_iteration(client):
    respx.get(CANDLES_URL).mock(
        side_effect=[
            httpx.Response(200, json=candles_payload(CANDLES_PAGE_SIZE)),
            httpx.Response(200, json=candles_payload(0)),
        ]
    )

    pages = list(client.iter_candle_pages("SBER", DAY, DAY))

    assert len(pages) == 1


@respx.mock
def test_unknown_security_raises(client):
    respx.get(CANDLES_URL).mock(return_value=httpx.Response(404))

    with pytest.raises(SecurityNotFoundError):
        list(client.iter_candle_pages("SBER", DAY, DAY))


@respx.mock
def test_retries_on_429(client):
    route = respx.get(CANDLES_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json=candles_payload(1)),
        ]
    )

    pages = list(client.iter_candle_pages("SBER", DAY, DAY))

    assert route.call_count == 2
    assert len(pages) == 1


@respx.mock
def test_does_not_retry_on_400(client):
    route = respx.get(CANDLES_URL).mock(return_value=httpx.Response(400))

    with pytest.raises(httpx.HTTPStatusError):
        list(client.iter_candle_pages("SBER", DAY, DAY))

    assert route.call_count == 1
