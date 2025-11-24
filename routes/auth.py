import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import User, Comment


auth_bp = Blueprint("auth", __name__, url_prefix="")


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
    return render_template("auth/register.html")


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
    return render_template("auth/login.html")


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

