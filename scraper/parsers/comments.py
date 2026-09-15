import re

from bs4 import BeautifulSoup

STATUS_BY_TITLE = {
    "Принято": "accepted",
    "Не принято": "rejected",
}

TIMESTAMP_RE = re.compile(r"\d{2}/\d{2} - \d{2}:\d{2}")


def parse_comments(html):
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one(".main-comments")
    if container is None:
        return []
    result = []
    for media in container.find_all("div", class_="media", recursive=False):
        result.extend(_parse_comment_node(media, parent_external_id=None))
    return result


def _parse_comment_node(media, parent_external_id):
    body = media.find("div", class_="media-body", recursive=False)
    if body is None:
        return []

    headings = body.find_all("h4", class_="media-heading", recursive=False)
    author_name = headings[0].get_text(strip=True) if headings else None
    # For nested replies, timestamp is in the same h4, so strip it from author_name
    if author_name:
        author_name = TIMESTAMP_RE.sub('', author_name).strip()

    heading_text = " ".join(h.get_text(" ", strip=True) for h in headings)
    timestamp_match = TIMESTAMP_RE.search(heading_text)
    commented_at_raw = timestamp_match.group() if timestamp_match else None

    article_ref = None
    status = None
    if len(headings) > 1:
        second = headings[1]
        ref_link = second.select_one("a.view-comment-part[npa-id]")
        if ref_link is not None:
            article_ref = ref_link.get_text(strip=True)
        status_icon = second.select_one("i.liker")
        if status_icon is not None:
            status = STATUS_BY_TITLE.get(status_icon.get("title", ""))

    text_el = body.find("p", recursive=False)
    external_id = None
    text = ""
    if text_el is not None:
        text = text_el.get_text(strip=True)
        if text_el.has_attr("id"):
            external_id = int(text_el["id"])

    comment = {
        "external_id": external_id,
        "parent_external_id": parent_external_id,
        "author_name": author_name,
        "body": text,
        "article_ref": article_ref,
        "status": status,
        "commented_at_raw": commented_at_raw,
    }

    result = [comment]
    nested = body.find("div", class_="media", recursive=False)
    if nested is not None:
        result.extend(_parse_comment_node(nested, parent_external_id=external_id))
    return result
