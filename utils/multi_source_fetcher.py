"""Multi-source fetcher that fuses several perspectives into key points."""

import random
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

try:
    import feedparser
except ImportError:  # pragma: no cover - optional dependency
    feedparser = None

RSS_FEEDS = [
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

BIAS_DOMAINS = {
    "left": {"cnn.com", "nytimes.com", "washingtonpost.com", "cbc.ca", "theguardian.com"},
    "center": {"bbc.co.uk", "reuters.com", "apnews.com", "npr.org"},
    "right": {"foxnews.com", "nypost.com", "newsmax.com", "dailycaller.com"},
}

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DEFAULT_IMAGE = "https://via.placeholder.com/800x400?text=News"


def _normalize_domain(url: str) -> str:
    try:
        parsed = urlparse(url or "")
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.split(":")[0]
    except Exception:
        return ""


def _classify_bias(domain: str) -> str:
    for bias, candidates in BIAS_DOMAINS.items():
        if any(domain == c or domain.endswith(f".{c}") for c in candidates):
            return bias
    return "center"


def _extract_keywords(text: str) -> List[str]:
    words = re.findall(r"\b[a-z]{4,}\b", (text or "").lower())
    stop_words = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "will",
        "news",
        "says",
        "could",
        "would",
        "should",
        "what",
        "when",
        "where",
        "which",
        "who",
        "there",
        "their",
        "these",
        "those",
        "about",
        "after",
        "before",
    }
    return [w for w in words if w not in stop_words][:8]


def _parse_feed(feed_url: str, entries_per_feed: int = 12, timeout: int = 4) -> List[Dict]:
    """Parse an RSS feed into lightweight entries."""
    entries: List[Dict] = []
    try:
        if feedparser:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.get("entries", [])[:entries_per_feed]:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", "").strip()
                summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                if not title or not link:
                    continue
                entries.append({"title": title, "link": link, "summary": summary})
            return entries

        # Fallback simple XML parsing
        resp = requests.get(feed_url, timeout=timeout, headers=HTTP_HEADERS)
        if resp.status_code != 200:
            return entries
        soup = BeautifulSoup(resp.content, "xml")
        for item in soup.find_all("item")[:entries_per_feed]:
            title_node = item.find("title")
            link_node = item.find("link")
            if not (title_node and link_node):
                continue
            summary_node = item.find("description")
            entries.append(
                {
                    "title": title_node.get_text(strip=True),
                    "link": link_node.get_text(strip=True),
                    "summary": summary_node.get_text(strip=True) if summary_node else "",
                }
            )
    except Exception:
        return entries
    return entries


def _collect_entries(max_feeds: int = 10, entries_per_feed: int = 12) -> List[Dict]:
    feeds = RSS_FEEDS[:]
    random.shuffle(feeds)
    collected: List[Dict] = []
    seen_links = set()

    for feed_url in feeds[:max_feeds]:
        feed_entries = _parse_feed(feed_url, entries_per_feed=entries_per_feed)
        if not feed_entries:
            continue
        for entry in feed_entries:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title or link in seen_links:
                continue
            domain = _normalize_domain(link)
            keywords = _extract_keywords(title)
            if not domain or len(keywords) < 2:
                continue
            collected.append(
                {
                    "title": title,
                    "link": link,
                    "summary": entry.get("summary", ""),
                    "domain": domain,
                    "keywords": keywords,
                }
            )
            seen_links.add(link)
            if len(collected) >= 120:  # safety limit
                return collected
    return collected


def _sentence_split(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    cleaned = []
    for sentence in sentences:
        s = re.sub(r"\s+", " ", sentence).strip()
        if len(s) >= 40:  # keep informative sentences only
            cleaned.append(s)
    return cleaned


def _get_image_from_url(url: str, timeout: int = 4) -> Optional[str]:
    try:
        resp = requests.get(url, timeout=timeout, headers=HTTP_HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for selector in [
            ("meta", {"property": "og:image"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"itemprop": "image"}),
        ]:
            tag = soup.find(*selector)
            if tag and tag.get("content"):
                candidate = tag["content"]
                if candidate.startswith("//"):
                    candidate = f"https:{candidate}"
                elif candidate.startswith("/"):
                    candidate = urljoin(resp.url, candidate)
                if candidate.startswith("http"):
                    return candidate
    except Exception:
        return None
    return None


def _extract_text_from_url(url: str, timeout: int = 3) -> str:
    try:
        resp = requests.get(url, timeout=timeout, headers=HTTP_HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(
            ["script", "style", "nav", "aside", "footer", "header", "button", "form", "iframe", "svg"]
        ):
            tag.decompose()
        selectors = [
            "article",
            "[role='article']",
            ".article-body",
            ".story-body",
            ".post-content",
            ".entry-content",
            "main",
            ".content",
        ]
        texts: List[str] = []
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            text = node.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 200:
                texts.append(text[:1000])
                break
        if texts:
            return " ".join(texts)
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            text = re.sub(r"(saved|share|follow|subscribe|newsletter).*?(\n|$)", "", text, flags=re.IGNORECASE)
            return text[:1000]
    except Exception:
        return ""
    return ""


def _build_key_points(texts: List[str], fallbacks: List[str], max_points: int = 5) -> List[str]:
    candidates: List[str] = []
    for text in texts:
        for sentence in _sentence_split(text):
            if len(candidates) >= max_points * 2:
                break
            candidates.append(sentence)
    if not candidates:
        for snippet in fallbacks:
            for sentence in _sentence_split(snippet):
                candidates.append(sentence)
                if len(candidates) >= max_points * 2:
                    break
            if candidates:
                break
    seen = set()
    key_points: List[str] = []
    for sentence in candidates:
        normalized = sentence.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        key_points.append(sentence)
        if len(key_points) >= max_points:
            break
    return key_points


def _select_source_cluster(entries: List[Dict], min_sources: int = 2, max_sources: int = 5) -> Optional[List[Dict]]:
    if not entries:
        return None
    shuffled = entries[:]
    random.shuffle(shuffled)
    for seed in shuffled:
        cluster = [seed]
        used_domains = {seed["domain"]}
        seed_keywords = set(seed["keywords"])
        seed_title = seed["title"].lower()
        for candidate in entries:
            if candidate is seed:
                continue
            if candidate["domain"] in used_domains:
                continue
            if candidate["link"] == seed["link"]:
                continue
            candidate_keywords = set(candidate["keywords"])
            overlap = seed_keywords & candidate_keywords
            title_overlap = (
                seed_title in candidate["title"].lower() or candidate["title"].lower() in seed_title
            )
            if len(overlap) >= 2 or title_overlap:
                cluster.append(candidate)
                used_domains.add(candidate["domain"])
            if len(cluster) >= max_sources:
                break
        if len(cluster) >= min_sources:
            return cluster
    return None


def _prepare_sources(cluster: List[Dict]) -> List[Dict]:
    prepared: List[Dict] = []
    for src in cluster:
        url = src["link"]
        domain = src["domain"]
        bias = _classify_bias(domain)
        raw_text = _extract_text_from_url(url)
        if not raw_text:
            cleaned_summary = BeautifulSoup(src.get("summary", ""), "html.parser").get_text(
                separator=" ", strip=True
            )
            raw_text = re.sub(r"\s+", " ", cleaned_summary).strip()
        prepared.append(
            {
                "url": url,
                "title": src.get("title"),
                "summary": src.get("summary", ""),
                "domain": domain,
                "bias": bias,
                "text": raw_text or "",
            }
        )
    return prepared


def fetch_multi_source_article(min_sources: int = 2) -> Optional[Dict]:
    """Provide a synthesized article built from multiple real sources."""
    entries = _collect_entries(max_feeds=10, entries_per_feed=12)
    cluster = _select_source_cluster(entries, min_sources=min_sources)
    if not cluster:
        return None

    prepared_sources = _prepare_sources(cluster)
    texts = [src["text"] for src in prepared_sources if src["text"]]
    fallback_summaries = [src.get("summary", "") for src in prepared_sources if src.get("summary")]

    key_points = _build_key_points(texts, fallback_summaries)

    if not key_points:
        # If we still failed to build points, skip this cluster
        return None

    overview_text = " ".join(texts) if texts else " ".join(fallback_summaries)
    overview_text = re.sub(r"\s+", " ", overview_text).strip()[:1400]

    summary_preview = " | ".join(key_points[:2]) if key_points else overview_text[:200]
    content = "Key Points:\n" + "\n".join(f"- {point}" for point in key_points)
    if overview_text:
        content += "\n\nCombined Overview:\n" + overview_text

    photo = None
    for src in prepared_sources[:3]:
        photo = _get_image_from_url(src["url"])
        if photo:
            break
    if not photo:
        photo = DEFAULT_IMAGE

    coverage = {"left": 0, "center": 0, "right": 0}
    for src in prepared_sources:
        coverage[src["bias"]] = coverage.get(src["bias"], 0) + 1

    primary_source = prepared_sources[0]

    return {
        "title": primary_source.get("title", "Untitled article"),
        "summary": summary_preview[:240],
        "content": content,
        "link": primary_source.get("url"),
        "photo": photo,
        "key_points": key_points,
        "overview": overview_text,
        "sources": [
            {
                "url": src["url"],
                "title": src["title"],
                "summary": src["summary"],
                "domain": src["domain"],
                "bias": src["bias"],
            }
            for src in prepared_sources
        ],
        "coverage_left": coverage["left"],
        "coverage_center": coverage["center"],
        "coverage_right": coverage["right"],
    }

