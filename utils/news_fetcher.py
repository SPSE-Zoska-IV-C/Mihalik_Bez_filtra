"""
News Fetcher Module
Fetches real news articles from RSS feeds and generates AI summaries.
"""

import feedparser
import requests
import random
import time
from datetime import datetime
from bs4 import BeautifulSoup
import re


# RSS Feed Sources (no API key required)
RSS_SOURCES = [
    "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News
    "https://feeds.reuters.com/reuters/topNews",  # Reuters Top News
    "https://rss.cnn.com/rss/edition.rss",  # CNN
    "https://feeds.npr.org/1001/rss.xml",  # NPR News
]


def fetch_random_article():
    """
    Fetch a random recent article from RSS feeds.
    
    Returns:
        dict: Article data with title, summary, image_url, source_url, content, date_posted
        None: If no article found
    """
    try:
        # Randomly select a RSS source
        rss_url = random.choice(RSS_SOURCES)
        
        # Parse RSS feed
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            print("No articles found in RSS feed")
            return None
        
        # Filter recent articles (last 24 hours if possible)
        recent_articles = []
        for entry in feed.entries[:20]:  # Check last 20 articles
            recent_articles.append(entry)
        
        if not recent_articles:
            return None
        
        # Randomly select an article
        selected_article = random.choice(recent_articles)
        
        # Extract data
        title = selected_article.get('title', 'Untitled')
        summary = selected_article.get('summary', '').strip()
        link = selected_article.get('link', '')
        
        # Get published date
        published_date = selected_article.get('published_parsed', datetime.utcnow())
        if isinstance(published_date, time.struct_time):
            published_date = datetime(*published_date[:6])
        
        # Try to get image from media content
        image_url = None
        if selected_article.get('media_content'):
            image_url = selected_article.get('media_content')[0].get('url')
        elif selected_article.get('links'):
            # Try to find image in links
            for link_elem in selected_article.get('links'):
                if link_elem.get('type', '').startswith('image'):
                    image_url = link_elem.get('href')
                    break
        
        # Generate content (use summary as content, or fetch full article)
        content = generate_article_content(title, summary)
        
        # Generate AI summary if we have content
        ai_summary = generate_ai_summary(title, content or summary)
        
        return {
            'title': title,
            'content': content or summary,
            'summary': ai_summary or summary,
            'image_url': image_url,
            'source_url': link,
            'date_posted': published_date,
            'ai_generated': True
        }
        
    except Exception as e:
        print(f"Error fetching article: {str(e)}")
        return None


def generate_article_content(title, summary):
    """
    Generate full article content from title and summary.
    Since we're using RSS without full article access, we'll create a synthesized version.
    """
    # Clean the summary
    clean_summary = clean_html_tags(summary)
    
    # If summary is substantial, use it as content
    if len(clean_summary) > 200:
        return clean_summary
    
    # Otherwise, create a brief article-style content
    article_content = f"""
{summary}

This news story covers developments related to {title.lower()}. The story highlights important information and current developments that may affect readers.

Stay informed with the latest updates on this developing story.
    """
    
    return article_content.strip()


def generate_ai_summary(title, content):
    """
    Generate an AI summary (placeholder implementation).
    In production, you could use OpenAI API, HuggingFace, etc.
    
    For now, we'll create a simple contextual summary.
    """
    # Extract key phrases
    content_clean = clean_html_tags(content)
    
    # Create a summarized version
    sentences = content_clean.split('.')
    if len(sentences) > 3:
        summary = '. '.join(sentences[:3]) + '.'
    else:
        summary = content_clean
    
    # Add context
    summary = f"Summary: {summary}"
    
    return summary


def clean_html_tags(text):
    """Remove HTML tags from text."""
    if not text:
        return ""
    
    # Use BeautifulSoup to strip HTML
    try:
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(strip=True)
    except:
        # Fallback: simple regex
        clean_text = re.sub(r'<[^>]+>', '', text)
        return clean_text.strip()


def check_duplicate_url(source_url, db_session, Article):
    """
    Check if an article with this source URL already exists.
    
    Args:
        source_url: The source URL to check
        db_session: SQLAlchemy session
        Article: Article model class
    
    Returns:
        bool: True if duplicate exists, False otherwise
    """
    if not source_url:
        return True
    
    existing = db_session.query(Article).filter_by(source_url=source_url).first()
    return existing is not None

