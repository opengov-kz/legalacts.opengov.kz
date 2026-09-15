from pathlib import Path

from scraper.parsers import document_page

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_document_page_extracts_core_fields_without_comments():
    data = document_page.parse_document_page(_read("document_no_comments.html"))
    assert data["title"] == (
        "О понижении размера ставки налогов при применении специального "
        "налогового режима на основе упрощенной декларации в городе Каражал"
    )
    assert data["status"] == "На публичном обсуждении"
    assert data["doc_type"] == "Решение"
    assert data["created_date"] == "15/09/2026"
    assert data["discussion_end_date"] == "30/09/2026"
    assert data["government_body"] == "Аппарат акима города Каражал"
    assert data["comments_total"] == 0
    assert data["likes_count"] == 0
    assert data["dislikes_count"] == 0


def test_parse_document_page_reads_counts_with_comments():
    data = document_page.parse_document_page(_read("document_with_comments.html"))
    assert data["status"] == "Архив"
    assert data["doc_type"] == "Приказ"
    assert data["government_body"] == "Министерство труда и социальной защиты населения РК"
    assert data["comments_total"] == 24
    assert data["likes_count"] == 0
    assert data["dislikes_count"] == 1


def test_parse_document_page_reads_kk_title():
    data = document_page.parse_document_page(_read("document_with_comments_kk.html"))
    assert data["title"].startswith("Қазақстан Республикасы")
