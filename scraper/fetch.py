import random
import time

import requests

BASE_URL = "https://legalacts.egov.kz"


class Fetcher:
    def __init__(
        self, user_agent, delay=0.6, jitter=0.4, max_retries=3, backoff=2.0,
        session=None, sleep_func=time.sleep, random_func=random.random,
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.delay = delay
        self.jitter = jitter
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep_func
        self._random = random_func

    def set_language(self, lang, location="/"):
        url = f"{BASE_URL}/application/changelang?lang={lang}&location={location}"
        self.get(url)

    def get(self, url):
        attempt = 0
        while True:
            self._sleep(self.delay + self._random() * self.jitter)
            try:
                response = self.session.get(url, timeout=15)
            except requests.RequestException:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                self._sleep(self.backoff**attempt)
                continue
            if response.status_code >= 500 and attempt < self.max_retries:
                attempt += 1
                self._sleep(self.backoff**attempt)
                continue
            return response
