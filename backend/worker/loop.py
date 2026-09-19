import os
import time

from scraper.run import run


def main(sleep_func=time.sleep):
    database_url = os.environ["DATABASE_URL"]
    interval = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "3600"))
    limit_raw = os.environ.get("WORKER_LIMIT")
    limit = int(limit_raw) if limit_raw else None

    while True:
        run(database_url, limit=limit)
        sleep_func(interval)


if __name__ == "__main__":
    main()
