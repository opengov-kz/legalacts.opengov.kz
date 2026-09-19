import logging
import os
import time

from scraper.run import run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main(sleep_func=time.sleep):
    database_url = os.environ["DATABASE_URL"]
    interval = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "3600"))
    limit_raw = os.environ.get("WORKER_LIMIT")
    limit = int(limit_raw) if limit_raw else None

    while True:
        try:
            run(database_url, limit=limit)
            logger.info("crawl cycle complete")
        except Exception:
            logger.exception("crawl cycle failed")
        sleep_func(interval)


if __name__ == "__main__":
    main()
