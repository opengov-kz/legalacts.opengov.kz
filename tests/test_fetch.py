import requests
import pytest

from scraper.fetch import Fetcher


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_get_returns_response_on_first_success():
    session = FakeSession([FakeResponse(200, "ok")])
    fetcher = Fetcher(
        "test-agent", session=session, sleep_func=lambda s: None, random_func=lambda: 0
    )
    response = fetcher.get("https://example.test/page")
    assert response.status_code == 200
    assert session.calls == ["https://example.test/page"]


def test_get_retries_on_server_error_then_succeeds():
    session = FakeSession([FakeResponse(500), FakeResponse(200, "ok")])
    fetcher = Fetcher(
        "test-agent", max_retries=3, session=session,
        sleep_func=lambda s: None, random_func=lambda: 0,
    )
    response = fetcher.get("https://example.test/page")
    assert response.status_code == 200
    assert len(session.calls) == 2


def test_get_raises_after_exhausting_retries_on_network_error():
    session = FakeSession([requests.ConnectionError("boom"), requests.ConnectionError("boom")])
    fetcher = Fetcher(
        "test-agent", max_retries=1, session=session,
        sleep_func=lambda s: None, random_func=lambda: 0,
    )
    with pytest.raises(requests.ConnectionError):
        fetcher.get("https://example.test/page")


def test_get_raises_after_exhausting_retries_on_server_error():
    session = FakeSession([FakeResponse(500), FakeResponse(500)])
    fetcher = Fetcher(
        "test-agent", max_retries=1, session=session,
        sleep_func=lambda s: None, random_func=lambda: 0,
    )
    with pytest.raises(requests.HTTPError):
        fetcher.get("https://example.test/page")
    assert len(session.calls) == 2


def test_get_returns_404_response_without_retrying():
    session = FakeSession([FakeResponse(404)])
    fetcher = Fetcher(
        "test-agent", session=session, sleep_func=lambda s: None, random_func=lambda: 0
    )
    response = fetcher.get("https://example.test/missing")
    assert response.status_code == 404
    assert len(session.calls) == 1


def test_get_waits_between_requests():
    session = FakeSession([FakeResponse(200, "ok")])
    sleeps = []
    fetcher = Fetcher(
        "test-agent", delay=0.6, jitter=0.4, session=session,
        sleep_func=sleeps.append, random_func=lambda: 0.5,
    )
    fetcher.get("https://example.test/page")
    assert sleeps == [0.6 + 0.5 * 0.4]


def test_set_language_requests_changelang_endpoint():
    session = FakeSession([FakeResponse(302, "")])
    fetcher = Fetcher(
        "test-agent", session=session, sleep_func=lambda s: None, random_func=lambda: 0
    )
    fetcher.set_language("kk", location="/npa/view?id=1")
    assert session.calls == [
        "https://legalacts.egov.kz/application/changelang?lang=kk&location=/npa/view?id=1"
    ]
