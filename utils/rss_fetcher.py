"""Utilities for fetching real news articles from RSS feeds."""

from __future__ import annotations

import random
import re
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit, urlencode

import requests
from bs4 import BeautifulSoup

try:  # Optional dependency
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    feedparser = None  # type: ignore


# Feeds chosen for breadth (general, world, technology)
RSS_FEEDS: List[str] = [
    "http://rss.cnn.com/rss/edition.rss",
    "http://rss.cnn.com/rss/edition_world.rss",
    "http://rss.cnn.com/rss/edition_technology.rss",
    "http://feeds.bbci.co.uk/news/rss.xml",
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "http://feeds.reuters.com/reuters/topNews",
    "http://feeds.reuters.com/reuters/worldNews",
    "http://feeds.reuters.com/reuters/technologyNews",
    "https://rss.cbc.ca/lineup/topstories.xml",
    "https://rss.cbc.ca/lineup/world.xml",
    "https://rss.cbc.ca/lineup/technology.xml",
]

DEFAULT_IMAGE = "https://placehold.co/800x400?text=News"
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}


def _normalize_image_url(url: str, base_url: str = "") -> str:
    """Return an absolute URL stripped of common size parameters."""
    if not url:
        return ""

    if url.startswith("//"):
        url = "https:" + url
    elif base_url and url.startswith("/"):
        url = urljoin(base_url, url)

    try:
        split = urlsplit(url)
        query_params = [
            (k, v)
            for k, v in parse_qsl(split.query, keep_blank_values=True)
            if k.lower() not in {"w", "width", "h", "height", "resize", "fit", "scale", "quality"}
        ]
        cleaned_query = urlencode(query_params, doseq=True)
        return urlunsplit((split.scheme, split.netloc, split.path, cleaned_query, split.fragment))
    except Exception:
        return url.rstrip("?&")


def _sanitize_summary(html_text: str, fallback: str = "") -> str:
    """Convert RSS HTML into a short preview string."""
    if not html_text:
        html_text = fallback
    soup = BeautifulSoup(html_text or "", "html.parser")
    summary = soup.get_text(" ", strip=True)
    summary = re.sub(r"\s+", " ", summary)
    if len(summary) > 200:
        summary = summary[:200].rstrip() + "..."
    return summary


def _clean_content(text: str) -> str:
    """Remove duplicate/metadata lines from article content."""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned: List[str] = []
    prev = ""

    news_sources = {
        "cnn",
        "bbc",
        "reuters",
        "cbc",
        "ap news",
        "associated press",
        "guardian",
        "washington post",
        "usa today",
    }
    locations = {
        "washington",
        "london",
        "new york",
        "los angeles",
        "san francisco",
        "atlanta",
        "dc",
    }

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()

        if lower == prev.lower():
            continue
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", line):
            continue
        if re.match(r"^[•·▪▫]\s*(source|location|published|updated|by|from):?", line, re.I):
            continue
        if re.fullmatch(r"[•·▪▫]", line):
            continue
        if any(src in lower for src in news_sources) and len(line.split()) < 6:
            continue
        if any(loc in lower for loc in locations) and len(line.split()) < 5:
            continue
        if re.search(r"\d+\s+(hour|day|week|month|year|minute)s?\s+ago", lower):
            continue
        if re.search(r"(updated|published|posted)\s+\d+", lower):
            continue
        if any(term in lower for term in ["facebook", "twitter", "share on", "follow us", "newsletter"]):
            continue
        if re.fullmatch(r"[•·▪▫\d\s\-_]+", line):
            continue
        if len(line) < 4:
            continue

        cleaned.append(line)
        prev = line

    # Deduplicate sentences
    sentences = re.split(r"[.!?]+\s+", " ".join(cleaned))
    unique: List[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        sent = sentence.strip()
        if len(sent) < 10:
            continue
        lower = sent.lower()
        if any(
            len(set(lower.split()) & set(existing.split())) > len(lower.split()) * 0.8
            for existing in seen
            if len(existing.split()) > 6
        ):
            continue
        seen.add(lower)
        unique.append(sent)

    return "\n\n".join(unique) if unique else ""


def _extract_full_content(url: str) -> str:
    """Scrape the article body and return cleaned text."""
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        if response.status_code != 200:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove clearly irrelevant elements
        for selector in [
            "script",
            "style",
            "nav",
            "aside",
            "footer",
            "header",
            "button",
            "form",
            ".social",
            ".share",
            ".newsletter",
            ".advertisement",
        ]:
            for elem in soup.select(selector):
                elem.decompose()

        containers = soup.select(
            "article, [role='article'], .article-body, "
            ".story-body, .post-content, .entry-content, main"
        )
        for container in containers:
            for inner in container.select(
                "time, .timestamp, .date, .author-info, .share-buttons, .newsletter-signup"
            ):
                inner.decompose()
            text = container.get_text("\n", strip=True)
            text = _clean_content(text)
            if len(text) >= 200:
                return text
    except Exception:
        return ""
    return ""


def _select_best_image(
    media_items: Optional[List[Dict]],
    enclosure_links: Optional[List[Dict]],
    article_url: str,
) -> str:
    """Choose the highest quality image available."""
    page_image = _extract_image_from_page(article_url)
    if page_image:
        return page_image

    best_url = ""
    best_score = 0

    def consider(url: str, width: Optional[int] = None, height: Optional[int] = None) -> None:
        nonlocal best_url, best_score
        if not url:
            return
        normalized = _normalize_image_url(url, article_url)
        if not normalized.startswith("http"):
            return
        score = 0
        if width and height:
            score = width * height
        if score > best_score:
            best_score = score
            best_url = normalized
        elif not best_url:
            best_url = normalized

    for media in media_items or []:
        url = media.get("url")
        width = None
        height = None
        try:
            width = int(media.get("width")) if media.get("width") else None
            height = int(media.get("height")) if media.get("height") else None
        except Exception:
            pass
        consider(url, width, height)

    for link in enclosure_links or []:
        if link.get("rel") == "enclosure" and link.get("type", "").startswith("image"):
            consider(link.get("href"))

    if best_url:
        return best_url

    fallback_image = _extract_image_from_page(article_url)
    return fallback_image or DEFAULT_IMAGE


def _extract_image_from_page(url: str) -> Optional[str]:
    """Fetch the article page and attempt to locate a hero image."""
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        base_url = resp.url

        for selector in [
            ("meta", {"property": "og:image"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"name": "article:image"}),
        ]:
            tag = soup.find(*selector)
            if tag and tag.get("content"):
                img = _normalize_image_url(tag["content"], base_url)
                if img.startswith("http"):
                    return img

        candidates = []
        for container in soup.select(
            "article, [role='article'], .article-body, .story-body, .post-content, .entry-content, main"
        ):
            for img in container.find_all("img"):
                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-lazy-src")
                    or img.get("data-original")
                    or img.get("data-image")
                )
                if not src:
                    continue
                src_lower = src.lower()
                if any(skip in src_lower for skip in ("icon", "logo", "sprite", "avatar")):
                    continue

                width = height = 0
                try:
                    width = int(img.get("width", 0))
                    height = int(img.get("height", 0))
                except Exception:
                    pass
                score = width * height if width and height else 1
                normalized = _normalize_image_url(src, base_url)
                if normalized.startswith("http"):
                    candidates.append((score, normalized))

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except Exception:
        return None
    return None


def _prepare_article(
    title: str,
    summary_html: str,
    link: str,
    media: Optional[List[Dict]] = None,
    enclosure_links: Optional[List[Dict]] = None,
) -> Optional[Dict[str, str]]:
    """Build the final article payload from parsed data."""
    title = (title or "").strip()
    link = (link or "").strip()
    if not title or not link:
        return None

    summary = _sanitize_summary(summary_html or "")
    content = _extract_full_content(link)
    if not content or len(content) < 200:
        content = _clean_content(BeautifulSoup(summary_html or "", "html.parser").get_text("\n", strip=True))
    if not content:
        content = summary
    preview = summary or (content[:200].rstrip() + "..." if len(content) > 200 else content)

    photo = _select_best_image(media, enclosure_links, link)

    return {
        "title": title,
        "summary": preview,
        "content": content,
        "link": link,
        "photo": photo or DEFAULT_IMAGE,
    }


def fetch_random_article(max_feeds: int = 3, entries_per_feed: int = 6) -> Optional[Dict[str, str]]:
    """Fetch a random article using feedparser (preferred path)."""
    if feedparser is None:
        raise RuntimeError("feedparser is not installed")

    feeds = RSS_FEEDS[:]
    random.shuffle(feeds)

    for feed_url in feeds[:max_feeds]:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            continue
        entries = list(parsed.entries or [])
        random.shuffle(entries)
        for entry in entries[:entries_per_feed]:
            title = getattr(entry, "title", "")
            summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = getattr(entry, "link", "")
            media = getattr(entry, "media_content", None)
            enclosure_links = getattr(entry, "links", None)

            article = _prepare_article(title, summary_html, link, media, enclosure_links)
            if article:
                return article
    return None


def fetch_random_article_basic(max_feeds: int = 3, entries_per_feed: int = 6) -> Optional[Dict[str, str]]:
    """Fallback article fetcher that does not rely on feedparser."""
    feeds = RSS_FEEDS[:]
    random.shuffle(feeds)

    for feed_url in feeds[:max_feeds]:
        try:
            response = requests.get(feed_url, headers=HTTP_HEADERS, timeout=12)
            if response.status_code != 200:
                continue
            soup = BeautifulSoup(response.content, "xml")
            items = soup.find_all("item")
            random.shuffle(items)
            for item in items[:entries_per_feed]:
                title = item.title.get_text(strip=True) if item.title else ""
                summary_html = item.description.decode_contents() if item.description else ""
                link = item.link.get_text(strip=True) if item.link else ""
                media = []
                for media_tag in item.find_all("media:content"):
                    media.append(
                        {
                            "url": media_tag.get("url"),
                            "width": media_tag.get("width"),
                            "height": media_tag.get("height"),
                        }
                    )
                enclosure_links = []
                for enclosure in item.find_all("enclosure"):
                    enclosure_links.append(
                        {
                            "href": enclosure.get("url"),
                            "type": enclosure.get("type"),
                            "rel": enclosure.get("rel") or "enclosure",
                        }
                    )

                article = _prepare_article(title, summary_html, link, media, enclosure_links)
                if article:
                    return article
        except Exception:
            continue
    return None


__all__ = [
    "fetch_random_article",
    "fetch_random_article_basic",
    "DEFAULT_IMAGE",
    "RSS_FEEDS",
]



