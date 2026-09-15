import re

from bs4 import BeautifulSoup

LABEL_MAP = {
    "status": "Статус:",
    "doc_type": "Тип НПА:",
    "created_date": "Дата создания:",
    "discussion_end_date": "Публичное обсуждение до:",
}


def _label_text(soup, label):
    for small in soup.select(".view-npa small"):
        b = small.find("b")
        if b is not None and b.get_text(strip=True) == label:
            b.extract()
            return small.get_text(strip=True)
    return None


def _count_by_class_prefix(soup, prefix):
    span = soup.find("span", class_=re.compile("^" + re.escape(prefix)))
    if span is None:
        return 0
    text = span.get_text(strip=True)
    return int(text) if text.isdigit() else 0


def parse_document_page(html):
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".view-npa h2")
    title = title_el.get_text(strip=True) if title_el else None

    fields = {key: _label_text(soup, label) for key, label in LABEL_MAP.items()}

    government_body_el = soup.select_one(".blog-info .gov-parent")
    government_body = (
        government_body_el.get_text(strip=True) if government_body_el else None
    )

    comments_total = 0
    comments_icon = soup.select_one('.blog-info i[title="Всего комментариев"]')
    if comments_icon is not None:
        li = comments_icon.find_parent("li")
        match = re.search(r"\d+", li.get_text()) if li else None
        if match:
            comments_total = int(match.group())

    return {
        "title": title,
        "status": fields["status"],
        "doc_type": fields["doc_type"],
        "created_date": fields["created_date"],
        "discussion_end_date": fields["discussion_end_date"],
        "government_body": government_body,
        "comments_total": comments_total,
        "likes_count": _count_by_class_prefix(soup, "likeCount-"),
        "dislikes_count": _count_by_class_prefix(soup, "dislikeCount-"),
    }
