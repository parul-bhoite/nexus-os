"""Extract observable signals from a fetched page.

Deliberately **observation only**. Nothing here interprets, scores or infers —
it records what is present in the HTML, with no judgement attached. Scoring
happens in `calculators/`, which is pure and unit-tested, and interpretation
happens in a model call that does not exist in M2 at all.

That split is I1 in structural form: an extractor that returned a "brand score"
would make the number's origin a matter of trust rather than of construction.

**`PageSignals` itself lives in `domain/page_signals.py`, not here.** This
module is the HTML parser, and `tests/test_no_unauthenticated_crawl.py` forbids
any module under `app/research/` from being reachable from an unauthenticated
route. The dashboard read path needs the *shape* and its storage codec —
`retrieval/crawl.py` deserialises a stored row — and dragging the parser along
with it put `app.research.extract` on a graph reachable from
`routes/companies.py`. Parsing a page and describing what a page contains are
two different things; only the first is the crawl engine.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from app.domain.page_signals import PageSignals

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Loose on purpose: GCC numbers vary in shape and this only records presence.
PHONE_RE = re.compile(r"(?:\+\d{1,4}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?){2,4}\d{2,4}")

SOCIAL_HOSTS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "wa.me": "whatsapp",
}


def _text_of(tags: list[Tag], limit: int) -> tuple[str, ...]:
    out = []
    for tag in tags[:limit]:
        text = tag.get_text(" ", strip=True)
        if text:
            out.append(text[:300])
    return tuple(out)


def extract_signals(html: str, *, url: str) -> PageSignals:
    soup = BeautifulSoup(html, "lxml")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()

    for junk in soup(["script", "style", "noscript", "template"]):
        junk.decompose()
    body_text = soup.get_text(" ", strip=True)

    soup_with_scripts = BeautifulSoup(html, "lxml")

    title_tag = soup_with_scripts.title
    title = title_tag.get_text(strip=True) if title_tag else None

    def _attr(tag: Tag, key: str) -> str | None:
        """Read one attribute as a plain string.

        bs4 returns a list for multi-valued attributes such as `rel` and
        `class`, so a bare `.get()` is not reliably a `str`.
        """
        value = tag.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            return " ".join(str(v) for v in value)
        return None

    def meta(name: str | None = None, prop: str | None = None) -> str | None:
        attrs: Mapping[str, str] = {"name": name} if name else {"property": prop or ""}
        tag = soup_with_scripts.find("meta", attrs=dict(attrs))
        if isinstance(tag, Tag):
            content = _attr(tag, "content")
            if content is not None:
                return content.strip()
        return None

    description = meta(name="description")
    robots = meta(name="robots") or ""

    canonical_tag = soup_with_scripts.find("link", rel="canonical")
    canonical = None
    if isinstance(canonical_tag, Tag):
        href = _attr(canonical_tag, "href")
        if href:
            canonical = urljoin(url, href)

    html_tag = soup_with_scripts.find("html")
    language = None
    if isinstance(html_tag, Tag):
        lang = _attr(html_tag, "lang")
        language = lang.strip() if lang and lang.strip() else None

    images = soup_with_scripts.find_all("img")
    with_alt = sum(
        1 for img in images if isinstance(img, Tag) and (_attr(img, "alt") or "").strip()
    )

    internal = external = 0
    socials: set[str] = set()
    for anchor in soup_with_scripts.find_all("a", href=True):
        href = _attr(anchor, "href") if isinstance(anchor, Tag) else None
        if not href:
            continue
        target_host = (urlsplit(urljoin(url, href)).hostname or "").lower()
        if not target_host or target_host == host:
            internal += 1
        else:
            external += 1
            for social_host, label in SOCIAL_HOSTS.items():
                if target_host.endswith(social_host):
                    socials.add(label)

    return PageSignals(
        url=url,
        is_https=parts.scheme == "https",
        title=title,
        title_length=len(title or ""),
        meta_description=description,
        meta_description_length=len(description or ""),
        h1_texts=_text_of(soup_with_scripts.find_all("h1"), 10),
        h2_texts=_text_of(soup_with_scripts.find_all("h2"), 25),
        has_viewport_meta=meta(name="viewport") is not None,
        has_canonical=canonical is not None,
        canonical_url=canonical,
        has_robots_meta=bool(robots),
        robots_blocks_indexing="noindex" in robots.lower(),
        has_structured_data=bool(
            soup_with_scripts.find("script", attrs={"type": "application/ld+json"})
        ),
        has_open_graph=meta(prop="og:title") is not None,
        declared_language=language,
        image_count=len(images),
        images_with_alt=with_alt,
        internal_link_count=internal,
        external_link_count=external,
        emails=tuple(sorted(set(EMAIL_RE.findall(body_text)))[:10]),
        has_phone=bool(PHONE_RE.search(body_text)),
        social_profiles=tuple(sorted(socials)),
        word_count=len(body_text.split()),
        html_bytes=len(html.encode("utf-8", errors="ignore")),
        script_count=len(soup_with_scripts.find_all("script")),
        stylesheet_count=len(soup_with_scripts.find_all("link", rel="stylesheet")),
        inline_style_count=len(soup_with_scripts.find_all("style")),
        text_sample=body_text[:2000],
    )


def extract_text(html: str) -> str:
    """The page's visible text, with markup and script content removed.

    Split out of `extract_signals`, which computed the same thing privately: the
    crawl needs the text without the twenty other signals, and
    `looks_javascript_rendered` needs to compare it against the script volume.
    Two implementations of "the visible text" would disagree about whether a
    page is a shell, and only one of them would be the one indexed.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return str(soup.get_text(" ", strip=True))


