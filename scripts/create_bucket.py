import logging
import os
import time

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def wait_for_s3(s3, attempts: int = 30, delay: float = 2) -> None:
    for _ in range(attempts):
        try:
            s3.list_buckets()
            return
        except EndpointConnectionError:
            time.sleep(delay)
        except ClientError as exc:
            # MinIO на старте отвечает 503, пока не поднялся
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 503:
                raise
            time.sleep(delay)
    raise RuntimeError(f"S3 не ответил за {attempts * delay:.0f} с")


def main() -> None:
    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        region_name=os.environ["S3_REGION"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )

    wait_for_s3(s3)

    try:
        s3.head_bucket(Bucket=bucket)
        logger.info("Бакет %s уже есть", bucket)
    except ClientError as exc:
        # 404 значит бакета нет, остальное (403, неверные ключи) пробрасываем
        if exc.response["Error"]["Code"] != "404":
            raise
        s3.create_bucket(Bucket=bucket)
        logger.info("Создан бакет %s", bucket)


if __name__ == "__main__":
    main()
