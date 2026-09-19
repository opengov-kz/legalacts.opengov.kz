import pytest

from worker import loop as loop_module


class StopLoop(Exception):
    pass


def test_main_calls_run_then_sleeps_with_configured_interval(monkeypatch):
    calls = []

    def fake_run(database_url, limit=None):
        calls.append(("run", database_url, limit))

    def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop()

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")
    monkeypatch.setenv("SCRAPE_INTERVAL_SECONDS", "42")
    monkeypatch.setenv("WORKER_LIMIT", "10")
    monkeypatch.setattr(loop_module, "run", fake_run)

    with pytest.raises(StopLoop):
        loop_module.main(sleep_func=fake_sleep)

    assert calls == [("run", "postgresql://test/db", 10), ("sleep", 42)]


def test_main_defaults_limit_to_none_when_unset(monkeypatch):
    calls = []

    def fake_run(database_url, limit=None):
        calls.append(("run", database_url, limit))

    def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop()

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")
    monkeypatch.delenv("SCRAPE_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("WORKER_LIMIT", raising=False)
    monkeypatch.setattr(loop_module, "run", fake_run)

    with pytest.raises(StopLoop):
        loop_module.main(sleep_func=fake_sleep)

    assert calls == [("run", "postgresql://test/db", None), ("sleep", 3600)]
