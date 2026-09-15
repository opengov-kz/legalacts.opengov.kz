from pathlib import Path

from scraper.parsers import comments as comments_parser

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_comments_flattens_top_level_and_replies():
    result = comments_parser.parse_comments(_read("document_with_comments.html"))
    assert len(result) == 20

    first = result[0]
    assert first["external_id"] == 15907499
    assert first["parent_external_id"] is None
    assert first["author_name"] == "СУХАНОВ АНДРЕЙ"
    assert first["status"] == "rejected"
    assert "Полная версия" in first["body"]
    assert first["commented_at_raw"] == "10/09 - 11:05"

    reply = result[1]
    assert reply["external_id"] == 15907783
    assert reply["parent_external_id"] == 15907499
    assert reply["author_name"] == "Министерство труда и социальной защиты населения РК"
    assert reply["status"] is None
    assert reply["commented_at_raw"] == "10/09 - 12:24"


def test_parse_comments_returns_empty_list_when_no_comments():
    assert comments_parser.parse_comments(_read("document_no_comments.html")) == []
