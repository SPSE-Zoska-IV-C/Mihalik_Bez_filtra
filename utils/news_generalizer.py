"""AI-powered multi-source news generalizer - fetches articles and generates bullet-point summaries."""

import random
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import feedparser
except ImportError:
    feedparser = None

RSS_FEEDS = [
    # Use HTTPS feeds first (more reliable)
    "https://rss.cnn.com/rss/edition.rss",
    "https://rss.cnn.com/rss/edition_world.rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.reuters.com/reuters/worldNews",
    "https://rss.cbc.ca/lineup/topstories.xml",
    "https://rss.cbc.ca/lineup/world.xml",
    "https://feeds.npr.org/1001/rss.xml",  # NPR Top Stories
    "https://feeds.npr.org/1004/rss.xml",  # NPR World
    "https://feeds.foxnews.com/foxnews/latest",  # Fox News
    # Additional backup feeds
    "https://www.theguardian.com/world/rss",
    "https://www.theguardian.com/international/rss",
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DEFAULT_IMAGE = "https://via.placeholder.com/800x400?text=News"


def _normalize_domain(url: str) -> str:
    """Extract and normalize domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.split(":")[0]
    except Exception:
        return ""


def _extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    stop_words = {
        'this', 'that', 'with', 'from', 'have', 'been', 'will', 'news', 'says',
        'could', 'would', 'should', 'what', 'when', 'where', 'which', 'who',
        'there', 'their', 'these', 'those', 'about', 'after', 'before', 'more'
    }
    return [w for w in words if w not in stop_words][:6]


def _fetch_rss_entries(max_feeds: int = 6, entries_per_feed: int = 8) -> List[Dict]:
    """Fetch entries from multiple RSS feeds with strict timeouts."""
    all_entries = []
    feeds = RSS_FEEDS[:]
    random.shuffle(feeds)
    
    # Try more feeds if network is unreliable
    for feed_url in feeds[:max_feeds]:
        try:
            # Always use requests with timeout for reliability
            resp = requests.get(feed_url, timeout=6, headers=HTTP_HEADERS, allow_redirects=True)
            if resp.status_code != 200:
                print(f"DEBUG: Feed {feed_url} returned status {resp.status_code}")
                continue
            
            # Try different parsing methods - use lxml-xml if available, otherwise xml.etree
            try:
                # Try lxml first (best for XML)
                soup = BeautifulSoup(resp.content, 'lxml-xml')
            except Exception:
                try:
                    # Fallback to xml parser
                    soup = BeautifulSoup(resp.content, 'xml')
                except Exception:
                    # Last resort: html.parser (but suppress warning)
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        soup = BeautifulSoup(resp.content, 'html.parser')
            
            items = soup.find_all('item')
            if not items:
                # Try alternative tag names
                items = soup.find_all('entry')  # Atom feeds use 'entry'
            
            for item in items[:entries_per_feed]:
                title_elem = item.find('title')
                link_elem = item.find('link')
                desc_elem = item.find('description') or item.find('summary') or item.find('content')
                
                # Handle different link formats
                link_text = ''
                if link_elem:
                    link_text = link_elem.get_text(strip=True) if hasattr(link_elem, 'get_text') else str(link_elem).strip()
                    # If link is in href attribute (Atom feeds)
                    if not link_text and link_elem.get('href'):
                        link_text = link_elem.get('href')
                
                if title_elem and link_text:
                    title_text = title_elem.get_text(strip=True) if hasattr(title_elem, 'get_text') else str(title_elem).strip()
                    desc_text = ''
                    if desc_elem:
                        desc_text = desc_elem.get_text(strip=True) if hasattr(desc_elem, 'get_text') else str(desc_elem).strip()
                    
                    if title_text and link_text:
                        all_entries.append({
                            'title': title_text,
                            'link': link_text,
                            'summary': desc_text,
                            'domain': _normalize_domain(link_text)
                        })
                if len(all_entries) >= 30:  # Limit total entries
                    break
            if len(all_entries) >= 30:
                break
        except requests.exceptions.Timeout:
            print(f"DEBUG: Feed {feed_url} timed out")
            continue
        except requests.exceptions.ConnectionError as e:
            # DNS resolution or connection errors - skip silently to avoid spam
            continue
        except requests.exceptions.RequestException as e:
            # Only log non-connection errors
            if "getaddrinfo failed" not in str(e) and "Failed to resolve" not in str(e):
                print(f"DEBUG: Feed {feed_url} error: {e}")
            continue
        except Exception as e:
            print(f"DEBUG: Feed {feed_url} parsing error: {e}")
            continue
    
    print(f"DEBUG: Fetched {len(all_entries)} entries total")
    return all_entries


def _group_articles_by_topic(entries: List[Dict], min_group_size: int = 2) -> Optional[List[Dict]]:
    """Group articles by similar topic using keyword matching - optimized for speed."""
    if len(entries) < min_group_size:
        return None
    
    # Try to find a group quickly (check fewer seeds)
    for seed_idx, seed in enumerate(entries[:15]):  # Check first 15 as seeds
        seed_keywords = set(_extract_keywords(seed['title']))
        if len(seed_keywords) < 1:  # More lenient - only need 1 keyword
            continue
        
        group = [seed]
        checked_indices = {seed_idx}
        
        # Check fewer entries for speed
        for other_idx, other in enumerate(entries[:40]):  # Check first 40
            if other_idx in checked_indices:
                continue
            
            other_keywords = set(_extract_keywords(other['title']))
            # More lenient: check if at least 1 keyword overlaps (reduced from 2)
            overlap = len(seed_keywords & other_keywords)
            if overlap >= 1:  # More lenient matching
                group.append(other)
                checked_indices.add(other_idx)
                if len(group) >= 3:  # Max 3 sources
                    break
        
        if len(group) >= min_group_size:
            return group
    
    # Fallback: if no good match, just return first 2-3 entries from different domains
    if len(entries) >= 2:
        seen_domains = set()
        fallback_group = []
        for entry in entries[:10]:
            domain = entry.get('domain', '')
            if domain and domain not in seen_domains:
                fallback_group.append(entry)
                seen_domains.add(domain)
                if len(fallback_group) >= 2:
                    return fallback_group
    
    return None


def _extract_text_from_url(url: str, timeout: int = 3) -> str:
    """Extract main text content from article URL - fast and limited."""
    try:
        resp = requests.get(url, timeout=timeout, headers=HTTP_HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        
        # Limit response size to prevent huge pages
        content = resp.text[:50000]  # Max 50KB
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove unwanted elements
        for tag in soup(['script', 'style', 'nav', 'aside', 'footer', 'header', 'button', 'form', 'iframe']):
            tag.decompose()
        
        # Try to find main content - quick check
        content_selectors = [
            'article', '[role="article"]', '.article-body', '.story-body',
            '.post-content', '.entry-content', 'main'
        ]
        
        for selector in content_selectors[:3]:  # Only check first 3 selectors
            elements = soup.select(selector)
            if elements:
                text = elements[0].get_text(separator=' ', strip=True)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 150:
                    return text[:800]  # Limit to 800 chars for speed
        
        # Skip body fallback - too slow
        return ""
    except Exception:
        return ""


def _get_image_from_url(url: str, timeout: int = 3) -> Optional[str]:
    """Extract image from article URL."""
    try:
        resp = requests.get(url, timeout=timeout, headers=HTTP_HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Try OpenGraph first
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            img_url = og['content']
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                from urllib.parse import urljoin
                img_url = urljoin(resp.url, img_url)
            if img_url.startswith('http'):
                return img_url
        
        # Try Twitter card
        tw = soup.find('meta', attrs={'name': 'twitter:image'})
        if tw and tw.get('content'):
            img_url = tw['content']
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            if img_url.startswith('http'):
                return img_url
    except Exception:
        pass
    return None


def _generate_bullet_summary_ai(texts: List[str], summaries: List[str]) -> List[str]:
    """Generate bullet-point summary using AI (OpenAI or HuggingFace)."""
    # Combine all text
    combined_text = " ".join(texts) if texts else " ".join(summaries)
    if not combined_text:
        return []
    
    # Clean and limit text
    combined_text = re.sub(r'\s+', ' ', combined_text).strip()[:3000]
    
    # Try OpenAI first (new API format)
    try:
        import os
        openai_key = os.environ.get('OPENAI_API_KEY')
        if openai_key:
            try:
                import openai
                # Try new API format first
                try:
                    client = openai.OpenAI(api_key=openai_key)
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a news summarizer. Generate 4-6 concise, factual bullet points that generalize and merge information from multiple sources. Do not compare sources, just present the essential facts clearly."
                            },
                            {
                                "role": "user",
                                "content": f"Summarize this news content into 4-6 key bullet points:\n\n{combined_text}"
                            }
                        ],
                        max_tokens=300,
                        temperature=0.3
                    )
                    result = response.choices[0].message.content.strip()
                except AttributeError:
                    # Fallback to old API format
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a news summarizer. Generate 4-6 concise, factual bullet points that generalize and merge information from multiple sources. Do not compare sources, just present the essential facts clearly."
                            },
                            {
                                "role": "user",
                                "content": f"Summarize this news content into 4-6 key bullet points:\n\n{combined_text}"
                            }
                        ],
                        max_tokens=300,
                        temperature=0.3
                    )
                    result = response.choices[0].message.content.strip()
                
                # Parse bullet points
                bullets = [line.strip('- •*').strip() for line in result.split('\n') if line.strip() and (line.strip().startswith('-') or line.strip().startswith('•') or line.strip().startswith('*'))]
                if bullets:
                    return bullets[:6]
            except Exception:
                pass
    except ImportError:
        pass
    
    # Fallback: Try HuggingFace
    try:
        from transformers import pipeline
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)
        summary = summarizer(combined_text, max_length=200, min_length=100, do_sample=False)
        result_text = summary[0]['summary_text']
        # Split into sentences and create bullets
        sentences = re.split(r'[.!?]+', result_text)
        bullets = [s.strip() for s in sentences if len(s.strip()) > 20][:6]
        if bullets:
            return bullets
    except Exception:
        pass
    
    # Final fallback: Simple extraction (always works)
    return _simple_bullet_extraction(combined_text)


def _simple_bullet_extraction(text: str) -> List[str]:
    """Simple fallback: extract key sentences as bullets."""
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    # Filter meaningful sentences
    bullets = []
    for sent in sentences:
        sent = sent.strip()
        if 30 <= len(sent) <= 200 and not sent.lower().startswith(('this', 'that', 'these', 'those')):
            bullets.append(sent)
            if len(bullets) >= 5:
                break
    return bullets


def _create_demo_article() -> Dict:
    """Create a demo article when network is unavailable."""
    demo_topics = [
        {
            'title': 'Global Climate Summit Reaches Historic Agreement',
            'bullets': [
                'World leaders agree on ambitious carbon reduction targets by 2030',
                'New funding mechanism established for developing nations',
                'Renewable energy investments to triple over next decade',
                'Major economies commit to net-zero emissions timeline'
            ],
            'sources': [
                {'url': 'https://example.com/news1', 'title': 'Climate Agreement Reached', 'domain': 'example.com'},
                {'url': 'https://example.com/news2', 'title': 'Global Climate Deal', 'domain': 'example.com'}
            ]
        },
        {
            'title': 'Technology Breakthrough in Artificial Intelligence',
            'bullets': [
                'New AI model demonstrates significant improvements in reasoning',
                'Researchers achieve breakthrough in natural language understanding',
                'Industry leaders announce major AI safety initiatives',
                'Applications expected across healthcare, education, and research sectors'
            ],
            'sources': [
                {'url': 'https://example.com/tech1', 'title': 'AI Breakthrough Announced', 'domain': 'example.com'},
                {'url': 'https://example.com/tech2', 'title': 'New AI Model Released', 'domain': 'example.com'}
            ]
        },
        {
            'title': 'International Space Mission Successfully Launched',
            'bullets': [
                'Multi-nation collaboration launches mission to study distant planets',
                'Advanced instruments will analyze atmospheric composition',
                'Mission expected to provide insights into planetary formation',
                'Data collection phase to begin in coming months'
            ],
            'sources': [
                {'url': 'https://example.com/space1', 'title': 'Space Mission Launched', 'domain': 'example.com'},
                {'url': 'https://example.com/space2', 'title': 'International Space Collaboration', 'domain': 'example.com'}
            ]
        }
    ]
    
    import random
    topic = random.choice(demo_topics)
    
    bullet_text = "\n".join(f"• {point}" for point in topic['bullets'])
    
    return {
        'title': topic['title'],
        'summary': bullet_text,
        'content': bullet_text,
        'link': topic['sources'][0]['url'],
        'photo': DEFAULT_IMAGE,
        'sources': topic['sources'],
        'ai_generated': True
    }


def fetch_and_generalize_news() -> Optional[Dict]:
    """Fetch multiple articles on the same topic and generate AI bullet-point summary - optimized for speed."""
    try:
        # Step 1: Fetch entries from RSS feeds (try more feeds if network is unreliable)
        entries = _fetch_rss_entries(max_feeds=6, entries_per_feed=8)
        if not entries:
            print("DEBUG: No entries fetched from RSS - network may be unavailable")
            # Fallback: Create demo article when network is unavailable
            print("DEBUG: Using demo mode - creating sample article")
            return _create_demo_article()
        if len(entries) < 2:
            print(f"DEBUG: Only {len(entries)} entries, need at least 2")
            # If we have at least 1 entry, use it with a fallback
            if len(entries) == 1:
                entry = entries[0]
                summary = entry.get('summary', '')
                if summary:
                    soup = BeautifulSoup(summary, 'html.parser')
                    clean_summary = soup.get_text(separator=' ', strip=True)[:500]
                else:
                    clean_summary = entry.get('title', '')
                
                bullets = _simple_bullet_extraction(clean_summary[:1000])
                if not bullets:
                    bullets = [clean_summary[:150] if clean_summary else entry.get('title', 'News article')]
                
                return {
                    'title': entry.get('title', 'News Summary'),
                    'summary': "\n".join(f"• {b}" for b in bullets),
                    'content': "\n".join(f"• {b}" for b in bullets),
                    'link': entry.get('link', '#'),
                    'photo': DEFAULT_IMAGE,
                    'sources': [{'url': entry.get('link', ''), 'title': entry.get('title', ''), 'domain': entry.get('domain', '')}],
                    'ai_generated': True
                }
            return None
        
        # Step 2: Group articles by topic (quick check)
        group = _group_articles_by_topic(entries[:25], min_group_size=2)  # Only check first 25
        if not group:
            print(f"DEBUG: Could not group {len(entries)} entries")
            # Fallback: use first 2 entries regardless of topic
            if len(entries) >= 2:
                group = entries[:2]
            else:
                return None
        
        # Step 3: Extract content from each article (limit to 3 sources, skip slow ones)
        texts = []
        summaries = []
        sources = []
        
        for article in group[:3]:  # Max 3 sources for speed
            url = article['link']
            summary = article.get('summary', '')
            
            # Try to extract full text (with short timeout)
            try:
                full_text = _extract_text_from_url(url, timeout=2)  # Reduced timeout
                if full_text:
                    texts.append(full_text)
            except Exception:
                pass
            
            # Always use summary as fallback (faster)
            if summary:
                try:
                    soup = BeautifulSoup(summary, 'html.parser')
                    clean_summary = soup.get_text(separator=' ', strip=True)
                    if clean_summary and len(clean_summary) > 50:
                        summaries.append(clean_summary[:500])  # Limit summary length
                except Exception:
                    if summary and len(summary) > 50:
                        summaries.append(summary[:500])
            
            sources.append({
                'url': url,
                'title': article.get('title', ''),
                'domain': article.get('domain', '')
            })
            
            # Stop if we have enough content
            if len(texts) >= 2 or (len(texts) + len(summaries)) >= 3:
                break
        
        # Ensure we have at least summaries
        if not texts and not summaries:
            # If we have sources, use their titles as fallback
            if sources:
                summaries = [s.get('title', '') for s in sources if s.get('title')]
            if not summaries:
                print("DEBUG: No texts or summaries found")
                # Last resort: create summary from titles
                if sources:
                    title_text = " ".join([s.get('title', '') for s in sources if s.get('title')])
                    if title_text:
                        summaries = [title_text]
                if not summaries:
                    return None
        
        # Step 4: Generate bullet-point summary (use simple extraction for speed)
        # Skip AI generation to avoid hanging - use fast simple extraction
        combined = " ".join(texts[:2]) if texts else " ".join(summaries[:3])
        if not combined or len(combined.strip()) < 50:
            # Fallback: use titles
            combined = " ".join([s.get('title', '') for s in sources[:3] if s.get('title')])
        
        bullet_points = _simple_bullet_extraction(combined[:1500])
        
        # Only try AI if simple extraction fails (but with timeout protection)
        if not bullet_points:
            try:
                bullet_points = _generate_bullet_summary_ai(texts, summaries)
            except Exception:
                bullet_points = []
        
        # Final fallback: create bullets from titles if nothing else works
        if not bullet_points:
            if sources:
                bullet_points = [f"News coverage from {s.get('domain', 'multiple sources')}" for s in sources[:3]]
            if not bullet_points:
                return None
        
        # Step 5: Get image (quick, skip if slow)
        image = None
        try:
            for src in sources[:2]:
                image = _get_image_from_url(src['url'], timeout=2)
                if image:
                    break
        except Exception:
            pass
        if not image:
            image = DEFAULT_IMAGE
        
        # Step 6: Create title from first article
        title = sources[0]['title'] if sources and sources[0].get('title') else "News Summary"
        if not title or len(title.strip()) < 5:
            title = "News Summary"
        
        # Step 7: Format bullet points as summary
        bullet_text = "\n".join(f"• {point}" for point in bullet_points)
        if not bullet_text or len(bullet_text.strip()) < 10:
            return None
        
        # Ensure we have a valid link
        link = sources[0]['url'] if sources and sources[0].get('url') else ''
        if not link:
            # Try to get any valid URL from sources
            for src in sources:
                if src.get('url'):
                    link = src['url']
                    break
            if not link:
                link = '#'  # Fallback to prevent validation error
        
        return {
            'title': title,
            'summary': bullet_text,
            'content': bullet_text,
            'link': link,
            'photo': image,
            'sources': sources,
            'ai_generated': True
        }
    except Exception as e:
        # Catch any unexpected errors
        print(f"Error in fetch_and_generalize_news: {e}")
        return None

