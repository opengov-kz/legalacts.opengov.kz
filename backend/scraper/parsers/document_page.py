import re

from bs4 import BeautifulSoup

LABEL_MAP = {
    "status": "Статус:",
    "doc_type": "Тип НПА:",
    "created_date": "Дата создания:",
    "discussion_end_date": "Публичное обсуждение до:",
}

GOVERNMENT_BODY_LABEL = "Государственный орган НПА:"
VERSION_LABEL = "Версия проекта:"
VERSION_NUMBER_RE = re.compile(r"Версия\s+(\d+)")


def _label_text(soup, label):
    for small in soup.select(".view-npa small, .blog-item small"):
        b = small.find("b")
        if b is not None and b.get_text(strip=True) == label:
            b.extract()
            return small.get_text(strip=True)
    return None


def _government_body(soup):
    el = soup.select_one(".blog-info .gov-parent")
    if el is not None:
        return el.get_text(strip=True)
    return _label_text(soup, GOVERNMENT_BODY_LABEL)


def _count_by_class_prefix(soup, prefix):
    span = soup.find("span", class_=re.compile("^" + re.escape(prefix)))
    if span is None:
        return 0
    text = span.get_text(strip=True)
    return int(text) if text.isdigit() else 0


def _views_count(soup):
    # Keyed on classes, not the "Количество просмотров" title attribute:
    # the .blog-item (arv) template carries the same icon classes but no
    # title (confirmed live 2026-09-24), while .view-npa (npa/kdrp) has both.
    icon = soup.select_one("i.liker.fa-eye")
    if icon is None:
        return 0
    li = icon.find_parent("li")
    match = re.search(r"\d+", li.get_text()) if li else None
    return int(match.group()) if match else 0


def parse_document_page(html):
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".view-npa h2, .blog-item h2")
    title = title_el.get_text(strip=True) if title_el else None
    template_recognized = title_el is not None

    fields = {key: _label_text(soup, label) for key, label in LABEL_MAP.items()}

    government_body = _government_body(soup)

    comments_total = 0
    comments_icon = soup.select_one('.blog-info i[title="Всего комментариев"]')
    if comments_icon is not None:
        li = comments_icon.find_parent("li")
        match = re.search(r"\d+", li.get_text()) if li else None
        if match:
            comments_total = int(match.group())

    return {
        "title": title,
        "template_recognized": template_recognized,
        "status": fields["status"],
        "doc_type": fields["doc_type"],
        "created_date": fields["created_date"],
        "discussion_end_date": fields["discussion_end_date"],
        "government_body": government_body,
        "comments_total": comments_total,
        "likes_count": _count_by_class_prefix(soup, "likeCount-"),
        "dislikes_count": _count_by_class_prefix(soup, "dislikeCount-"),
        "views_count": _views_count(soup),
    }


def parse_version_info(html):
    soup = BeautifulSoup(html, "lxml")
    for small in soup.select(".view-npa small, .blog-item small"):
        b = small.find("b")
        if b is None or b.get_text(strip=True) != VERSION_LABEL:
            continue
        link = small.find("a", href=True)
        previous_version_url = link["href"] if link else None
        b.extract()
        if link is not None:
            link.extract()
        text = small.get_text(" ", strip=True)
        match = VERSION_NUMBER_RE.search(text)
        version_number = int(match.group(1)) if match else None
        return {"version_number": version_number, "previous_version_url": previous_version_url}
    return {"version_number": None, "previous_version_url": None}


def parse_report_link(html):
    soup = BeautifulSoup(html, "lxml")
    link = soup.select_one('a[href^="/report?id="]')
    return link["href"] if link else None
