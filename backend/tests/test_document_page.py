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


def test_parse_document_page_reads_arv_conclusion_template():
    # /npa/viewArvConclusion pages use a different template than /npa/view:
    # no `.view-npa` wrapper, so title/status/doc_type/dates live under
    # `.blog-item` instead. There is no "Статус:" label on this template.
    data = document_page.parse_document_page(_read("document_arv_conclusion.html"))
    assert data["title"].startswith(
        "Заключение о соблюдении процедур анализа регуляторного акта"
    )
    assert data["status"] is None
    assert data["doc_type"] == "Заключение по АРВ"
    assert data["created_date"] == "07/09/2026"
    assert data["discussion_end_date"] is None
    assert data["government_body"] == "Министерство национальной экономики РК"
    assert data["comments_total"] == 0
    assert data["likes_count"] == 1
    assert data["dislikes_count"] == 0


def test_parse_document_page_falls_back_to_government_body_label_when_gov_parent_absent():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Государственный орган НПА:</b> город Караганды</small>'
        '</div>'
    )
    data = document_page.parse_document_page(html)
    assert data["government_body"] == "город Караганды"


def test_parse_document_page_reports_template_recognized_for_known_templates():
    data = document_page.parse_document_page(_read("document_no_comments.html"))
    assert data["template_recognized"] is True

    data_arv = document_page.parse_document_page(_read("document_arv_conclusion.html"))
    assert data_arv["template_recognized"] is True


def test_parse_document_page_reports_template_not_recognized_for_unknown_html():
    html = (
        '<html><body><div class="some-other-template">'
        '<h1>Not a known template</h1></div></body></html>'
    )
    data = document_page.parse_document_page(html)
    assert data["template_recognized"] is False
    assert data["title"] is None


def test_parse_version_info_returns_number_and_previous_url_when_present():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=52440">Версия 1</a> )</small>'
        '</div>'
    )
    data = document_page.parse_version_info(html)
    assert data["version_number"] == 2
    assert data["previous_version_url"] == "/application/viewcardhistory?id=52440"


def test_parse_version_info_returns_none_url_for_earliest_version():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Версия проекта:</b> Версия 1</small>'
        '</div>'
    )
    data = document_page.parse_version_info(html)
    assert data["version_number"] == 1
    assert data["previous_version_url"] is None


def test_parse_version_info_ignores_linked_versions_own_number_when_current_page_blank():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Версия проекта:</b> '
        '( <a href="/application/viewcardhistory?id=100">Версия 5</a> )</small>'
        '</div>'
    )
    data = document_page.parse_version_info(html)
    assert data["version_number"] is None
    assert data["previous_version_url"] == "/application/viewcardhistory?id=100"


def test_parse_version_info_returns_none_when_field_absent():
    html = '<div class="view-npa"><h2>Test</h2></div>'
    data = document_page.parse_version_info(html)
    assert data["version_number"] is None
    assert data["previous_version_url"] is None


def test_parse_report_link_returns_href_when_present():
    data = document_page.parse_report_link(_read("document_with_comments.html"))
    assert data == "/report?id=15906353"


def test_parse_report_link_returns_none_when_absent():
    data = document_page.parse_report_link(_read("document_no_comments.html"))
    assert data is None
