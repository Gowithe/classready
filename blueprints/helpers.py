# ==============================================================================
# FILE: blueprints/helpers.py
# Shared decorators, helpers, and config used across all blueprints
# ==============================================================================

import os
import smtplib
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import session, flash, redirect, url_for, request, jsonify, abort
from werkzeug.security import check_password_hash

from models import User, Topic, UserSubscription, UsageLimits


# ==============================================================================
# Image Compression Helper
# ==============================================================================
def save_compressed_image(file_storage, upload_folder, prefix="hw", max_size=1200, quality=80):
    """Save uploaded image with auto-resize and compression.
    Returns the filename or empty string if invalid."""
    import secrets as _secrets
    from werkzeug.utils import secure_filename as _sf

    if not file_storage or not file_storage.filename:
        return ""

    fname = file_storage.filename
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
        return ""

    safe_name = _sf(fname)
    final_name = f"{prefix}_{_secrets.token_hex(6)}_{safe_name}"
    save_path = os.path.join(upload_folder, final_name)

    try:
        from PIL import Image as _Image
        img = _Image.open(file_storage)

        # Auto-rotate based on EXIF
        try:
            from PIL import ExifTags
            for k, v in ExifTags.TAGS.items():
                if v == "Orientation":
                    exif = img._getexif()
                    if exif and k in exif:
                        orient = exif[k]
                        if orient == 3:
                            img = img.rotate(180, expand=True)
                        elif orient == 6:
                            img = img.rotate(270, expand=True)
                        elif orient == 8:
                            img = img.rotate(90, expand=True)
                    break
        except Exception:
            pass

        # Resize if too large
        w, h = img.size
        if w > max_size or h > max_size:
            ratio = min(max_size / w, max_size / h)
            img = img.resize((int(w * ratio), int(h * ratio)), _Image.LANCZOS)

        # Save as JPEG for smaller size (unless PNG with transparency)
        if ext == "png" and img.mode in ("RGBA", "LA"):
            img.save(save_path, "PNG", optimize=True)
        else:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            save_path = save_path.rsplit(".", 1)[0] + ".jpg"
            final_name = final_name.rsplit(".", 1)[0] + ".jpg"
            img.save(save_path, "JPEG", quality=quality, optimize=True)

    except ImportError:
        # Pillow not installed — save as-is
        file_storage.seek(0)
        file_storage.save(save_path)
    except Exception as e:
        print(f"[WARN] Image compression failed: {e}, saving raw")
        file_storage.seek(0)
        file_storage.save(save_path)

    return final_name


def save_multiple_images(file_list, upload_folder, prefix="hw", max_size=1200, quality=80):
    """Save multiple uploaded images. Returns comma-separated filenames."""
    names = []
    for f in file_list:
        name = save_compressed_image(f, upload_folder, prefix, max_size, quality)
        if name:
            names.append(name)
    return ",".join(names)


# ==============================================================================
# Disk Usage Helper
# ==============================================================================
def get_disk_usage(path="/var/data"):
    """Return disk usage dict: total, used, free (in MB), percent."""
    try:
        import shutil
        usage = shutil.disk_usage(path)
        total_mb = usage.total / (1024 * 1024)
        used_mb = usage.used / (1024 * 1024)
        free_mb = usage.free / (1024 * 1024)
        pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0
        return {
            "total_mb": round(total_mb),
            "used_mb": round(used_mb),
            "free_mb": round(free_mb),
            "percent": round(pct, 1),
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "percent": 0}


# ==============================================================================
# Email Config
# ==============================================================================
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip()


# ==============================================================================
# Decorators
# ==============================================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("auth.login"))
        user = User.get_by_id(session["user_id"])
        if not user or user.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


# ==============================================================================
# Common Utilities
# ==============================================================================
def _is_admin():
    return session.get("role") == "admin"


def _can_access_topic(topic):
    return _is_admin() or int(topic.get("owner_id") or 0) == int(session.get("user_id") or 0)


def _get_topic_or_404(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)
    if not _can_access_topic(topic):
        abort(403)
    return topic


def _wants_json_response():
    return (
        request.path.startswith("/api/")
        or "application/json" in (request.headers.get("Accept") or "").lower()
    )


def _json_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def is_premium_user(user_id: int) -> bool:
    try:
        return UserSubscription.is_premium(user_id)
    except Exception:
        return False


# ==============================================================================
# Email Helpers
# ==============================================================================
def _build_external_url(path: str) -> str:
    if APP_BASE_URL:
        return APP_BASE_URL.rstrip("/") + path
    return path


def send_verify_email(to_email: str, verify_link: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[EMAIL] SMTP not configured. VERIFY LINK:", verify_link)
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = "\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e40\u0e02\u0e49\u0e32\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19 Teacher Platform"

    html = f"""<div style="font-family:Arial,sans-serif;line-height:1.6">
      <h2>\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2d\u0e35\u0e40\u0e21\u0e25</h2>
      <p>\u0e02\u0e2d\u0e1a\u0e04\u0e38\u0e13\u0e17\u0e35\u0e48\u0e2a\u0e21\u0e31\u0e04\u0e23\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e04\u0e25\u0e34\u0e01\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e14\u0e49\u0e32\u0e19\u0e25\u0e48\u0e32\u0e07\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2d\u0e35\u0e40\u0e21\u0e25\u0e02\u0e2d\u0e07\u0e04\u0e38\u0e13</p>
      <p><a href="{verify_link}" style="display:inline-block;padding:10px 14px;background:#667eea;color:#fff;text-decoration:none;border-radius:10px">\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e2d\u0e35\u0e40\u0e21\u0e25</a></p>
      <p style="word-break:break-all">{verify_link}</p>
      <p style="color:#64748b;font-size:13px">\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e19\u0e35\u0e49\u0e21\u0e35\u0e2d\u0e32\u0e22\u0e38 24 \u0e0a\u0e31\u0e48\u0e27\u0e42\u0e21\u0e07</p>
    </div>"""
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def send_reset_password_email(to_email: str, reset_link: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[EMAIL] SMTP not configured. RESET LINK:", reset_link)
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = "\u0e23\u0e35\u0e40\u0e0b\u0e47\u0e15\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19 - Teacher Platform"

    html = f"""<div style="font-family:Arial,sans-serif;line-height:1.6;max-width:500px;margin:0 auto;">
      <h2 style="color:#667eea;">\U0001f510 \u0e23\u0e35\u0e40\u0e0b\u0e47\u0e15\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19</h2>
      <p>\u0e04\u0e25\u0e34\u0e01\u0e1b\u0e38\u0e48\u0e21\u0e14\u0e49\u0e32\u0e19\u0e25\u0e48\u0e32\u0e07\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e15\u0e31\u0e49\u0e07\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e43\u0e2b\u0e21\u0e48:</p>
      <p style="text-align:center;margin:24px 0;">
        <a href="{reset_link}" style="display:inline-block;padding:12px 24px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;text-decoration:none;border-radius:10px;font-weight:bold;">
          \u0e15\u0e31\u0e49\u0e07\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e43\u0e2b\u0e21\u0e48
        </a>
      </p>
      <p style="word-break:break-all;font-size:13px;background:#f1f5f9;padding:10px;border-radius:6px;">{reset_link}</p>
      <p style="color:#ef4444;font-size:13px;">\u26a0\ufe0f \u0e25\u0e34\u0e07\u0e01\u0e4c\u0e19\u0e35\u0e49\u0e21\u0e35\u0e2d\u0e32\u0e22\u0e38 1 \u0e0a\u0e31\u0e48\u0e27\u0e42\u0e21\u0e07</p>
    </div>"""
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
