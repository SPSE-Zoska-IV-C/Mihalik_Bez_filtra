from datetime import datetime
from flask_login import UserMixin
from extensions import db, bcrypt, login_manager

@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    articles = db.relationship("Article", backref="author", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text)
    photo = db.Column(db.String(500))
    source_url = db.Column(db.String(500))
    ai_generated = db.Column(db.Boolean, nullable=False, default=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    
    reactions = db.relationship("ArticleReaction", backref="article", lazy=True, cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="article", lazy=True, cascade="all, delete-orphan")
    
    def get_sources(self):
        """Parse sources from content JSON if it's a multi-source article"""
        import json
        try:
            data = json.loads(self.content)
            # Check if it's the new format with bullets
            if isinstance(data, dict) and 'bullets' in data:
                return data
            # Check if it's the old format with source summaries
            elif isinstance(data, list) and all(isinstance(s, dict) and 'source' in s for s in data):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return None


class ArticleReaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    liked = db.Column(db.Boolean, default=False, nullable=False)
    date_reacted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('article_id', 'user_id'),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship to Article and User
    article = db.relationship("Article", back_populates="comments", lazy=True)
    author = db.relationship("User", backref="comments", lazy=True)