from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db, bcrypt, login_manager, migrate
from models import Article, User, ArticleReaction, Comment 
from routes.auth import auth_bp
from routes.articles import articles_bp
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

db_path = os.path.join(instance_path, 'site.db')
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-this-secret-key"

# Google OAuth Configuration
app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "")
app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET", "")

# Google Gemini API Configuration
app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")

db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)

app.register_blueprint(auth_bp)
app.register_blueprint(articles_bp)

# Initialize OAuth
from routes.auth import init_oauth
init_oauth(app)

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

    def _ensure_user_columns():
        try:
            cols = db.session.execute(_sql_text("PRAGMA table_info('user');")).fetchall()
            existing = {c[1] for c in cols}
            if 'profile_image' not in existing:
                db.session.execute(_sql_text("ALTER TABLE user ADD COLUMN profile_image VARCHAR(500)"))
                db.session.commit()
            if 'google_id' not in existing:
                db.session.execute(_sql_text("ALTER TABLE user ADD COLUMN google_id VARCHAR(255)"))
                db.session.commit()
            # Make password_hash nullable for OAuth users
            # SQLite doesn't support ALTER COLUMN, so we need to recreate table
            password_hash_not_null = False
            for col in cols:
                if col[1] == 'password_hash' and col[3] == 0:  # 0 means NOT NULL
                    password_hash_not_null = True
                    break
            
            if password_hash_not_null:
                print("Converting password_hash to nullable for OAuth support...")
                # SQLite workaround: recreate table with nullable password_hash
                # Use TEXT instead of VARCHAR to ensure nullable works properly
                db.session.execute(_sql_text("""
                    CREATE TABLE user_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        username VARCHAR(80) NOT NULL UNIQUE,
                        email VARCHAR(120) NOT NULL UNIQUE,
                        password_hash TEXT,
                        google_id TEXT,
                        is_admin BOOLEAN NOT NULL,
                        date_created DATETIME NOT NULL,
                        profile_image TEXT
                    )
                """))
                db.session.execute(_sql_text("""
                    INSERT INTO user_new (id, username, email, password_hash, google_id, is_admin, date_created, profile_image)
                    SELECT id, username, email, password_hash, google_id, is_admin, date_created, profile_image
                    FROM user
                """))
                db.session.execute(_sql_text("DROP TABLE user"))
                db.session.execute(_sql_text("ALTER TABLE user_new RENAME TO user"))
                db.session.commit()
                print("password_hash is now nullable")
        except Exception as e:
            print(f"Error ensuring user columns: {e}")
            db.session.rollback()

    try:
        from flask_migrate import upgrade as _upgrade

        result = db.session.execute(
            _sql_text("SELECT name FROM sqlite_master WHERE type='table' AND name='article';")
        ).first()
        if not result:
            _upgrade()
            # After creating schema on a fresh DB, ensure colum-ns exist too
            _ensure_article_columns()
            _ensure_user_columns()
        else:
            _ensure_article_columns()
            _ensure_user_columns()
    except Exception:
        try:
            from flask_migrate import upgrade as _upgrade_fallback
            _upgrade_fallback()
            _ensure_article_columns()
            _ensure_user_columns()
        except Exception:
            db.create_all()

@app.get("/")
def index():
    return redirect(url_for("list_articles"))

@app.get("/map")
def map():
    return render_template("map.html")

@app.get("/articles")
def list_articles():
    filter_keyword = request.args.get('filter', '').lower()
    search_query = request.args.get('search', '').strip().lower()
    
    articles = Article.query.order_by(Article.date_posted.desc()).all()
    
    # Apply search query if specified (from navbar search bar)
    if search_query:
        filtered_articles = []
        for article in articles:
            title_lower = article.title.lower()
            summary_lower = (article.summary or '').lower()
            content_lower = article.content.lower()
            combined_text = f"{title_lower} {summary_lower} {content_lower}"
            
            if search_query in combined_text:
                filtered_articles.append(article)
        articles = filtered_articles
    
    # Apply filter if specified (from filter buttons)
    if filter_keyword:
        filtered_articles = []
        for article in articles:
            title_lower = article.title.lower()
            summary_lower = (article.summary or '').lower()
            content_lower = article.content.lower()
            combined_text = f"{title_lower} {summary_lower} {content_lower}"
            
            if filter_keyword in combined_text:
                filtered_articles.append(article)
        articles = filtered_articles
    
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
                         article_stats=article_stats,
                         current_filter=filter_keyword,
                         current_search=search_query)


@app.post("/fetch_article")
@login_required
def fetch_article():
    multi_source_fetcher = None
    try:
        from utils.multi_source_fetcher import MultiSourceNewsFetcher
        gemini_key = app.config.get("GEMINI_API_KEY", "")
        multi_source_fetcher = MultiSourceNewsFetcher(gemini_api_key=gemini_key)
    except Exception as e:
        print(f"Error importing multi_source_fetcher: {e}")
        import traceback
        traceback.print_exc()
        multi_source_fetcher = None

    # Get list of existing article titles to avoid fetching the same story
    existing_titles = [a.title for a in Article.query.with_entities(Article.title).all()]
    
    data = None
    if multi_source_fetcher:
        try:
            data = multi_source_fetcher.fetch_multi_source_article(exclude_titles=existing_titles)
            print(f"Fetched data: {data.get('title') if data else 'None'}")
        except Exception as e:
            print(f"Error fetching multi-source article: {e}")
            import traceback
            traceback.print_exc()
            data = None

    if not data:
        flash("Could not fetch an article right now. Please try again shortly.", "warning")
        return redirect(url_for("list_articles"))

    # Check for duplicate by title only
    existing = Article.query.filter(Article.title == data['title']).first()
    
    if not existing:
        try:
            # Ensure title and summary are not too long
            title = data['title'][:200] if len(data['title']) > 200 else data['title']
            summary = data.get('summary', '')[:500] if len(data.get('summary', '')) > 500 else data.get('summary', '')
            source_url = data.get('source_url', '')[:500] if len(data.get('source_url', '')) > 500 else data.get('source_url', '')
            photo = (data.get('photo') or None)
            if photo and len(photo) > 500:
                photo = photo[:500]
            
            article = Article(
                title=title,
                content=data['content'],  # JSON string with sources
                summary=summary,
                photo=photo,
                source_url=source_url,
                ai_generated=False,
                author=current_user,
                date_posted=datetime.utcnow(),
            )
            db.session.add(article)
            db.session.commit()
            print(f"Article saved: {article.id} - {article.title}")
            flash(f"Article '{article.title}' fetched successfully!", "success")

            # Keep only latest 50 articles
            ids = [a.id for a in Article.query.order_by(Article.date_posted.desc()).all()]
            if len(ids) > 50:
                to_delete = ids[50:]
                if to_delete:
                    Article.query.filter(Article.id.in_(to_delete)).delete(synchronize_session=False)
                    db.session.commit()
        except Exception as e:
            print(f"Error saving article: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            flash("Error saving article. Please try again.", "danger")
    else:
        flash("This article already exists.", "info")

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

