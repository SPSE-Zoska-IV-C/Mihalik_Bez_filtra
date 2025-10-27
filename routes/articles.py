from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Article, ArticleReaction, Comment
from datetime import datetime

articles_bp = Blueprint("articles_bp", __name__)


@articles_bp.route("/article/<int:article_id>/like", methods=["POST"])
@login_required
def toggle_like(article_id):
    """Toggle like/unlike for the current user on an article"""
    article = Article.query.get_or_404(article_id)
    
    # Check if user already has a reaction to this article
    reaction = ArticleReaction.query.filter_by(
        article_id=article_id, user_id=current_user.id
    ).first()
    
    if reaction:
        # Toggle like status
        reaction.liked = not reaction.liked
    else:
        # Create new reaction
        reaction = ArticleReaction(
            article_id=article_id,
            user_id=current_user.id,
            liked=True
        )
        db.session.add(reaction)
    
    db.session.commit()
    
    # Get updated like count
    like_count = ArticleReaction.query.filter_by(
        article_id=article_id, liked=True
    ).count()
    
    return jsonify({
        "success": True,
        "liked": reaction.liked,
        "like_count": like_count,
        "article_id": article_id
    })


@articles_bp.route("/article/<int:article_id>/comment", methods=["POST"])
@login_required
def add_comment(article_id):
    """Add a user comment to an article"""
    article = Article.query.get_or_404(article_id)
    content = request.json.get("content", "").strip()
    
    if not content:
        return jsonify({"success": False, "error": "Comment cannot be empty"}), 400
    
    # Create new comment
    comment = Comment(
        article_id=article_id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "comment": {
            "id": comment.id,
            "content": comment.content,
            "author": current_user.username,
            "date_posted": comment.date_posted.strftime('%Y-%m-%d %H:%M')
        },
        "article_id": article_id
    })

