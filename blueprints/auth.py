# ==============================================================================
# FILE: blueprints/auth.py
# Auth Blueprint: login, register, verify, reset password, my-account
# ==============================================================================

import os
import secrets as _secrets
import traceback
from datetime import datetime
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash

from models import User, get_db, UserSubscription, UsageLimits, Classroom
from blueprints.helpers import (
    login_required, is_premium_user,
    _build_external_url, APP_BASE_URL,
    send_verify_email, send_reset_password_email,
)

auth_bp = Blueprint("auth", __name__)

# --- Cloudflare Turnstile CAPTCHA ---
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()

# --- Google OAuth ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def _verify_turnstile(token: str) -> bool:
    """Verify Cloudflare Turnstile token. Returns True if valid or if Turnstile is not configured."""
    if not TURNSTILE_SECRET_KEY:
        # Turnstile not configured — skip verification (dev mode)
        return True
    if not token:
        return False
    try:
        resp = http_requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": TURNSTILE_SECRET_KEY, "response": token},
            timeout=10,
        )
        result = resp.json()
        return result.get("success", False)
    except Exception as e:
        print(f"[TURNSTILE ERROR] {e}")
        return False


# ==============================================================================
# Landing
# ==============================================================================
@auth_bp.route("/")
def landing():
    return render_template("landing.html")


# ==============================================================================
# Register
# ==============================================================================
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # --- Turnstile CAPTCHA verification ---
        turnstile_token = request.form.get("cf-turnstile-response", "")
        if TURNSTILE_SECRET_KEY and not _verify_turnstile(turnstile_token):
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e27\u0e48\u0e32\u0e04\u0e38\u0e13\u0e44\u0e21\u0e48\u0e43\u0e0a\u0e48\u0e1a\u0e2d\u0e17 (CAPTCHA failed)", "error")
            return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)

        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        confirm = (request.form.get("confirm_password") or "").strip()

        if not email or not password:
            flash("Email and password required.", "error")
            return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)
        if User.get_by_email(email):
            flash("Email already registered.", "error")
            return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)

        user = User.create(email, password, "teacher")
        token = (user or {}).get("verify_token")
        if not token:
            flash("Could not create verification token. Please try again.", "error")
            return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)

        verify_path = url_for("auth.verify_email", token=token)
        verify_link = _build_external_url(verify_path) if APP_BASE_URL else url_for("auth.verify_email", token=token, _external=True)

        try:
            send_verify_email(email, verify_link)
        except Exception:
            traceback.print_exc()
            flash("\u0e2a\u0e48\u0e07\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e44\u0e21\u0e48\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e25\u0e2d\u0e07\u0e43\u0e2b\u0e21\u0e48\u0e20\u0e32\u0e22\u0e2b\u0e25\u0e31\u0e07", "error")
            return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)

        return render_template("verify_sent.html", email=email)

    return render_template("register.html", turnstile_site_key=TURNSTILE_SITE_KEY)


# ==============================================================================
# Verify Email
# ==============================================================================
@auth_bp.route("/verify/<token>")
def verify_email(token):
    user = User.get_by_verify_token(token)
    if not user:
        flash("\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07\u0e2b\u0e23\u0e37\u0e2d\u0e16\u0e39\u0e01\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19\u0e44\u0e1b\u0e41\u0e25\u0e49\u0e27", "error")
        return redirect(url_for("auth.login"))

    try:
        exp = user.get("verify_expires")
        if exp:
            exp_dt = datetime.fromisoformat(exp)
            if datetime.utcnow() > exp_dt:
                flash("\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2b\u0e21\u0e14\u0e2d\u0e32\u0e22\u0e38 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e2a\u0e21\u0e31\u0e04\u0e23\u0e43\u0e2b\u0e21\u0e48\u0e2b\u0e23\u0e37\u0e2d\u0e02\u0e2d\u0e2a\u0e48\u0e07\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07", "error")
                return redirect(url_for("auth.login"))
    except Exception:
        pass

    User.mark_verified(user["id"])
    flash("\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08! \u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e02\u0e49\u0e32\u0e2a\u0e39\u0e48\u0e23\u0e30\u0e1a\u0e1a", "success")
    return redirect(url_for("auth.login"))


# ==============================================================================
# Login / Logout
# ==============================================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        next_url = request.form.get("next") or next_url
        user = User.get_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            if not int(user.get("is_verified") or 0):
                flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e01\u0e48\u0e2d\u0e19\u0e40\u0e02\u0e49\u0e32\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19 (\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e43\u0e19\u0e01\u0e25\u0e48\u0e2d\u0e07\u0e08\u0e14\u0e2b\u0e21\u0e32\u0e22)", "error")
                return redirect(url_for("auth.login"))
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["role"] = user["role"]
            session["display_name"] = user.get("display_name") or ""
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html", next_url=next_url)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.landing"))


# ==============================================================================
# Google OAuth Login
# ==============================================================================
@auth_bp.route("/auth/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        flash("Google Login \u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e44\u0e14\u0e49\u0e15\u0e31\u0e49\u0e07\u0e04\u0e48\u0e32", "error")
        return redirect(url_for("auth.login"))

    # Save next URL for after login
    next_url = request.args.get("next", "")
    if next_url and next_url.startswith("/"):
        session["login_next_url"] = next_url

    # Build callback URL
    callback_url = _build_external_url(url_for("auth.google_callback"))

    # Generate state to prevent CSRF
    state = _secrets.token_urlsafe(32)
    session["google_oauth_state"] = state

    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@auth_bp.route("/auth/google/callback")
def google_callback():
    error = request.args.get("error")
    if error:
        flash(f"Google Login \u0e16\u0e39\u0e01\u0e22\u0e01\u0e40\u0e25\u0e34\u0e01: {error}", "error")
        return redirect(url_for("auth.login"))

    code = request.args.get("code")
    state = request.args.get("state")

    # Verify state
    if not state or state != session.pop("google_oauth_state", None):
        flash("\u0e40\u0e01\u0e34\u0e14\u0e02\u0e49\u0e2d\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14 (state mismatch)", "error")
        return redirect(url_for("auth.login"))

    if not code:
        flash("Google Login \u0e25\u0e49\u0e21\u0e40\u0e2b\u0e25\u0e27", "error")
        return redirect(url_for("auth.login"))

    callback_url = _build_external_url(url_for("auth.google_callback"))

    # Exchange code for tokens
    try:
        token_resp = http_requests.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        }, timeout=15)
        token_data = token_resp.json()
    except Exception as e:
        print(f"[GOOGLE OAuth] Token exchange error: {e}")
        flash("Google Login \u0e25\u0e49\u0e21\u0e40\u0e2b\u0e25\u0e27", "error")
        return redirect(url_for("auth.login"))

    access_token = token_data.get("access_token")
    if not access_token:
        print(f"[GOOGLE OAuth] No access_token: {token_data}")
        flash("Google Login \u0e25\u0e49\u0e21\u0e40\u0e2b\u0e25\u0e27", "error")
        return redirect(url_for("auth.login"))

    # Get user info
    try:
        user_resp = http_requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        user_info = user_resp.json()
    except Exception as e:
        print(f"[GOOGLE OAuth] Userinfo error: {e}")
        flash("Google Login \u0e25\u0e49\u0e21\u0e40\u0e2b\u0e25\u0e27", "error")
        return redirect(url_for("auth.login"))

    email = (user_info.get("email") or "").strip().lower()
    if not email:
        flash("\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e14\u0e36\u0e07\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e08\u0e32\u0e01 Google", "error")
        return redirect(url_for("auth.login"))

    display_name = user_info.get("name") or ""

    # Find or create user
    user = User.create_or_get_google_user(email, display_name)

    # Set session
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    session["role"] = user.get("role", "teacher")
    session["display_name"] = user.get("display_name") or display_name

    next_url = session.pop("login_next_url", "")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("dashboard"))


# ==============================================================================
# Resend Verification
# ==============================================================================
@auth_bp.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()

        if not email:
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e01\u0e23\u0e2d\u0e01\u0e2d\u0e35\u0e40\u0e21\u0e25", "error")
            return render_template("resend_verification.html")

        user = User.get_by_email(email)

        if not user:
            flash("\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e19\u0e35\u0e49\u0e43\u0e19\u0e23\u0e30\u0e1a\u0e1a", "error")
            return render_template("resend_verification.html")

        if user.get("is_verified"):
            flash("\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e19\u0e35\u0e49\u0e44\u0e14\u0e49\u0e23\u0e31\u0e1a\u0e01\u0e32\u0e23\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e41\u0e25\u0e49\u0e27 \u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e40\u0e02\u0e49\u0e32\u0e2a\u0e39\u0e48\u0e23\u0e30\u0e1a\u0e1a\u0e44\u0e14\u0e49\u0e40\u0e25\u0e22", "success")
            return redirect(url_for("auth.login"))

        token = User.refresh_verify_token(user["id"])
        if token:
            verify_path = url_for("auth.verify_email", token=token)
            verify_link = _build_external_url(verify_path) if APP_BASE_URL else url_for("auth.verify_email", token=token, _external=True)
            try:
                send_verify_email(email, verify_link)
                flash("\u0e2a\u0e48\u0e07\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e43\u0e2b\u0e21\u0e48\u0e44\u0e1b\u0e17\u0e35\u0e48\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e02\u0e2d\u0e07\u0e04\u0e38\u0e13\u0e41\u0e25\u0e49\u0e27 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e01\u0e25\u0e48\u0e2d\u0e07\u0e08\u0e14\u0e2b\u0e21\u0e32\u0e22", "success")
            except Exception as e:
                print(f"[EMAIL ERROR] {e}")
                flash("\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e2a\u0e48\u0e07\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e44\u0e14\u0e49 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e25\u0e2d\u0e07\u0e43\u0e2b\u0e21\u0e48\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07", "error")

        return redirect(url_for("auth.login"))

    return render_template("resend_verification.html")


# ==============================================================================
# Forgot / Reset Password
# ==============================================================================
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()

        if not email:
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e01\u0e23\u0e2d\u0e01\u0e2d\u0e35\u0e40\u0e21\u0e25", "error")
            return render_template("forgot_password.html")

        user = User.get_by_email(email)

        if user:
            token = User.set_reset_token(user["id"])
            if token:
                reset_path = url_for("auth.reset_password", token=token)
                reset_link = _build_external_url(reset_path) if APP_BASE_URL else url_for("auth.reset_password", token=token, _external=True)
                try:
                    send_reset_password_email(email, reset_link)
                except Exception as e:
                    print(f"[EMAIL ERROR] {e}")

        flash("\u0e2b\u0e32\u0e01\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e19\u0e35\u0e49\u0e21\u0e35\u0e2d\u0e22\u0e39\u0e48\u0e43\u0e19\u0e23\u0e30\u0e1a\u0e1a \u0e40\u0e23\u0e32\u0e44\u0e14\u0e49\u0e2a\u0e48\u0e07\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e23\u0e35\u0e40\u0e0b\u0e47\u0e15\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e44\u0e1b\u0e41\u0e25\u0e49\u0e27 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e01\u0e25\u0e48\u0e2d\u0e07\u0e08\u0e14\u0e2b\u0e21\u0e32\u0e22", "success")
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.get_by_reset_token(token)

    if not user:
        flash("\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e23\u0e35\u0e40\u0e0b\u0e47\u0e15\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07\u0e2b\u0e23\u0e37\u0e2d\u0e2b\u0e21\u0e14\u0e2d\u0e32\u0e22\u0e38\u0e41\u0e25\u0e49\u0e27", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e15\u0e49\u0e2d\u0e07\u0e21\u0e35\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e19\u0e49\u0e2d\u0e22 6 \u0e15\u0e31\u0e27\u0e2d\u0e31\u0e01\u0e29\u0e23", "error")
            return render_template("reset_password.html", token=token)

        if password != confirm:
            flash("\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e44\u0e21\u0e48\u0e15\u0e23\u0e07\u0e01\u0e31\u0e19", "error")
            return render_template("reset_password.html", token=token)

        User.reset_password(user["id"], password)
        flash("\u0e23\u0e35\u0e40\u0e0b\u0e47\u0e15\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08! \u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e40\u0e02\u0e49\u0e32\u0e2a\u0e39\u0e48\u0e23\u0e30\u0e1a\u0e1a\u0e14\u0e49\u0e27\u0e22\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e43\u0e2b\u0e21\u0e48\u0e44\u0e14\u0e49\u0e41\u0e25\u0e49\u0e27", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)


# ==============================================================================
# My Account
# ==============================================================================
@auth_bp.route("/my-account")
@login_required
def my_account():
    user = User.get_by_id(session["user_id"])
    if not user:
        return redirect(url_for("auth.logout"))

    subscription = UserSubscription.get_active_subscription(user["id"])
    is_premium = subscription is not None

    raw_stats = UsageLimits.get_user_stats(user["id"])

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM classroom_students cs
        JOIN classrooms cl ON cs.classroom_id = cl.id
        WHERE cl.owner_id = ?
    """, (user["id"],))
    student_count = c.fetchone()[0]
    conn.close()

    stats = {
        "topics": raw_stats.get("topic_count", 0),
        "classrooms": raw_stats.get("classroom_count", 0),
        "ai_this_month": raw_stats.get("ai_generate_count", 0),
        "students": student_count,
    }

    if is_premium:
        limits = {"topics": None, "classrooms": None, "ai_generate": None, "students_per_classroom": None}
    else:
        limits = {
            "topics": UsageLimits.FREE_TOPICS,
            "classrooms": UsageLimits.FREE_CLASSROOMS,
            "ai_generate": UsageLimits.FREE_AI_GENERATE_PER_MONTH,
            "students_per_classroom": UsageLimits.FREE_STUDENTS_PER_CLASSROOM,
        }

    return render_template("my_account.html", user=user, subscription=subscription, is_premium=is_premium, stats=stats, limits=limits)


@auth_bp.route("/my-account/update", methods=["POST"])
@login_required
def my_account_update():
    display_name = (request.form.get("display_name") or "").strip()[:100]
    User.update_profile(session["user_id"], display_name)
    session["display_name"] = display_name
    flash("\u0e2d\u0e31\u0e1b\u0e40\u0e14\u0e15\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("auth.my_account"))


@auth_bp.route("/my-account/change-password", methods=["POST"])
@login_required
def my_account_change_password():
    user = User.get_by_id(session["user_id"])
    if not user:
        return redirect(url_for("auth.logout"))

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not check_password_hash(user["password_hash"], current_password):
        flash("\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e1b\u0e31\u0e08\u0e08\u0e38\u0e1a\u0e31\u0e19\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07", "error")
        return redirect(url_for("auth.my_account"))

    if len(new_password) < 6:
        flash("\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e43\u0e2b\u0e21\u0e48\u0e15\u0e49\u0e2d\u0e07\u0e21\u0e35\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e19\u0e49\u0e2d\u0e22 6 \u0e15\u0e31\u0e27\u0e2d\u0e31\u0e01\u0e29\u0e23", "error")
        return redirect(url_for("auth.my_account"))

    if new_password != confirm_password:
        flash("\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e43\u0e2b\u0e21\u0e48\u0e44\u0e21\u0e48\u0e15\u0e23\u0e07\u0e01\u0e31\u0e19", "error")
        return redirect(url_for("auth.my_account"))

    User.update_password(session["user_id"], new_password)
    flash("\u0e40\u0e1b\u0e25\u0e35\u0e48\u0e22\u0e19\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08!", "success")
    return redirect(url_for("auth.my_account"))
