from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db, bcrypt, login_manager, migrate
from models import Article, User, ArticleReaction, Comment, Discussion, DiscussionComment 
from routes.auth import auth_bp
from routes.articles import articles_bp
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

database_url = os.getenv("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    os.makedirs(instance_path, exist_ok=True)
    db_path = os.path.join(instance_path, 'site.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-this-secret-key"

app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "")
app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET", "")

app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")

db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)

app.register_blueprint(auth_bp)
app.register_blueprint(articles_bp)

from routes.auth import init_oauth
init_oauth(app)

with app.app_context():
    from sqlalchemy import text as _sql_text

    def _ensure_article_columns():
        """Zabezpečí, že tabuľka article má všetky potrebné stĺpce pre multi-source články."""
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
            if 'latitude' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN latitude REAL")
            if 'longitude' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN longitude REAL")
            if 'location_name' not in existing:
                alter_statements.append("ALTER TABLE article ADD COLUMN location_name VARCHAR(200)")
            for stmt in alter_statements:
                db.session.execute(_sql_text(stmt))
            if alter_statements:
                db.session.commit()
        except Exception:
            pass

    def _ensure_comment_columns():
        """Zabezpečí, že tabuľka comment má stĺpec parent_id pre vnorené komentáre."""
        try:
            cols = db.session.execute(_sql_text("PRAGMA table_info('comment');")).fetchall()
            existing = {c[1] for c in cols}
            if 'parent_id' not in existing:
                db.session.execute(_sql_text("ALTER TABLE comment ADD COLUMN parent_id INTEGER"))
                db.session.commit()
        except Exception:
            pass

    def _ensure_discussion_comment_columns():
        """Zabezpečí, že tabuľka discussion_comment má stĺpec parent_id pre vnorené komentáre v diskusiách."""
        try:
            cols = db.session.execute(_sql_text("PRAGMA table_info('discussion_comment');")).fetchall()
            existing = {c[1] for c in cols}
            if 'parent_id' not in existing:
                db.session.execute(_sql_text("ALTER TABLE discussion_comment ADD COLUMN parent_id INTEGER"))
                
                
                db.session.commit()
        except Exception:
            pass

    def _ensure_user_columns():
        """Zabezpečí, že tabuľka user má potrebné stĺpce pre OAuth a profilové obrázky, vrátane konverzie password_hash na nullable."""
        try:
            cols = db.session.execute(_sql_text("PRAGMA table_info('user');")).fetchall()
            existing = {c[1] for c in cols}
            if 'profile_image' not in existing:
                db.session.execute(_sql_text("ALTER TABLE user ADD COLUMN profile_image VARCHAR(500)"))
                db.session.commit()
            if 'google_id' not in existing:
                db.session.execute(_sql_text("ALTER TABLE user ADD COLUMN google_id VARCHAR(255)"))
                db.session.commit()
            
            
            password_hash_not_null = False
            for col in cols:
                if col[1] == 'password_hash' and col[3] == 0:  
                    password_hash_not_null = True
                    break
            
            if password_hash_not_null:
                print("Converting password_hash to nullable for OAuth support...")
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
            
            _ensure_article_columns()
            _ensure_user_columns()
        else:
            _ensure_article_columns()
            _ensure_user_columns()
            _ensure_comment_columns()
            _ensure_discussion_comment_columns()
    except Exception:
        try:
            from flask_migrate import upgrade as _upgrade_fallback
            _upgrade_fallback()
            _ensure_article_columns()
            _ensure_user_columns()
            _ensure_comment_columns()
            _ensure_discussion_comment_columns()
        except Exception:
            db.create_all()
            _ensure_article_columns()
            _ensure_user_columns()
            _ensure_comment_columns()
            _ensure_discussion_comment_columns()

    
    db.create_all()

@app.get("/")
def index():
    return redirect(url_for("list_articles"))

def extract_location_with_gemini(title: str, content: str, summary: str = "") -> dict:
    """Zistí miesto súvisiace s článkom pomocou Gemini API,Skúsi vyextrahovať primárnu geografickú lokalitu z textu článku."""
    #kontrola API kľúča
    gemini_key = app.config.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return {"latitude": None, "longitude": None, "location_name": None}
    # ijnicializacia gemini 
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        
        model = None
        for model_name in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-1.5-flash']:
            try:
                model = genai.GenerativeModel(model_name)
                break
            except:
                continue
        
        if not model:
            return {"latitude": None, "longitude": None, "location_name": None}
        #priprava textu clanku
        article_text = f"Title: {title}\n\n"
        if summary:
            article_text += f"Summary: {summary}\n\n"
        article_text += f"Content: {content[:2000]}"  
        #prompt
        prompt = f"""Analyze this news article and determine the primary geographic location where the event occurred or is most relevant.

{article_text}

Instructions:
- Identify the primary location (city, region, country) where this event took place or is most relevant
- If multiple locations are mentioned, choose the most important one
- If no specific location can be determined, return "null" for all fields
- Return ONLY a JSON object in this exact format (no other text):
{{
  "location_name": "City, Country" or null,
  "latitude": number or null,
  "longitude": number or null
}}

If you cannot determine a location, return:
{{
  "location_name": null,
  "latitude": null,
  "longitude": null
}}

JSON response:"""

        response = model.generate_content(prompt)
        response_text = response.text.strip()
        #Spracovanie odpovede 
        import json
        import re
        
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        try:
            location_data = json.loads(response_text)
            return {
                "latitude": location_data.get("latitude"),
                "longitude": location_data.get("longitude"),
                "location_name": location_data.get("location_name")
            }
        # Fallback parsing (ak JSON zlyha lebo nemame suradnice iba nazov)
        except json.JSONDecodeError:
            location_name_match = re.search(r'"location_name":\s*"([^"]+)"', response_text)
            if location_name_match:
                return {
                    "latitude": None,
                    "longitude": None,
                    "location_name": location_name_match.group(1)
                }
            return {"latitude": None, "longitude": None, "location_name": None}
            #Regex sa pokúša nájsť vzor "location_name": "..." a extrahovať len text z úvodzoviek.
    except Exception as e:
        print(f"Error extracting location with Gemini: {e}")
        return {"latitude": None, "longitude": None, "location_name": None}


def geocode_location(location_name: str) -> dict:
    """Prekonvertuje názov lokality na súradnice pomocou Nominatim (OpenStreetMap) získa zemepisnu šírku a dĺžku."""
    if not location_name:
        return {"latitude": None, "longitude": None}
    # Príprava requestu na Nominatim
    try:
        import requests
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": location_name,
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "BezFiltraNewsApp/1.0"
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        #Spracovanie odpovede
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return {
                    "latitude": float(data[0]["lat"]),
                    "longitude": float(data[0]["lon"])
                }
    except Exception as e:
        print(f"Error geocoding location: {e}")
    
    return {"latitude": None, "longitude": None}


@app.get("/map")
def map():
    return render_template("map.html")


@app.get("/api/articles/with-location")
def get_articles_with_location():
    """API endpoint na získanie článkov s polohou pre mapu,JSON so zoznamom článkov, ktoré majú súradnice"""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24) # cas po ktorom sa clanky vymazu
    #kriteria pre nacitanie clanku na mapu
    articles = Article.query.filter(
        Article.latitude.isnot(None),
        Article.longitude.isnot(None),
        Article.date_posted >= cutoff_time 
    ).order_by(Article.date_posted.desc()).limit(100).all()
    
    articles_data = []
    for article in articles:
        sources_data = article.get_sources()
        preview_text = article.summary or ""
        if not preview_text and sources_data and 'bullets' in sources_data:
            preview_text = sources_data['bullets'][0][:200] if sources_data['bullets'] else ""
        
        articles_data.append({
            "id": article.id,
            "title": article.title,
            "latitude": article.latitude,
            "longitude": article.longitude,
            "location_name": article.location_name,
            "preview": preview_text[:200] + "..." if len(preview_text) > 200 else preview_text,
            "photo": article.cover_image_url(300, 200),
            "date_posted": article.date_posted.strftime('%Y-%m-%d %H:%M')
        })
    
    return jsonify(articles_data)


@app.get("/articles")
def list_articles():
    """Načítava člannky z databazy."""
    filter_keyword = request.args.get('filter', '').lower()
    search_query = request.args.get('search', '').strip().lower()
    
    articles = Article.query.order_by(Article.date_posted.desc()).all()
    
    
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


@app.get("/discussions")
def discussions():
    """Zobrazí všetky diskusie, pripadne filtrovabe podla članku.
    Ak nie je špecifikovaný konkrétny článok, vytvorí sa jednoduché
    zoskupenie podľa priradeného článku (alebo None pre všeobecné
    diskusie). Šablóna potom iteruje cez skupiny."""
    # Načíta diskusie, prípadne podľa článku, a spracuje hierarchiu.
    article_id = request.args.get("article_id", type=int)
    article = Article.query.get_or_404(article_id) if article_id else None

    if article:
        discussions = Discussion.query.filter_by(article_id=article.id).order_by(Discussion.date_created.desc()).all()
        return render_template("discussions.html", discussions=discussions, article=article)

    all_discussions = Discussion.query.order_by(Discussion.date_created.desc()).all()
    groups = {}
    for d in all_discussions:
        key = d.article  
        groups.setdefault(key, []).append(d)

    grouped_list = []
    
    if None in groups:
        grouped_list.append((None, groups.pop(None)))
    
    for art, ds in groups.items():
        grouped_list.append((art, ds))

    return render_template("discussions.html", groups=grouped_list, article=None)


@app.route("/discussions/new", methods=["GET", "POST"])
@login_required
def new_discussion():
    """Vytvorí novú diskusiu, buď globálnu alebo viazanú na článok, formulár"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        question = request.form.get("question", "").strip()
        article_id_raw = request.form.get("article_id", "").strip()
        article_id = int(article_id_raw) if article_id_raw.isdigit() else None
        
        if not title or not question:
            flash("Title and question are required to create a discussion.", "danger")
            return redirect(request.referrer or url_for("new_discussion"))
        
        linked_article = None
        if article_id:
            linked_article = Article.query.get(article_id)
        
        discussion = Discussion(
            title=title[:200],
            question=question,
            article=linked_article,
            author=current_user
        )
        db.session.add(discussion)
        db.session.commit()
        flash("Discussion created successfully.", "success")
        return redirect(url_for("discussion_detail", discussion_id=discussion.id))
    
    article_id = request.args.get("article_id", type=int)
    article = Article.query.get_or_404(article_id) if article_id else None
    return render_template("discussion_new.html", article=article)


@app.post("/discussions/<int:discussion_id>/delete")
@login_required
def delete_discussion(discussion_id: int):
    """Odstráni diskusiu. Iba autor alebo admin ju môže zmazať."""
    discussion = Discussion.query.get_or_404(discussion_id)
    if discussion.user_id != current_user.id and not current_user.is_admin:
        flash("You are not allowed to delete that discussion.", "danger")
        return redirect(url_for("discussion_detail", discussion_id=discussion.id))

    
    db.session.delete(discussion)
    db.session.commit()
    flash("Discussion deleted.", "success")
    return redirect(url_for("discussions"))


@app.get("/discussions/<int:discussion_id>")
def discussion_detail(discussion_id: int):
    """Zobrazí detail diskusie spolu s komentármi v stromovej štruktúre."""
    discussion = Discussion.query.get_or_404(discussion_id)
    
    
    all_comments = DiscussionComment.query.filter_by(
        discussion_id=discussion.id
    ).order_by(DiscussionComment.date_posted.asc()).all()

    
    comments_dict = {c.id: c for c in all_comments}
    for c in all_comments:
        if c.parent_id and c.parent_id in comments_dict:
            parent = comments_dict[c.parent_id]
            if not hasattr(parent, '_replies'):
                parent._replies = []
            parent._replies.append(c)

    top_level_comments = [c for c in all_comments if c.parent_id is None]

    return render_template(
        "discussion_detail.html",
        discussion=discussion,
        comments=top_level_comments,
    )


@app.post("/discussions/<int:discussion_id>/comment")
@login_required
def add_discussion_comment(discussion_id: int):
    """Pridá komentár alebo odpoveď do diskusie.
    Podporuje klasické odošlé formuláre aj AJAX JSON volania pre
    inline odpovede. ``parent_id`` môže vytvoriť vnorenú odpoveď.
    """
    discussion = Discussion.query.get_or_404(discussion_id)

    
    if request.is_json:
        data = request.get_json()
        content = (data.get("content", "") or "").strip()
        parent_id = data.get("parent_id")
    else:
        content = (request.form.get("content", "") or "").strip()
        parent_id = request.form.get("parent_id")
    
    if not content:
        msg = "Comment cannot be empty."
        if request.is_json:
            return {"success": False, "error": msg}, 400
        flash(msg, "danger")
        return redirect(url_for("discussion_detail", discussion_id=discussion.id))
    
    comment = DiscussionComment(
        discussion=discussion,
        author=current_user,
        content=content
    )
    if parent_id:
        try:
            pid = int(parent_id)
            parent = DiscussionComment.query.get(pid)
            if parent and parent.discussion_id == discussion.id:
                comment.parent = parent
        except (ValueError, TypeError):
            pass
    db.session.add(comment)
    db.session.commit()
    
    if request.is_json:
        return {"success": True}

    flash("Comment added to discussion.", "success")
    return redirect(url_for("discussion_detail", discussion_id=discussion.id))

@app.post("/fetch_article")
@login_required
def fetch_article():
    """Načíta nový článok z viacerých zdrojov a uloží ho do databázy."""
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

    
    existing = Article.query.filter(Article.title == data['title']).first()
    
    if not existing:
        try:
            
            title = data['title'][:200] if len(data['title']) > 200 else data['title']
            summary = data.get('summary', '')[:500] if len(data.get('summary', '')) > 500 else data.get('summary', '')
            source_url = data.get('source_url', '')[:500] if len(data.get('source_url', '')) > 500 else data.get('source_url', '')
            photo = (data.get('photo') or None)
            if photo and len(photo) > 500:
                photo = photo[:500]
            
            
            print("Extracting location from article...")
            location_data = extract_location_with_gemini(title, data['content'], summary)
            
            
            if location_data.get("location_name") and not location_data.get("latitude"):
                print(f"Geocoding location: {location_data['location_name']}")
                geocode_result = geocode_location(location_data["location_name"])
                location_data["latitude"] = geocode_result.get("latitude")
                location_data["longitude"] = geocode_result.get("longitude")
            
            article = Article(
                title=title,
                content=data['content'],  
                summary=summary,
                photo=photo,
                source_url=source_url,
                author=current_user,
                date_posted=datetime.now(timezone.utc),
                latitude=location_data.get("latitude"),
                longitude=location_data.get("longitude"),
                location_name=location_data.get("location_name")
            )
            db.session.add(article)
            db.session.commit()
            print(f"Article saved: {article.id} - {article.title}")
            if location_data.get("location_name"):
                print(f"Location: {location_data['location_name']} ({location_data.get('latitude')}, {location_data.get('longitude')})")
            flash(f"Article '{article.title}' fetched successfully!", "success")

            
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


@app.route("/article/<int:article_id>")
def article_detail(article_id):
    """Zobrazovanie detailu clanku."""
    article = Article.query.get_or_404(article_id)
    
    user_reaction = None
    if current_user.is_authenticated:
        user_reaction = ArticleReaction.query.filter_by(
            article_id=article_id, user_id=current_user.id
        ).first()
    
    like_count = ArticleReaction.query.filter_by(
        article_id=article_id, liked=True
    ).count()
    
    top_level_comments = Comment.query.filter_by(
        article_id=article_id, 
        parent_id=None
    ).order_by(Comment.date_posted.asc()).all()
    
    all_comments = Comment.query.filter_by(article_id=article_id).order_by(Comment.date_posted.asc()).all()
    
    comments_dict = {c.id: c for c in all_comments}
    for comment in all_comments:
        if comment.parent_id and comment.parent_id in comments_dict:
            parent = comments_dict[comment.parent_id]
            if not hasattr(parent, '_replies'):
                parent._replies = []
            parent._replies.append(comment)
    
    comments = top_level_comments
    
    return render_template("article_detail.html",
                         article=article,
                         user_reaction=user_reaction,
                         like_count=like_count,
                         comments=comments)

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)

