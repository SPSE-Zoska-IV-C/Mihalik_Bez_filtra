"""
Multi-source news fetcher that aggregates articles from multiple sources
about the same topic, similar to Ground News.
"""
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
import re
from urllib.parse import urlparse
import json


class MultiSourceNewsFetcher:
    """Fetches news from multiple sources and groups by topic"""
    
    # Real RSS feeds from reputable news sources
    RSS_FEEDS = [
        "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News
        "https://rss.cnn.com/rss/edition.rss",  # CNN
        "https://feeds.reuters.com/reuters/topNews",  # Reuters
        "https://feeds.npr.org/1001/rss.xml",  # NPR
        "https://www.theguardian.com/world/rss",  # The Guardian
        "https://feeds.abcnews.com/abcnews/topstories",  # ABC News
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",  # NY Times
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
                
                for entry in feed.entries[:10]:  # Limit per feed
                    article = {
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': entry.get('summary', '') or entry.get('description', ''),
                        'published': entry.get('published', ''),
                        'source': source_name,
                        'source_url': feed_url
                    }
                    
                    # Try to get image from media tags or content
                    article['image'] = self._extract_image(entry)
                    
                    # Try to fetch full content
                    if article['link']:
                        article['content'] = self._fetch_article_content(article['link'])
                    
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
        return domain.replace('www.', '').split('.')[0].title()
    
    def _extract_image(self, entry) -> Optional[str]:
        """Extract image URL from RSS entry"""
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
        soup = BeautifulSoup(content, 'html.parser')
        content = soup.get_text()
        
        # Remove extra whitespace
        content = ' '.join(content.split())
        
        # If content is short enough, return as is
        if len(content) <= max_length:
            return content
        
        # Try to find a good sentence break
        sentences = re.split(r'[.!?]\s+', content)
        summary = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(summary) + len(sentence) + 2 <= max_length:
                summary += sentence + ". "
            else:
                break
        
        # If no good break found, just truncate at word boundary
        if not summary or len(summary) < 20:
            words = content[:max_length].split()
            summary = ' '.join(words[:-1]) + "..." if len(words) > 1 else content[:max_length] + "..."
        
        return summary.strip()
    
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
    
    def fetch_multi_source_article(self) -> Optional[Dict]:
        """Fetch and group articles from multiple sources about the same topic"""
        print("Fetching articles from multiple sources...")
        all_articles = self.fetch_all_feeds()
        
        if not all_articles:
            print("No articles fetched from any feed")
            return None
        
        print(f"Found {len(all_articles)} articles, grouping by topic...")
        groups = self.group_by_topic(all_articles, similarity_threshold=0.25)
        
        if not groups:
            print("No groups found with multiple sources")
            return None
        
        # Get the largest group (most sources covering the same story)
        largest_group = max(groups, key=len)
        
        if len(largest_group) < 2:
            print(f"Largest group only has {len(largest_group)} source(s)")
            return None
        
        print(f"Found story covered by {len(largest_group)} sources")
        
        # Create aggregated article
        main_article = largest_group[0]
        
        # Collect summaries from all sources
        source_summaries = []
        images = []
        seen_sources = set()  # Avoid duplicate sources
        
        for article in largest_group:
            source_name = article.get('source', 'Unknown')
            # Skip if we already have this source
            if source_name in seen_sources:
                continue
            seen_sources.add(source_name)
            
            summary = article.get('summary', '') or article.get('content', '')
            if summary:
                summarized = self._summarize_content(summary, max_length=150)
                if summarized:  # Only add if we have a summary
                    source_summaries.append({
                        'source': source_name,
                        'summary': summarized,
                        'url': article.get('link', '')
                    })
            
            if article.get('image'):
                images.append(article['image'])
        
        # Need at least 2 sources with summaries
        if len(source_summaries) < 2:
            print(f"Only {len(source_summaries)} sources with valid summaries")
            return None
        
        # Use first available image
        main_image = images[0] if images else None
        
        # Use the title from the main article
        title = main_article.get('title', 'Breaking News')
        if not title or len(title.strip()) < 10:
            title = f"News Story from {len(source_summaries)} Sources"
        
        return {
            'title': title,
            'content': json.dumps(source_summaries),  # Store as JSON
            'summary': f"Coverage from {len(source_summaries)} sources",
            'photo': main_image,
            'source_url': main_article.get('link', ''),
            'sources': source_summaries,
            'source_count': len(source_summaries)
        }

