from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db, bcrypt, login_manager, migrate
from models import Article, User, ArticleReaction, Comment 
from routes.auth import auth_bp
from routes.articles import articles_bp
import os
app = Flask(__name__)

instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

db_path = os.path.join(instance_path, 'site.db')
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-this-secret-key"

db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)

app.register_blueprint(auth_bp)
app.register_blueprint(articles_bp)

with app.app_context():
    from sqlalchemy import text as _sql_text

    def _ensure_article_columns():
        try:
            cols = db.session.execute(_sql_text("PRAGMA table_info('article');")).fetchall()
            existing = {c[1] for c in cols}
            alter_statements = []
            if 'summary' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN summary TEXT")
            if 'photo' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN photo VARCHAR(500)")
            if 'source_url' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN source_url VARCHAR(500)")
            if 'ai_generated' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN ai_generated BOOLEAN NOT NULL DEFAULT 0")
            for stmt in alter_statements:
                db.session.execute(_sql_text(stmt))
            if alter_statements:
                db.session.commit()
        except Exception:
            # Best-effort; ignore if migrations will handle it
            pass

    try:
        from flask_migrate import upgrade as _upgrade

        result = db.session.execute(
            _sql_text("SELECT name FROM sqlite_master WHERE type='table' AND name='article';")
        ).first()
        if not result:
            _upgrade()
            # After creating schema on a fresh DB, ensure colum-ns exist too
            _ensure_article_columns()
        else:
            _ensure_article_columns()
    except Exception:
        try:
            from flask_migrate import upgrade as _upgrade_fallback
            _upgrade_fallback()
            _ensure_article_columns()
        except Exception:
            db.create_all()

@app.get("/")
def index():
    return redirect(url_for("list_articles"))


@app.get("/articles")
def list_articles():
    articles = Article.query.order_by(Article.date_posted.desc()).all()
    
    user_reactions = {}
    if current_user.is_authenticated:
        reactions = ArticleReaction.query.filter_by(user_id=current_user.id).all()
        for reaction in reactions:
            user_reactions[reaction.article_id] = reaction
    
    article_stats = {}
    for article in articles:
        like_count = ArticleReaction.query.filter_by(
            article_id=article.id, liked=True
        ).count()
        article_stats[article.id] = {"like_count": like_count}
    
    return render_template("articles.html", 
                         articles=articles, 
                         user_reactions=user_reactions,
                         article_stats=article_stats)


@app.post("/fetch_article")
@login_required
def fetch_article():
    rss_fetcher = None
    try:
        import utils.rss_fetcher as rss_fetcher  # type: ignore
    except Exception:
        rss_fetcher = None

    data = None
    if rss_fetcher:
        try:
            data = rss_fetcher.fetch_random_article()
        except RuntimeError:
            data = rss_fetcher.fetch_random_article_basic()
        except Exception:
            data = rss_fetcher.fetch_random_article_basic()

        if not data:
            data = rss_fetcher.fetch_random_article_basic()

    if not data:
        flash("Could not fetch an article right now. Please try again shortly.", "warning")
        return redirect(url_for("list_articles"))

    # Check duplicate by title or link
    existing = Article.query.filter(
        (Article.title == data['title']) | (Article.source_url == data['link'])
    ).first()
    if not existing:
        article = Article(
            title=data['title'],
            content=(data.get('content') or data.get('summary') or ''),
            summary=(data.get('summary') or ''),
            photo=(data.get('photo') or None),
            source_url=data.get('link'),
            ai_generated=False,
            author=current_user,
            date_posted=datetime.utcnow(),
        )
        db.session.add(article)
        db.session.commit()

        # Keep only latest 50 articles
        ids = [a.id for a in Article.query.order_by(Article.date_posted.desc()).all()]
        if len(ids) > 50:
            to_delete = ids[50:]
            if to_delete:
                Article.query.filter(Article.id.in_(to_delete)).delete(synchronize_session=False)
                db.session.commit()

    return redirect(url_for("list_articles"))

@app.route("/add_article", methods=["GET", "POST"])
@login_required
def add_article():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if title and content:
            article = Article(title=title, content=content, author=current_user)
            db.session.add(article)
            db.session.commit()
            return redirect(url_for("list_articles"))
    return render_template("add_article.html")


@app.route("/article/<int:article_id>")
def article_detail(article_id):
    """Display individual article with comments"""
    article = Article.query.get_or_404(article_id)
    
    user_reaction = None
    if current_user.is_authenticated:
        user_reaction = ArticleReaction.query.filter_by(
            article_id=article_id, user_id=current_user.id
        ).first()
    
    # pocet lajkov
    like_count = ArticleReaction.query.filter_by(
        article_id=article_id, liked=True
    ).count()
    
    # vratenie komentarov v poradi od datumu 
    comments = Comment.query.filter_by(article_id=article_id).order_by(Comment.date_posted.asc()).all()
    
    return render_template("article_detail.html",
                         article=article,
                         user_reaction=user_reaction,
                         like_count=like_count,
                         comments=comments)

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)

