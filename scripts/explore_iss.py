"""Разведка MOEX ISS: сверяет справочник бумаг и замеряет поведение API.
Ничего не пишет в S3, результат нужен для docs/scope.md."""

import logging
import time
from datetime import date, timedelta

from ingest.config import securities_path
from ingest.iss import CANDLES_PAGE_SIZE, IssClient, SecurityNotFoundError
from ingest.parse import candles_to_rows, group_by_date
from ingest.securities import load_securities

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROBE_SECID = "SBER"
RATE_PROBES = 20


def check_securities(client: IssClient) -> None:
    print("\n=== Справочник бумаг TQBR ===")
    board = client.get_board_securities()
    on_board = {row["SECID"] for row in board}
    print(f"Всего бумаг на TQBR: {len(on_board)}")

    ours = load_securities(securities_path())
    missing = [s.secid for s in ours if s.secid not in on_board]
    print(f"В нашем справочнике: {len(ours)}")
    print(f"Нет на TQBR: {missing if missing else 'нет таких'}")


def check_candles_shape(client: IssClient, day: date) -> None:
    print(f"\n=== Формат свечей, {PROBE_SECID} за {day} ===")
    pages = list(client.iter_candle_pages(PROBE_SECID, day, day))
    if not pages:
        print("Свечей нет, возможно это выходной. Возьми другую дату")
        return

    print(f"Страниц: {len(pages)}, строк на первой: {len(pages[0])}")
    print(f"Ожидаемый размер страницы в коде: {CANDLES_PAGE_SIZE}")
    print(f"Колонки: {sorted(pages[0][0])}")
    print(f"Первая свеча: {pages[0][0]}")

    rows = [r for page in pages for r in candles_to_rows(PROBE_SECID, 1, page)]
    print(f"Всего свечей за день: {len(rows)}")
    print(f"Первая: {rows[0]['begin']}, последняя: {rows[-1]['begin']}")


def check_month_volume(client: IssClient, date_from: date, date_till: date) -> None:
    print(f"\n=== Объём за месяц, {PROBE_SECID} {date_from}..{date_till} ===")
    requests = 0
    rows = []
    for page in client.iter_candle_pages(PROBE_SECID, date_from, date_till):
        requests += 1
        rows.extend(candles_to_rows(PROBE_SECID, 1, page))

    by_day = group_by_date(rows)
    print(f"Запросов: {requests}, свечей: {len(rows)}, торговых дней: {len(by_day)}")
    if by_day:
        per_day = len(rows) / len(by_day)
        print(f"В среднем свечей в день: {per_day:.0f}")

    weekend = sorted(d for d in by_day if d.weekday() >= 5)
    print(f"Торги в выходные: {weekend if weekend else 'не было'}")


def check_unknown_secid(client: IssClient, day: date) -> None:
    print("\n=== Несуществующая бумага ===")
    try:
        pages = list(client.iter_candle_pages("NOSUCHSECID", day, day))
    except SecurityNotFoundError:
        print("ISS ответил 404")
    else:
        print(f"ISS ответил 200, страниц: {len(pages)}")
        print("Поэтому тикеры сверяются со списком бумаг режима до загрузки")


def check_rate(client: IssClient, day: date) -> None:
    print(f"\n=== Нагрузка: {RATE_PROBES} запросов подряд без паузы ===")
    probe = IssClient(delay=0)
    started = time.time()
    try:
        for _ in range(RATE_PROBES):
            next(iter(probe.iter_candle_pages(PROBE_SECID, day, day)), None)
    except Exception as exc:
        print(f"Упёрлись в лимит после части запросов: {type(exc).__name__}: {exc}")
    else:
        elapsed = time.time() - started
        print(f"Прошли все за {elapsed:.1f} с, ошибок нет")
    finally:
        probe.close()


def main() -> None:
    # берём заведомо прошедший рабочий период, чтобы данные точно были
    today = date.today()
    probe_day = today - timedelta(days=7)
    while probe_day.weekday() >= 5:
        probe_day -= timedelta(days=1)

    month_till = today.replace(day=1) - timedelta(days=1)
    month_from = month_till.replace(day=1)

    with IssClient() as client:
        check_securities(client)
        check_candles_shape(client, probe_day)
        check_month_volume(client, month_from, month_till)
        check_unknown_secid(client, probe_day)
        check_rate(client, probe_day)


if __name__ == "__main__":
    main()
