from pathlib import Path

from scraper.parsers import list_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_list_page_extracts_document_cards():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    cards = list_page.parse_list_page(html)
    assert len(cards) == 5
    assert cards[0]["url"] == "https://legalacts.egov.kz/npa/view?id=15908401"
    assert "внесении изменений" in cards[0]["title"].lower()


def test_parse_total_pages_reads_script_value():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    assert list_page.parse_total_pages(html) == 29852


def test_parse_total_pages_defaults_to_one_when_absent():
    assert list_page.parse_total_pages("<html><body>Нет данных</body></html>") == 1
