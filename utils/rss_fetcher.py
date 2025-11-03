import random
from datetime import datetime
from typing import Optional, Dict

import feedparser
import requests
from bs4 import BeautifulSoup


CNN_FEEDS = [
    "http://rss.cnn.com/rss/edition.rss",
    "http://rss.cnn.com/rss/edition_world.rss",
    "http://rss.cnn.com/rss/edition_technology.rss",
]

DEFAULT_IMAGE = "https://via.placeholder.com/800x400?text=News"


def _extract_image_from_page(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Prefer OpenGraph image
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            return og['content']
        # Fallback to Twitter image
        tw = soup.find('meta', attrs={'name': 'twitter:image'})
        if tw and tw.get('content'):
            return tw['content']
        # Fallback: first large image
        img = soup.find('img')
        if img and img.get('src'):
            return img['src']
    except Exception:
        return None
    return None


def fetch_random_article() -> Optional[Dict]:
    feed_url = random.choice(CNN_FEEDS)
    parsed = feedparser.parse(feed_url)
    entries = parsed.entries or []
    if not entries:
        return None

    entry = random.choice(entries)
    title = getattr(entry, 'title', '').strip()
    summary = getattr(entry, 'summary', '').strip() or getattr(entry, 'description', '').strip()
    link = getattr(entry, 'link', '').strip()

    published = None
    if getattr(entry, 'published', None):
        try:
            published = datetime(*entry.published_parsed[:6])
        except Exception:
            published = None

    photo = None
    # Try media content if available
    media_content = getattr(entry, 'media_content', None)
    if media_content and isinstance(media_content, list) and media_content:
        url = media_content[0].get('url')
        if url:
            photo = url
    # Try media_thumbnail
    if not photo:
        thumbs = getattr(entry, 'media_thumbnail', None)
        if thumbs and isinstance(thumbs, list):
            url = thumbs[0].get('url')
            if url:
                photo = url
    # Try enclosure link
    if not photo and getattr(entry, 'links', None):
        for l in entry.links:
            if l.get('rel') == 'enclosure' and l.get('type', '').startswith('image') and l.get('href'):
                photo = l['href']
                break
    if not photo and link:
        photo = _extract_image_from_page(link)
    if not photo:
        photo = DEFAULT_IMAGE

    if not title or not link:
        return None

    return {
        'title': title,
        'summary': summary or '',
        'link': link,
        'published': published,
        'photo': photo or DEFAULT_IMAGE,
    }


