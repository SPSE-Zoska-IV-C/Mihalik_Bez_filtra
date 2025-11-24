"""
Multi-source news fetcher that aggregates articles from multiple sources
about the same topic, similar to Ground News.
"""
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter
import re
from urllib.parse import urlparse
import json


class MultiSourceNewsFetcher:
    """Fetches news from multiple sources and groups by topic"""
    
    # Real RSS feeds from reputable news sources - expanded list
    RSS_FEEDS = [
        # Major international news
        "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News
        "https://feeds.bbci.co.uk/news/world/rss.xml",  # BBC World
        "https://rss.cnn.com/rss/edition.rss",  # CNN
        "https://rss.cnn.com/rss/edition_world.rss",  # CNN World
        "https://feeds.reuters.com/reuters/topNews",  # Reuters Top
        "https://feeds.reuters.com/reuters/worldNews",  # Reuters World
        "https://feeds.npr.org/1001/rss.xml",  # NPR
        "https://www.theguardian.com/world/rss",  # The Guardian World
        "https://www.theguardian.com/international/rss",  # The Guardian International
        "https://feeds.abcnews.com/abcnews/topstories",  # ABC News
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",  # NY Times World
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",  # NY Times Home
        # Additional sources
        "https://feeds.washingtonpost.com/rss/world",  # Washington Post World
        "https://www.aljazeera.com/xml/rss/all.xml",  # Al Jazeera
        "https://feeds.feedburner.com/time/world",  # Time World
        "https://feeds.feedburner.com/time/topstories",  # Time Top Stories
        "https://www.nbcnews.com/rss",  # NBC News
        "https://feeds.cbsnews.com/CBSNewsMain",  # CBS News
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_all_feeds(self) -> List[Dict]:
        """Fetch articles from all RSS feeds"""
        all_articles = []
        
        for feed_url in self.RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                source_name = self._extract_source_name(feed_url)
                
                for entry in feed.entries[:50]:  # Get many more entries per feed to find overlapping stories
                    # Try multiple fields for summary/description
                    summary_text = (entry.get('summary', '') or 
                                   entry.get('description', '') or
                                   entry.get('content', [{}])[0].get('value', '') if isinstance(entry.get('content'), list) else '')
                    
                    article = {
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': summary_text,
                        'description': entry.get('description', ''),
                        'published': entry.get('published', ''),
                        'source': source_name,
                        'source_url': feed_url
                    }
                    
                    # Try to get image from media tags or content
                    article['image'] = self._extract_image(entry)
                    
                    # Don't fetch full content - use RSS summary only for speed
                    # article['content'] = ''  # Will use summary instead
                    
                    all_articles.append(article)
            except Exception as e:
                print(f"Error fetching feed {feed_url}: {e}")
                continue
        
        return all_articles
    
    def _extract_source_name(self, feed_url: str) -> str:
        """Extract source name from feed URL"""
        domain = urlparse(feed_url).netloc
        if 'bbc' in domain:
            return 'BBC News'
        elif 'cnn' in domain:
            return 'CNN'
        elif 'reuters' in domain:
            return 'Reuters'
        elif 'npr' in domain:
            return 'NPR'
        elif 'guardian' in domain:
            return 'The Guardian'
        elif 'abcnews' in domain:
            return 'ABC News'
        elif 'nytimes' in domain:
            return 'New York Times'
        elif 'washingtonpost' in domain or 'washington' in domain:
            return 'Washington Post'
        elif 'aljazeera' in domain:
            return 'Al Jazeera'
        elif 'time.com' in domain or 'feedburner.com/time' in domain:
            return 'Time'
        elif 'nbcnews' in domain:
            return 'NBC News'
        elif 'cbsnews' in domain:
            return 'CBS News'
        return domain.replace('www.', '').split('.')[0].title()
    
    def _extract_image(self, entry) -> Optional[str]:
        """Extract image URL from RSS entry, falling back to scraping the article page."""
        # Check media tags
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image'):
                    return media.get('url')
        
        # Check media_thumbnail
        if hasattr(entry, 'media_thumbnail'):
            for thumb in entry.media_thumbnail:
                return thumb.get('url')
        
        # Check summary/description for img tags
        summary = entry.get('summary', '') or entry.get('description', '')
        if summary:
            soup = BeautifulSoup(summary, 'html.parser')
            img = soup.find('img')
            if img and img.get('src'):
                return img.get('src')
        
        # Fallback: scrape Open Graph/Twitter image from the article page
        link = entry.get('link')
        if link:
            og_image = self._scrape_open_graph_image(link)
            if og_image:
                return og_image
        
        return None

    def _scrape_open_graph_image(self, url: str) -> Optional[str]:
        """Fetch the article page and return og:image/twitter:image if available."""
        try:
            resp = self.session.get(url, timeout=6)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            selectors = [
                ('meta', {'property': 'og:image'}),
                ('meta', {'name': 'og:image'}),
                ('meta', {'property': 'twitter:image'}),
                ('meta', {'name': 'twitter:image'}),
                ('meta', {'name': 'twitter:image:src'}),
            ]
            for tag, attrs in selectors:
                node = soup.find(tag, attrs=attrs)
                if node and node.get('content'):
                    return node['content']
            # fallback: first <img> with reasonable size
            img = soup.find('img')
            if img and img.get('src'):
                return img['src']
        except Exception:
            return None
        return None
    
    def _fetch_article_content(self, url: str) -> str:
        """Fetch full article content from URL"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            
            # Try to find main content
            content_selectors = [
                'article',
                '[role="main"]',
                '.article-body',
                '.content',
                'main',
                '.post-content'
            ]
            
            content = None
            for selector in content_selectors:
                content = soup.select_one(selector)
                if content:
                    break
            
            if not content:
                content = soup.find('body')
            
            if content:
                # Get text and clean it
                text = content.get_text(separator=' ', strip=True)
                # Limit length
                return text[:2000] if len(text) > 2000 else text
            
            return ''
        except Exception:
            return ''
    
    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles using simple word overlap"""
        words1 = set(re.findall(r'\w+', title1.lower()))
        words2 = set(re.findall(r'\w+', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        # Jaccard similarity
        return len(intersection) / len(union) if union else 0.0
    
    def _summarize_content(self, content: str, max_length: int = 150) -> str:
        """Create a simple summary from content"""
        if not content:
            return ""
        
        # Remove HTML tags if present
        try:
            soup = BeautifulSoup(content, 'html.parser')
            content = soup.get_text()
        except:
            # If parsing fails, just use the content as-is
            pass
        
        # Remove extra whitespace
        content = ' '.join(content.split())
        
        # If content is very short, return as is (might be a short summary already)
        if len(content) <= max_length:
            return content
        
        # Try to find a good sentence break
        sentences = re.split(r'[.!?]\s+', content)
        summary = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 5:  # Skip very short sentences
                continue
            if len(summary) + len(sentence) + 2 <= max_length:
                summary += sentence + ". "
            else:
                break
        
        # If no good break found, just truncate at word boundary
        if not summary or len(summary) < 15:
            words = content[:max_length].split()
            if len(words) > 1:
                summary = ' '.join(words[:-1]) + "..."
            else:
                summary = content[:max_length] + "..."
        
        return summary.strip()
    
    def _extract_generalized_bullets(self, source_summaries: List[Dict], max_bullets: int = 5) -> List[str]:
        """
        Extract overarching bullet points that summarize key angles across sources
        rather than attributing to a single outlet.
        """
        if not source_summaries:
            return []
        
        combined_texts = []
        for source in source_summaries:
            raw = source.get('summary', '')
            if not raw:
                continue
            soup = BeautifulSoup(raw, 'html.parser')
            cleaned = ' '.join(soup.get_text().split())
            if cleaned:
                combined_texts.append(cleaned)
        
        full_text = " ".join(combined_texts)
        if not full_text:
            return []
        
        sentences = re.split(r'[.!?]\s+', full_text)
        sentences = [s.strip() for s in sentences if 30 <= len(s.strip()) <= 200]
        if not sentences:
            return []
        
        words = re.findall(r'\b\w+\b', full_text.lower())
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was',
            'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may',
            'new', 'now', 'old', 'see', 'two', 'way', 'who', 'did', 'let', 'put', 'say',
            'she', 'too', 'use', 'from', 'into', 'that', 'with', 'have', 'this', 'they'
        }
        filtered_words = [w for w in words if len(w) > 3 and w not in stop_words]
        word_freq = Counter(filtered_words)
        
        scored_sentences = []
        for sentence in sentences:
            lower = sentence.lower()
            score = 0
            if any(char.isdigit() for char in sentence):
                score += 2
            if 60 <= len(sentence) <= 160:
                score += 1
            for word, freq in word_freq.items():
                if word in lower:
                    score += freq
            scored_sentences.append((score, sentence))
        
        scored_sentences.sort(reverse=True, key=lambda x: x[0])
        
        bullets: List[str] = []
        seen_word_sets: List[set] = []
        for _, sentence in scored_sentences:
            words_set = set(re.findall(r'\b\w+\b', sentence.lower()))
            if not words_set:
                continue
            duplicate = False
            for seen in seen_word_sets:
                overlap = len(words_set & seen)
                if overlap / (max(len(words_set), len(seen)) or 1) >= 0.55:
                    duplicate = True
                    break
            if duplicate:
                continue
            bullets.append(sentence)
            seen_word_sets.append(words_set)
            if len(bullets) >= max_bullets:
                break
        
        return bullets[:max_bullets]
    
    def group_by_topic(self, articles: List[Dict], similarity_threshold: float = 0.3) -> List[List[Dict]]:
        """Group articles by topic similarity"""
        groups = []
        used = set()
        
        for i, article1 in enumerate(articles):
            if i in used:
                continue
            
            group = [article1]
            used.add(i)
            
            for j, article2 in enumerate(articles[i+1:], start=i+1):
                if j in used:
                    continue
                
                similarity = self._calculate_similarity(article1['title'], article2['title'])
                if similarity >= similarity_threshold:
                    group.append(article2)
                    used.add(j)
            
            if len(group) >= 2:  # Only return groups with at least 2 sources
                groups.append(group)
        
        return groups
    
    def analyze_available_stories(self, exclude_titles: List[str] = None) -> List[Dict]:
        """First phase: Analyze and find which stories are covered by multiple sources"""
        if exclude_titles is None:
            exclude_titles = []
        
        print("Phase 1: Analyzing articles from multiple sources...")
        all_articles = self.fetch_all_feeds()
        
        if not all_articles:
            print("No articles fetched from any feed")
            return []
        
        print(f"Found {len(all_articles)} articles, grouping by topic...")
        groups = self.group_by_topic(all_articles, similarity_threshold=0.25)
        
        if not groups:
            print("No groups found with multiple sources")
            return []
        
        print(f"Found {len(groups)} story groups, checking which are new...")
        
        # Analyze each group to see if it's new and how many sources cover it
        available_stories = []
        for group in groups:
            main_title = group[0].get('title', '')
            source_count = len(set(a.get('source', 'Unknown') for a in group))
            
            # Check if this story is similar to existing ones
            is_new = True
            max_similarity = 0.0
            for excluded_title in exclude_titles:
                similarity = self._calculate_similarity(main_title, excluded_title)
                max_similarity = max(max_similarity, similarity)
                if similarity > 0.5:  # 50% similarity threshold - more lenient
                    is_new = False
                    break
            
            if is_new and source_count >= 2:
                available_stories.append({
                    'group': group,
                    'title': main_title,
                    'source_count': source_count,
                    'max_similarity': max_similarity
                })
                print(f"  ✓ NEW: '{main_title[:60]}...' ({source_count} sources)")
            else:
                if not is_new:
                    print(f"  ✗ SKIP: '{main_title[:60]}...' (similarity: {max_similarity:.2f}, already fetched)")
                else:
                    print(f"  ✗ SKIP: '{main_title[:60]}...' (only {source_count} sources)")
        
        # Sort by source count (most sources first), then by lowest similarity to existing
        available_stories.sort(key=lambda x: (-x['source_count'], x['max_similarity']))
        
        print(f"\nPhase 1 complete: Found {len(available_stories)} new stories covered by multiple sources")
        return available_stories
    
    def fetch_multi_source_article(self, exclude_titles: List[str] = None) -> Optional[Dict]:
        """Fetch and group articles from multiple sources about the same topic"""
        if exclude_titles is None:
            exclude_titles = []
        
        # Phase 1: Analyze which stories are available
        available_stories = self.analyze_available_stories(exclude_titles)
        
        if not available_stories:
            print("No new stories found that are covered by multiple sources")
            return None
        
        print(f"\nPhase 2: Fetching details for best story...")
        print(f"Selected: '{available_stories[0]['title'][:60]}...' ({available_stories[0]['source_count']} sources)")
        
        # Phase 2: Try to fetch the selected story, or try next best ones if it fails
        for story_idx, selected_story in enumerate(available_stories[:5]):  # Try up to 5 best stories
            current_group = selected_story['group']
            print(f"\nTrying story {story_idx + 1}: '{selected_story['title'][:60]}...'")
            
            # Create aggregated article
            main_article = current_group[0]
            
            # Collect summaries from all sources
            source_summaries = []
            images = []
            seen_sources = set()  # Avoid duplicate sources
            
            for article in current_group:
                source_name = article.get('source', 'Unknown')
                # Skip if we already have this source
                if source_name in seen_sources:
                    continue
                seen_sources.add(source_name)
                
                # Get summary from various possible fields
                summary = (article.get('summary', '') or 
                          article.get('description', '') or 
                          article.get('content', '') or
                          article.get('title', ''))
                
                if summary and len(summary.strip()) > 10:  # At least 10 characters
                    # Clean and summarize
                    summarized = self._summarize_content(summary, max_length=200)
                    if summarized and len(summarized.strip()) > 10:
                        source_summaries.append({
                            'source': source_name,
                            'summary': summarized,
                            'url': article.get('link', '')
                        })
                        print(f"  ✓ Added summary from {source_name}: {len(summarized)} chars")
                    else:
                        print(f"  ✗ Skipped {source_name}: summary too short after processing")
                else:
                    print(f"  ✗ Skipped {source_name}: no summary available")
                
                if article.get('image'):
                    images.append(article['image'])
            
            print(f"Total sources with valid summaries: {len(source_summaries)}")
            
            # If we have enough summaries, use this story
            if len(source_summaries) >= 2:
                print(f"✓ Successfully extracted {len(source_summaries)} summaries")
                break
            else:
                print(f"✗ Story {story_idx + 1} failed: only {len(source_summaries)} valid summaries, trying next...")
                source_summaries = []  # Reset for next iteration
                continue
        
        # Check if we found a valid story
        if len(source_summaries) < 2:
            print(f"✗ Could not find any story with at least 2 valid summaries after trying {min(5, len(available_stories))} stories")
            return None
        
        # We found a valid group, now extract bullet points
        print(f"Successfully found story with {len(source_summaries)} sources")
        
        # Extract generalized bullet points from all sources
        bullet_points = self._extract_generalized_bullets(source_summaries, max_bullets=5)
        
        if not bullet_points or len(bullet_points) < 2:
            print("Could not extract enough bullet points")
            return None
        
        # Store both bullet points and source info
        data_to_store = {
            'bullets': bullet_points,
            'sources': [{'source': s['source'], 'url': s['url']} for s in source_summaries]
        }
        
        # Use first available image
        main_image = images[0] if images else None
        
        # Use the title from the main article
        title = main_article.get('title', 'Breaking News')
        if not title or len(title.strip()) < 10:
            title = f"News Story from {len(source_summaries)} Sources"
        
        return {
            'title': title,
            'content': json.dumps(data_to_store),  # Store bullets and source info as JSON
            'summary': f"Coverage from {len(source_summaries)} sources",
            'photo': main_image,
            'source_url': main_article.get('link', ''),
            'bullets': bullet_points,
            'source_count': len(source_summaries)
        }

