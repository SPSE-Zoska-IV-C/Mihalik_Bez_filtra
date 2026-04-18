from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Article, ArticleReaction, Comment
from datetime import datetime

articles_bp = Blueprint("articles_bp", __name__)


@articles_bp.route("/article/<int:article_id>/like", methods=["POST"])
@login_required
def toggle_like(article_id):
    """Prepne like/odlike pre aktuálneho používateľa na článku."""
    # Uloží alebo aktualizuje reakciu používateľa na článok.
    article = Article.query.get_or_404(article_id)
    
    
    reaction = ArticleReaction.query.filter_by(
        article_id=article_id, user_id=current_user.id
    ).first()
    
    if reaction:
        
        reaction.liked = not reaction.liked
    else:
        
        reaction = ArticleReaction(
            article_id=article_id,
            user_id=current_user.id,
            liked=True
        )
        db.session.add(reaction)
    
    db.session.commit()
    
    
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
    """Pridá komentár k článku, Uloží komentár do databázy a vráti JSON odpoveď."""
    article = Article.query.get_or_404(article_id)
    content = request.json.get("content", "").strip()
    parent_id = request.json.get("parent_id", None)
    
    if not content:
        return jsonify({"success": False, "error": "Comment cannot be empty"}), 400
    
    
    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.article_id != article_id:
            return jsonify({"success": False, "error": "Invalid parent comment"}), 400
    
    
    comment = Comment(
        article_id=article_id,
        user_id=current_user.id,
        content=content,
        parent_id=parent_id if parent_id else None
    )
    db.session.add(comment)
    db.session.commit()
    
    
    reply_chain = comment.get_reply_chain()
    
    return jsonify({
        "success": True,
        "comment": {
            "id": comment.id,
            "content": comment.content,
            "author": current_user.username,
            "author_id": current_user.id,
            "date_posted": comment.date_posted.strftime('%Y-%m-%d %H:%M'),
            "parent_id": comment.parent_id,
            "reply_to": comment.parent.author.username if comment.parent else None,
            "reply_chain": reply_chain
        },
        "article_id": article_id
    })

