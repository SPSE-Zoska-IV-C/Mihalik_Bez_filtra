from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from extensions import db, bcrypt, login_manager, migrate
from models import Article
from routes.auth import auth_bp


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-this-secret-key"

db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)

app.register_blueprint(auth_bp)


 


 


@app.get("/")
def index():
    return redirect(url_for("list_articles"))


@app.get("/articles")
def list_articles():
    articles = Article.query.order_by(Article.date_posted.desc()).all()
    return render_template("articles.html", articles=articles)


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


if __name__ == "__main__":
    app.run(debug=True)

