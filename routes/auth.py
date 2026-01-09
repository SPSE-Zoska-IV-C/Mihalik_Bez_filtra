import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from extensions import db
from models import User, Comment


auth_bp = Blueprint("auth", __name__, url_prefix="")

oauth = OAuth()


def init_oauth(app):
    """Initialize OAuth with Google"""
    oauth.init_app(app)
    
    # Set redirect URI to always use localhost (matches Google Console)
    redirect_uri = "http://localhost:5000/callback/google"
    
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        },
        # Set redirect_uri at registration level for consistency
        redirect_uri=redirect_uri
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("list_articles"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already registered.", "warning")
            return render_template("auth/register.html")

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. You can now log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", google_enabled=bool(current_app.config.get("GOOGLE_CLIENT_ID")))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("list_articles"))
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        # Try lookup by email first, then by username
        user = User.query.filter_by(email=identifier.lower()).first()
        if user is None:
            user = User.query.filter_by(username=identifier).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("list_articles"))
        flash("Invalid credentials.", "danger")
    return render_template("auth/login.html", google_enabled=bool(current_app.config.get("GOOGLE_CLIENT_ID")))


@auth_bp.route("/login/google")
def google_login():
    """Initiate Google OAuth login"""
    if not current_app.config.get("GOOGLE_CLIENT_ID") or not oauth:
        flash("Google login is not configured.", "danger")
        return redirect(url_for("auth.login"))
    
    # Use the redirect_uri from OAuth registration (always localhost:5000)
    # This ensures consistency with Google Console and callback
    redirect_uri = "http://localhost:5000/callback/google"
    
    print(f"Starting OAuth flow with redirect_uri: {redirect_uri}")
    print(f"Session ID: {session.get('_id', 'No session ID')}")
    print(f"SECRET_KEY set: {bool(current_app.config.get('SECRET_KEY'))}")
    
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/callback/google")
def google_callback():
    """Handle Google OAuth callback"""
    if not oauth:
        flash("Google login is not configured.", "danger")
        return redirect(url_for("auth.login"))
    
    try:
        print(f"Callback received - Request URL: {request.url}")
        print(f"Session ID: {session.get('_id', 'No session ID')}")
        print(f"State in request: {request.args.get('state', 'No state')}")
        
        # Authlib should automatically use the same redirect_uri from authorize_redirect
        # But we need to ensure the request URL matches what was used in authorize
        # Get the authorization token (Authlib handles state and redirect_uri automatically)
        token = oauth.google.authorize_access_token()
        print(f"Token received: {bool(token)}")
        
        # Clean up session
        session.pop('oauth_redirect_uri', None)
        
        # Get user info - Authlib should handle this automatically
        user_info = None
        
        # Method 1: Check if userinfo is already in token (some providers include it)
        if token and 'userinfo' in token:
            user_info = token.get('userinfo')
            print("User info from token")
        else:
            # Method 2: Fetch from userinfo endpoint (standard OAuth flow)
            try:
                resp = oauth.google.get('userinfo', token=token)
                if resp and resp.status_code == 200:
                    user_info = resp.json()
                    print("User info fetched from API")
                else:
                    print(f"Failed to fetch userinfo: status {resp.status_code if resp else 'None'}")
            except Exception as api_error:
                print(f"Error fetching userinfo from API: {api_error}")
                import traceback
                traceback.print_exc()
        
        if not user_info:
            print("No user info available")
            flash("Failed to get user information from Google.", "danger")
            return redirect(url_for("auth.login"))
        
        print(f"User info keys: {list(user_info.keys()) if isinstance(user_info, dict) else 'Not a dict'}")
        
        google_id = user_info.get('sub')
        email = user_info.get('email')
        # Try multiple fields for name
        name = (user_info.get('name') or 
                user_info.get('given_name') or 
                user_info.get('displayName') or
                (email.split('@')[0] if email else 'User'))
        picture = user_info.get('picture')
        
        # Ensure name is not empty
        if not name or not name.strip():
            name = email.split('@')[0] if email else 'User'
        
        print(f"Extracted - google_id: {google_id}, email: {email}, name: {name}, picture: {bool(picture)}")
        
        if not google_id or not email:
            print(f"Missing required fields - google_id: {bool(google_id)}, email: {bool(email)}")
            flash("Failed to get user information from Google.", "danger")
            return redirect(url_for("auth.login"))
        
        # Create or get user
        try:
            print(f"Attempting to create/get user with google_id={google_id}, email={email}, name={name}")
            user = User.create_google_user(google_id, email, name, picture)
            print(f"User created/found: id={user.id}, username={user.username}, email={user.email}")
            login_user(user)
            flash("Logged in successfully with Google!", "success")
            return redirect(url_for("list_articles"))
        except Exception as db_error:
            print(f"Database error: {type(db_error).__name__}: {str(db_error)}")
            import traceback
            traceback.print_exc()
            error_msg = str(db_error)
            if "UNIQUE constraint" in error_msg or "unique" in error_msg.lower():
                flash("An account with this email or Google ID already exists. Please try logging in instead.", "warning")
            else:
                flash(f"Failed to create/login user: {error_msg}. Please try again.", "danger")
            return redirect(url_for("auth.login"))
        
    except Exception as e:
        import traceback
        print(f"Google OAuth error: {e}")
        print(f"Error type: {type(e).__name__}")
        traceback.print_exc()
        flash(f"Failed to login with Google: {str(e)}. Please try again.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/settings")
@login_required
def settings():
    return render_template("auth/settings.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    comment_count = Comment.query.filter_by(user_id=current_user.id).count()
    if request.method == "POST":
        remove = request.form.get("remove_image")
        uploaded_file = request.files.get("profile_upload")
        message = "No changes made."

        def remove_old_file():
            if current_user.profile_image and not current_user.profile_image.startswith("http"):
                old_path = os.path.join(current_app.static_folder, current_user.profile_image)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass

        if remove:
            remove_old_file()
            current_user.profile_image = None
            message = "Profile picture removed."
        elif uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
            if ext not in allowed:
                flash("Unsupported file type. Please upload JPG, PNG, GIF, WEBP, or SVG.", "danger")
                return redirect(url_for("auth.profile"))

            upload_dir = os.path.join(current_app.static_folder, "uploads", "avatars")
            os.makedirs(upload_dir, exist_ok=True)
            new_filename = f"user_{current_user.id}_{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(upload_dir, new_filename)
            uploaded_file.save(file_path)

            remove_old_file()
            current_user.profile_image = os.path.join("uploads", "avatars", new_filename).replace("\\", "/")
            message = "Profile picture updated."

        db.session.commit()
        flash(message, "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html", comment_count=comment_count)

