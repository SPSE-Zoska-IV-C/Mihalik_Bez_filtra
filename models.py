from datetime import datetime
import hashlib
from flask_login import UserMixin
from flask import url_for
from extensions import db, bcrypt, login_manager

@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)  # Nullable for OAuth users
    google_id = db.Column(db.String(255), unique=True, nullable=True)  # Google OAuth ID
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    profile_image = db.Column(db.String(500))

    articles = db.relationship("Article", backref="author", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)
    
    @staticmethod
    def create_google_user(google_id: str, email: str, name: str, picture: str = None):
        """Create or get user from Google OAuth"""
        try:
            # First, try to find user by google_id
            user = User.query.filter_by(google_id=google_id).first()
            
            if user:
                # User exists with this google_id, update profile image if needed
                if picture and not user.profile_image:
                    user.profile_image = picture
                db.session.commit()
                return user
            
            # Check if email already exists (user might have registered with email/password)
            user = User.query.filter_by(email=email).first()
            if user:
                # Link Google account to existing user
                # Check if google_id is already taken by another user
                existing_google_user = User.query.filter_by(google_id=google_id).first()
                if existing_google_user and existing_google_user.id != user.id:
                    raise ValueError(f"Google ID {google_id} is already linked to another account")
                
                user.google_id = google_id
                if picture:
                    user.profile_image = picture
                db.session.commit()
                return user
            
            # Create new user
            # Generate username from name
            username = name.lower().replace(' ', '_').replace('.', '_').replace('-', '_')[:80]
            # Remove any invalid characters
            username = ''.join(c for c in username if c.isalnum() or c == '_')
            if not username:
                # Fallback to email prefix if name is invalid
                username = email.split('@')[0].lower()[:80]
            
            # Ensure username is unique
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}_{counter}"[:80]
                counter += 1
                if counter > 1000:  # Safety limit
                    raise ValueError("Could not generate unique username")
            
            user = User(
                username=username,
                email=email,
                google_id=google_id,
                password_hash=None,  # No password for OAuth users
                profile_image=picture
            )
            db.session.add(user)
            db.session.commit()
            return user
            
        except Exception as e:
            db.session.rollback()
            print(f"Error in create_google_user: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def profile_image_url(self, size: int = 128) -> str:
        if self.profile_image:
            if self.profile_image.startswith("http"):
                return self.profile_image
            return url_for("static", filename=self.profile_image)
        seed_source = (self.email or self.username or "user").encode("utf-8", errors="ignore")
        seed = hashlib.md5(seed_source).hexdigest()
        return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}&radius=50&scale=110&size={size}"


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
    # Geolocation fields
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_name = db.Column(db.String(200), nullable=True)  # Human-readable location name
    
    reactions = db.relationship("ArticleReaction", backref="article", lazy=True, cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="article", lazy=True, cascade="all, delete-orphan")
    
    def _placeholder_seed(self) -> str:
        base = (self.title or str(self.id) or "news").encode("utf-8", errors="ignore")
        return hashlib.md5(base).hexdigest()[:16]

    def placeholder_image_url(self, width: int = 800, height: int = 450) -> str:
        seed = self._placeholder_seed()
        return f"https://picsum.photos/seed/{seed}/{width}/{height}"

    def cover_image_url(self, width: int = 800, height: int = 450) -> str:
        """
        Returns the stored photo if present, otherwise a deterministic placeholder.
        """
        if self.photo:
            return self.photo
        return self.placeholder_image_url(width, height)
        base = (self.title or str(self.id) or "news").encode("utf-8", errors="ignore")
        seed = hashlib.md5(base).hexdigest()[:16]
        return f"https://picsum.photos/seed/{seed}/{width}/{height}"

    def get_sources(self):
        """Parse sources from content JSON if it's a multi-source article"""
        import json
        try:
            data = json.loads(self.content)
            if isinstance(data, dict) and 'bullets' in data:
                return data
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
    
    article = db.relationship("Article", back_populates="comments", lazy=True)
    author = db.relationship("User", backref="comments", lazy=True)