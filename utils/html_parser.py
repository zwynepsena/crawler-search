from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


# Truly invisible containers whose inner text should be skipped.
# Important: do NOT include void tags like meta/link here, because they do not
# have closing tags and would leave skip_depth stuck above zero.
_SKIP_CONTAINERS = frozenset([
    "script",
    "style",
    "noscript",
    "object",
    "embed",
    "iframe",
])


class _LinkExtractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return

        for attr, value in attrs:
            if attr and attr.lower() == "href" and value:
                absolute = _to_absolute(value.strip(), self.base_url)
                if absolute:
                    self.links.append(absolute)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._tokens = []
        self._skip_depth = 0
        self._head_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag == "head":
            self._head_depth += 1

        if tag in _SKIP_CONTAINERS:
            self._skip_depth += 1

        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "title":
            self._in_title = False

        if tag in _SKIP_CONTAINERS:
            self._skip_depth = max(0, self._skip_depth - 1)

        if tag == "head":
            self._head_depth = max(0, self._head_depth - 1)

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return

        if self._skip_depth > 0:
            return

        if self._in_title:
            if not self.title:
                self.title = text
            return

        # Ignore non-title text inside <head>
        if self._head_depth > 0:
            return

        self._tokens.append(text)

    @property
    def body_text(self):
        return " ".join(self._tokens)


def extract_links(html: str, base_url: str) -> list[str]:
    parser = _LinkExtractor(base_url)
    parser.feed(html)
    parser.close()

    seen = set()
    result = []

    for link in parser.links:
        if link not in seen:
            seen.add(link)
            result.append(link)

    return result


def extract_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.title, parser.body_text


def _to_absolute(href: str, base_url: str) -> str | None:
    if not href:
        return None

    lowered = href.lower()
    if lowered.startswith(("#", "mailto:", "javascript:", "data:", "tel:")):
        return None

    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)

    if parsed.scheme not in ("http", "https"):
        return None

    if not parsed.netloc:
        return None

    return parsed._replace(fragment="").geturl()