from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    articles = db.relationship("Article", backref="author", lazy=True)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


def get_or_create_default_user() -> User:
    default_username = "admin"
    user = User.query.filter_by(username=default_username).first()
    if user is None:
        user = User(username=default_username, email="admin@example.com", password="changeme")
        db.session.add(user)
        db.session.commit()
    return user


@app.get("/")
def index():
    return redirect(url_for("list_articles"))


@app.get("/articles")
def list_articles():
    articles = Article.query.order_by(Article.date_posted.desc()).all()
    return render_template("articles.html", articles=articles)


@app.route("/add_article", methods=["GET", "POST"])
def add_article():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if title and content:
            author = get_or_create_default_user()
            article = Article(title=title, content=content, author=author)
            db.session.add(article)
            db.session.commit()
            return redirect(url_for("list_articles"))
    return render_template("add_article.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        get_or_create_default_user()
    app.run(debug=True)

