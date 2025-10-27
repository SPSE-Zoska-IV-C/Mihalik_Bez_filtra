"""
AI Comment Generator
A utility module for generating AI-powered comments on articles.
"""

import re
import random


def generate_ai_comment(article_title: str, article_content: str) -> str:
    """
    Generate an AI-powered comment based on the article title and content.
    
    This is a placeholder implementation that simulates AI behavior.
    In production, this could be replaced with an actual AI API call
    (OpenAI, HuggingFace, etc.)
    
    Args:
        article_title: The title of the article
        article_content: The content of the article
        
    Returns:
        A generated comment string
    """
    # Extract keywords from the title
    title_words = re.findall(r'\w+', article_title.lower())
    main_keywords = [w for w in title_words if len(w) > 4][:3]
    
    # Generate contextual comment templates
    comment_templates = [
        f"Interesting perspective on {article_title.lower()}! This raises important points worth considering.",
        f"This article about '{article_title}' provides valuable insights. Well-articulated thoughts on the topic.",
        f"Great read! The discussion on {article_title.lower()} is particularly relevant in today's context.",
        f"Thought-provoking content. The article touches on some key aspects of {article_title.lower()}.",
        f"Appreciate the depth of analysis here. {article_title} is an important topic that deserves more attention.",
        f"Compelling arguments presented. This perspective on {article_title.lower()} adds to the conversation.",
        f"Well-written piece on {article_title.lower()}. The points raised here merit further discussion.",
        f"Insightful read! The article offers a fresh angle on {article_title.lower()}.",
    ]
    
    # Generate a random contextual response
    comment = random.choice(comment_templates)
    
    # For longer articles, add an additional note
    if len(article_content) > 500:
        comment += " The detailed analysis provides a comprehensive understanding of the subject matter."
    
    return comment

