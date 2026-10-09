import argparse
import logging
from datetime import date, timedelta

from ingest.config import s3_settings, securities_path
from ingest.iss import IssClient, SecurityNotFoundError
from ingest.parse import candles_to_rows, group_by_date
from ingest.securities import load_securities
from ingest.storage import put_candles, raw_candles_key, s3_client

logger = logging.getLogger(__name__)


def month_ranges(date_from: date, date_till: date) -> list[tuple[date, date]]:
    """Режет период на календарные месяцы: так и запрос к ISS не разрастается,
    и в памяти лежит максимум месяц свечей одной бумаги."""
    if date_from > date_till:
        raise ValueError(f"{date_from} позже {date_till}")

    ranges = []
    start = date_from
    while start <= date_till:
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        end = min(next_month - timedelta(days=1), date_till)
        ranges.append((start, end))
        start = end + timedelta(days=1)
    return ranges


def load_security(
    client: IssClient,
    s3,
    bucket: str,
    secid: str,
    date_from: date,
    date_till: date,
    interval: int = 1,
) -> int:
    written = 0
    for chunk_from, chunk_till in month_ranges(date_from, date_till):
        rows = []
        for page in client.iter_candle_pages(
            secid, chunk_from, chunk_till, interval=interval
        ):
            rows.extend(candles_to_rows(secid, interval, page))

        for day, day_rows in sorted(group_by_date(rows).items()):
            key = raw_candles_key(interval, secid, day)
            put_candles(s3, bucket, key, day_rows)
            written += len(day_rows)

        logger.info("%s %s..%s: %d свечей", secid, chunk_from, chunk_till, len(rows))
    return written


def filter_known_secids(client: IssClient, secids: list[str]) -> list[str]:
    """На неизвестную бумагу ISS отвечает не 404, а пустым списком свечей,
    поэтому опечатку в справочнике ловим заранее по списку бумаг режима."""
    on_board = {row["SECID"] for row in client.get_board_securities()}
    unknown = [secid for secid in secids if secid not in on_board]
    if unknown:
        logger.warning("Нет на TQBR, пропускаю: %s", ", ".join(unknown))

    known = [secid for secid in secids if secid in on_board]
    if not known:
        raise RuntimeError("Ни одной бумаги из справочника нет на TQBR")
    return known


def load_securities_range(
    secids: list[str], date_from: date, date_till: date, interval: int = 1
) -> int:
    settings = s3_settings()
    s3 = s3_client(settings)
    total = 0
    missing = []

    with IssClient() as client:
        for secid in filter_known_secids(client, secids):
            try:
                total += load_security(
                    client, s3, settings.bucket, secid, date_from, date_till, interval
                )
            except SecurityNotFoundError:
                # редкий случай: бумага есть в списке режима, но свечи отдают 404
                logger.warning("ISS не отдал свечи по %s, пропускаю", secid)
                missing.append(secid)

    if missing:
        logger.warning("Бумаги без данных: %s", ", ".join(missing))
    if total == 0:
        raise RuntimeError("Не загружено ни одной свечи, проверь период и справочник")

    logger.info("Загружено свечей: %d", total)
    return total


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Загрузка свечей MOEX ISS в raw-слой")
    parser.add_argument("--date-from", required=True, type=_parse_date)
    parser.add_argument("--date-till", required=True, type=_parse_date)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument(
        "--secid",
        action="append",
        help="бумага (можно повторить); по умолчанию весь справочник",
    )
    args = parser.parse_args()

    secids = args.secid or [s.secid for s in load_securities(securities_path())]
    load_securities_range(secids, args.date_from, args.date_till, args.interval)


if __name__ == "__main__":
    main()
