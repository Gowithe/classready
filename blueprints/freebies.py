# ==============================================================================
# FILE: blueprints/freebies.py
# Public freebies page + admin upload
# ==============================================================================

import os
import secrets
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, current_app,
)
from werkzeug.utils import secure_filename

from models import Freebie
from blueprints.helpers import login_required, is_premium_user

freebies_bp = Blueprint("freebies", __name__)


def _is_admin():
    return session.get("role") == "admin"


ALLOWED_PDF = {"pdf"}
ALLOWED_IMG = {"png", "jpg", "jpeg", "webp"}


def _allowed(filename, exts):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


# ==============================================================================
# Public Freebies Page
# ==============================================================================
@freebies_bp.route("/freebies")
def freebies_index():
    category = request.args.get("category", "")
    if category:
        items = Freebie.get_all(active_only=True, category=category)
    else:
        items = Freebie.get_all(active_only=True)

    return render_template(
        "freebies.html",
        items=items,
        categories=Freebie.CATEGORIES,
        current_category=category,
    )


# ==============================================================================
# Public share link — no login required
# ==============================================================================
@freebies_bp.route("/f/<token>")
def freebies_public(token):
    """Public viewer — anyone with the link can view, no login needed."""
    freebie = Freebie.get_by_token(token)
    if not freebie:
        abort(404)
    return render_template("freebies_public.html", freebie=freebie)


@freebies_bp.route("/f/<token>/pdf")
def freebies_public_pdf(token):
    """Serve the PDF file publicly (no login) for shared freebie links."""
    freebie = Freebie.get_by_token(token)
    if not freebie:
        abort(404)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_folder, freebie["pdf_file"])


@freebies_bp.route("/freebies/<int:freebie_id>/view")
def freebies_view(freebie_id):
    """View PDF inline — PUBLIC, no login required (for sharing)."""
    freebie = Freebie.get_by_id(freebie_id)
    if not freebie or not freebie.get("is_active"):
        abort(404)
    return render_template("freebies_view.html", freebie=freebie)


@freebies_bp.route("/freebies/<int:freebie_id>/pdf")
def freebies_pdf_raw(freebie_id):
    """Serve the raw PDF for inline viewing (public)."""
    freebie = Freebie.get_by_id(freebie_id)
    if not freebie or not freebie.get("is_active"):
        abort(404)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_folder, freebie["pdf_file"], as_attachment=False)


@freebies_bp.route("/freebies/<int:freebie_id>/download")
@login_required
def freebies_download(freebie_id):
    freebie = Freebie.get_by_id(freebie_id)
    if not freebie or not freebie.get("is_active"):
        abort(404)

    # Premium check
    if not freebie.get("is_free"):
        if not is_premium_user(session["user_id"]):
            flash("\u0e44\u0e1f\u0e25\u0e4c\u0e19\u0e35\u0e49\u0e2a\u0e33\u0e2b\u0e23\u0e31\u0e1a\u0e2a\u0e21\u0e32\u0e0a\u0e34\u0e01 Premium \u0e40\u0e17\u0e48\u0e32\u0e19\u0e31\u0e49\u0e19", "error")
            return redirect(url_for("payment.pricing"))

    Freebie.increment_download(freebie_id)

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_folder, freebie["pdf_file"], as_attachment=True)


# ==============================================================================
# Admin - Freebies Management
# ==============================================================================
@freebies_bp.route("/admin/freebies")
@login_required
def admin_freebies():
    if not _is_admin():
        abort(403)
    items = Freebie.get_all(active_only=False)
    return render_template("admin_freebies.html", items=items, categories=Freebie.CATEGORIES)


@freebies_bp.route("/admin/freebies/create", methods=["GET", "POST"])
@login_required
def admin_freebie_create():
    if not _is_admin():
        abort(403)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        category = (request.form.get("category") or "fundamentals").strip()
        is_free = request.form.get("is_free") == "1"

        if not title:
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e23\u0e30\u0e1a\u0e38\u0e0a\u0e37\u0e48\u0e2d", "error")
            return render_template("admin_freebie_edit.html", freebie=None, categories=Freebie.CATEGORIES)

        pdf_file = request.files.get("pdf_file")
        if not pdf_file or not pdf_file.filename or not _allowed(pdf_file.filename, ALLOWED_PDF):
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e2d\u0e31\u0e1b\u0e42\u0e2b\u0e25\u0e14\u0e44\u0e1f\u0e25\u0e4c PDF", "error")
            return render_template("admin_freebie_edit.html", freebie=None, categories=Freebie.CATEGORIES)

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        safe_name = secure_filename(pdf_file.filename)
        final_pdf = f"freebie_{secrets.token_hex(6)}_{safe_name}"
        pdf_file.save(os.path.join(upload_folder, final_pdf))

        thumbnail = ""
        thumb_file = request.files.get("thumbnail")
        if thumb_file and thumb_file.filename and _allowed(thumb_file.filename, ALLOWED_IMG):
            safe_thumb = secure_filename(thumb_file.filename)
            thumbnail = f"thumb_{secrets.token_hex(6)}_{safe_thumb}"
            thumb_file.save(os.path.join(upload_folder, thumbnail))

        Freebie.create(
            title=title, description=description, category=category,
            pdf_file=final_pdf, thumbnail=thumbnail, is_free=is_free,
        )
        flash("\u0e2d\u0e31\u0e1b\u0e42\u0e2b\u0e25\u0e14\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08", "success")
        return redirect(url_for("freebies.admin_freebies"))

    return render_template("admin_freebie_edit.html", freebie=None, categories=Freebie.CATEGORIES)


@freebies_bp.route("/admin/freebies/<int:freebie_id>/edit", methods=["GET", "POST"])
@login_required
def admin_freebie_edit(freebie_id):
    if not _is_admin():
        abort(403)

    freebie = Freebie.get_by_id(freebie_id)
    if not freebie:
        abort(404)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        category = (request.form.get("category") or "fundamentals").strip()
        is_free = request.form.get("is_free") == "1"

        updates = {
            "title": title, "description": description,
            "category": category, "is_free": 1 if is_free else 0,
        }

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        pdf_file = request.files.get("pdf_file")
        if pdf_file and pdf_file.filename and _allowed(pdf_file.filename, ALLOWED_PDF):
            safe_name = secure_filename(pdf_file.filename)
            final_pdf = f"freebie_{secrets.token_hex(6)}_{safe_name}"
            pdf_file.save(os.path.join(upload_folder, final_pdf))
            updates["pdf_file"] = final_pdf

        thumb_file = request.files.get("thumbnail")
        if thumb_file and thumb_file.filename and _allowed(thumb_file.filename, ALLOWED_IMG):
            safe_thumb = secure_filename(thumb_file.filename)
            thumbnail = f"thumb_{secrets.token_hex(6)}_{safe_thumb}"
            thumb_file.save(os.path.join(upload_folder, thumbnail))
            updates["thumbnail"] = thumbnail

        Freebie.update(freebie_id, **updates)
        flash("\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e41\u0e25\u0e49\u0e27", "success")
        return redirect(url_for("freebies.admin_freebies"))

    return render_template("admin_freebie_edit.html", freebie=freebie, categories=Freebie.CATEGORIES)


@freebies_bp.route("/admin/freebies/<int:freebie_id>/delete", methods=["POST"])
@login_required
def admin_freebie_delete(freebie_id):
    if not _is_admin():
        abort(403)
    Freebie.delete(freebie_id)
    flash("\u0e25\u0e1a\u0e41\u0e25\u0e49\u0e27", "success")
    return redirect(url_for("freebies.admin_freebies"))
