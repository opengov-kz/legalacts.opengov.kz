import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://legalacts.egov.kz"
TOTAL_PAGES_RE = re.compile(r"totalPages:\s*(\d+)")


def parse_list_page(html):
    soup = BeautifulSoup(html, "lxml")
    cards = []
    for block in soup.select("div.contentlist"):
        link = block.select_one("h3 a[href]")
        if link is None:
            continue
        cards.append({
            "url": urljoin(BASE_URL, link["href"]),
            "title": link.get_text(strip=True),
        })
    return cards


def parse_total_pages(html):
    match = TOTAL_PAGES_RE.search(html)
    return int(match.group(1)) if match else 1
