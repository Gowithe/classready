# ==============================================================================
# FILE: blueprints/admin.py
# Admin blueprint – dashboard, topic CRUD, library management (subjects/units),
# AI generation, import from topic, payments overview, user management
# ==============================================================================

import os
import json
import secrets
import traceback
import threading
from datetime import datetime

from flask import (
    Blueprint, request, session, jsonify, redirect, url_for,
    render_template, abort, flash, current_app,
)
from werkzeug.utils import secure_filename

from models import (
    Topic, LibrarySubject, LibraryUnit, LibraryClone, LibraryRating,
    UserSubscription, SubscriptionPlan, PaymentTransaction,
    GameQuestion, PracticeQuestion, get_db,
)
from blueprints.helpers import admin_required, login_required, _is_admin, is_premium_user

admin_bp = Blueprint("admin", __name__)


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"pdf", "png", "jpg", "jpeg", "gif"}


# ==============================================================================
# Admin Dashboard & Topic CRUD
# ==============================================================================
@admin_bp.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", topics=Topic.get_all())


@admin_bp.route("/admin/topics/create", methods=["GET", "POST"])
@admin_required
def admin_create_topic():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required.", "error")
            return render_template("admin_create_topic.html")
        topic = Topic.create(
            session["user_id"],
            name,
            request.form.get("description") or "",
            json.dumps({"slides": []}),
            "manual",
            None,
        )
        return redirect(url_for("admin.admin_edit_topic", topic_id=topic["id"]))
    return render_template("admin_create_topic.html")


@admin_bp.route("/admin/topics/<int:topic_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_topic(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return redirect(url_for("admin.admin_dashboard"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slides_json = request.form.get("slides_json") or ""
        try:
            json.loads(slides_json)
        except Exception:
            flash("Invalid JSON.", "error")
            return render_template("admin_edit_topic.html", topic=topic)
        pdf_filename = topic.get("pdf_file")
        file = request.files.get("pdf_file")
        if file and file.filename and _allowed_file(file.filename):
            fn = f"topic{topic_id}_{secrets.token_hex(6)}_{secure_filename(file.filename)}"
            file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], fn))
            pdf_filename = fn
        Topic.update(topic_id, name, request.form.get("description") or "", slides_json, pdf_filename)
        flash("Saved.", "success")
    return render_template("admin_edit_topic.html", topic=Topic.get_by_id(topic_id))


@admin_bp.route("/admin/topics/<int:topic_id>/delete", methods=["POST"])
@admin_required
def admin_delete_topic(topic_id):
    Topic.delete(topic_id)
    return redirect(url_for("admin.admin_dashboard"))


# ==============================================================================
# Admin Library Management
# ==============================================================================
@admin_bp.route("/admin/library")
@login_required
@admin_required
def admin_library():
    subjects = LibrarySubject.get_all_active()
    subject_units = {}
    try:
        for s in subjects:
            sid = s["id"] if isinstance(s, dict) else s.id
            subject_units[int(sid)] = LibraryUnit.get_by_subject(int(sid))
    except Exception:
        subject_units = {}
    return render_template("admin/library.html", subjects=subjects, subject_units=subject_units)


# ---------------------------------------------------------------------------
# Subject CRUD
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/library/subject/create", methods=["GET", "POST"])
@login_required
def admin_library_subject_create():
    if not _is_admin():
        abort(403)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e43\u0e2a\u0e48\u0e0a\u0e37\u0e48\u0e2d\u0e27\u0e34\u0e0a\u0e32", "error")
            return render_template("admin/library_subject_edit.html", subject=None)
        LibrarySubject.create(
            name=name,
            description=request.form.get("description", ""),
            grade_level=request.form.get("grade_level", ""),
            subject_type=request.form.get("subject_type", "english"),
            icon=request.form.get("icon", "\U0001f4da"),
            color=request.form.get("color", "#667eea"),
        )
        flash("\u0e2a\u0e23\u0e49\u0e32\u0e07\u0e27\u0e34\u0e0a\u0e32\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08", "success")
        return redirect(url_for("admin.admin_library"))
    return render_template("admin/library_subject_edit.html", subject=None)


@admin_bp.route("/admin/library/subject/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
def admin_library_subject_edit(subject_id):
    if not _is_admin():
        abort(403)
    subject = LibrarySubject.get_by_id(subject_id)
    if not subject:
        abort(404)
    if request.method == "POST":
        LibrarySubject.update(
            subject_id,
            name=request.form.get("name", "").strip(),
            description=request.form.get("description", ""),
            grade_level=request.form.get("grade_level", ""),
            subject_type=request.form.get("subject_type", "english"),
            icon=request.form.get("icon", "\U0001f4da"),
            color=request.form.get("color", "#667eea"),
        )
        flash("\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08", "success")
        return redirect(url_for("admin.admin_library"))
    return render_template("admin/library_subject_edit.html", subject=subject)


# ---------------------------------------------------------------------------
# Unit CRUD
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/library/unit/create/<int:subject_id>", methods=["GET", "POST"])
@login_required
def admin_library_unit_create(subject_id):
    if not _is_admin():
        abort(403)
    subject = LibrarySubject.get_by_id(subject_id)
    if not subject:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e43\u0e2a\u0e48\u0e0a\u0e37\u0e48\u0e2d\u0e1a\u0e17\u0e40\u0e23\u0e35\u0e22\u0e19", "error")
            return render_template("admin/library_unit_edit.html", subject=subject, unit=None, slides_count=0, game_count=0, practice_count=0)
        pdf_filename = None
        if "pdf_file" in request.files:
            pdf = request.files["pdf_file"]
            if pdf and pdf.filename and pdf.filename.endswith(".pdf"):
                pdf_filename = secure_filename(f"lib_{subject_id}_{int(datetime.utcnow().timestamp())}_{pdf.filename}")
                pdf.save(os.path.join(current_app.config["UPLOAD_FOLDER"], pdf_filename))
        unit = LibraryUnit.create(
            subject_id=subject_id,
            name=name,
            unit_number=int(request.form.get("unit_number", 1)),
            description=request.form.get("description", ""),
            is_free=request.form.get("is_free") == "1",
            estimated_time=int(request.form.get("estimated_time", 60)),
            pdf_file=pdf_filename,
        )
        flash("\u0e2a\u0e23\u0e49\u0e32\u0e07\u0e1a\u0e17\u0e40\u0e23\u0e35\u0e22\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08! \u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16 Generate \u0e40\u0e19\u0e37\u0e49\u0e2d\u0e2b\u0e32\u0e44\u0e14\u0e49", "success")
        return redirect(url_for("admin.admin_library_unit_edit", unit_id=unit["id"]))
    return render_template("admin/library_unit_edit.html", subject=subject, unit=None, slides_count=0, game_count=0, practice_count=0)


@admin_bp.route("/admin/library/unit/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
def admin_library_unit_edit(unit_id):
    if not _is_admin():
        abort(403)
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        abort(404)
    subject = LibrarySubject.get_by_id(unit["subject_id"])

    if request.method == "POST":
        pdf_filename = unit.get("pdf_file")
        if "pdf_file" in request.files:
            pdf = request.files["pdf_file"]
            if pdf and pdf.filename and pdf.filename.endswith(".pdf"):
                pdf_filename = secure_filename(f"lib_{unit['subject_id']}_{int(datetime.utcnow().timestamp())}_{pdf.filename}")
                pdf.save(os.path.join(current_app.config["UPLOAD_FOLDER"], pdf_filename))
        slides_json = request.form.get("slides_json", unit.get("slides_json") or "{}")
        game_json = request.form.get("game_json", unit.get("game_json") or "{}")
        practice_json = request.form.get("practice_json", unit.get("practice_json") or "[]")
        LibraryUnit.update(
            unit_id,
            name=request.form.get("name", "").strip(),
            unit_number=int(request.form.get("unit_number", 1)),
            description=request.form.get("description", ""),
            is_free=1 if request.form.get("is_free") == "1" else 0,
            estimated_time=int(request.form.get("estimated_time", 60)),
            pdf_file=pdf_filename,
            slides_json=slides_json,
            game_json=game_json,
            practice_json=practice_json,
        )
        flash("\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08", "success")
        return redirect(url_for("admin.admin_library_unit_edit", unit_id=unit_id))

    unit = LibraryUnit.get_by_id(unit_id)
    slides_count, game_count, practice_count = 0, 0, 0

    if unit.get("slides_json"):
        try:
            sd = json.loads(unit["slides_json"])
            sl = sd.get("slides", []) if isinstance(sd, dict) else sd
            slides_count = len(sl) if isinstance(sl, list) else 0
        except Exception:
            pass
    if unit.get("game_json"):
        try:
            gd = json.loads(unit["game_json"])
            for qs in gd.values():
                if isinstance(qs, list):
                    game_count += len(qs)
        except Exception:
            pass
    if unit.get("practice_json"):
        try:
            pd = json.loads(unit["practice_json"])
            practice_count = len(pd) if isinstance(pd, list) else 0
        except Exception:
            pass

    return render_template(
        "admin/library_unit_edit.html",
        subject=subject,
        unit=unit,
        slides_count=slides_count,
        game_count=game_count,
        practice_count=practice_count,
    )


@admin_bp.route("/admin/library/unit/<int:unit_id>/delete", methods=["POST"])
@login_required
def admin_library_unit_delete(unit_id):
    if not _is_admin():
        abort(403)
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        abort(404)
    try:
        LibraryUnit.hard_delete(unit_id)
        flash("\u0e25\u0e1a\u0e1a\u0e17\u0e40\u0e23\u0e35\u0e22\u0e19\u0e2d\u0e2d\u0e01\u0e08\u0e32\u0e01\u0e04\u0e25\u0e31\u0e07\u0e01\u0e25\u0e32\u0e07\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22\u0e41\u0e25\u0e49\u0e27", "success")
    except Exception as e:
        traceback.print_exc()
        flash(f"\u0e25\u0e1a\u0e44\u0e21\u0e48\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08: {e}", "error")
    return redirect(url_for("admin.admin_library"))


# ---------------------------------------------------------------------------
# AI Generate for Library Unit
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/library/unit/<int:unit_id>/generate/<gen_type>", methods=["POST"])
@login_required
def admin_library_unit_generate(unit_id, gen_type):
    if not _is_admin():
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        return jsonify({"ok": False, "error": "Unit not found"}), 404
    if gen_type not in ["all", "slides", "game", "practice"]:
        return jsonify({"ok": False, "error": "Invalid type"}), 400

    topic_name = unit["name"]

    # Use shared background task system from app.py
    from app import _create_task, _update_task, _cleanup_old_tasks

    _cleanup_old_tasks()
    task_id = _create_task()

    def run_admin_generate():
        try:
            _update_task(task_id, status="generating")
            from ai_generator import generate_lesson_bundle
            from flask import current_app

            bundle = generate_lesson_bundle(topic_name)
            if not bundle:
                _update_task(task_id, status="error", error="AI generation failed")
                return

            updates = {}

            if gen_type in ["all", "slides"]:
                slides = bundle.get("slides") or []
                slides_json = json.dumps({"slides": slides}, ensure_ascii=False)
                updates["slides_json"] = slides_json

            if gen_type in ["all", "game"]:
                game_raw = bundle.get("game") or {}
                game_data = {}
                for set_no in [1, 2, 3]:
                    set_key = str(set_no)
                    questions = game_raw.get(set_key) or game_raw.get(f"set{set_no}") or []
                    if questions:
                        game_data[set_key] = []
                        for idx, q in enumerate(questions):
                            game_data[set_key].append({
                                "tile_no": idx + 1,
                                "question": q.get("question", ""),
                                "answer": q.get("answer", ""),
                                "points": q.get("points", 10),
                            })
                game_json = json.dumps(game_data, ensure_ascii=False)
                updates["game_json"] = game_json

            if gen_type in ["all", "practice"]:
                practice_raw = bundle.get("practice") or []
                practice_data = []
                for q in practice_raw:
                    practice_data.append({
                        "question": q.get("question", ""),
                        "choices": q.get("choices", []),
                        "correct_index": q.get("correct_index", 0),
                    })
                practice_json = json.dumps(practice_data, ensure_ascii=False)
                updates["practice_json"] = practice_json

            if updates:
                LibraryUnit.update(unit_id, **updates)

            _update_task(task_id, status="done", result={"ok": True})
        except Exception as e:
            _update_task(task_id, status="error", error=str(e))

    threading.Thread(target=run_admin_generate, daemon=True).start()
    return jsonify({"ok": True, "task_id": task_id})


# ---------------------------------------------------------------------------
# Import from existing Topic
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/library/unit/<int:unit_id>/import-from-topic/<int:topic_id>", methods=["POST"])
@login_required
def admin_library_import_from_topic(unit_id, topic_id):
    if not _is_admin():
        abort(403)
    unit = LibraryUnit.get_by_id(unit_id)
    topic = Topic.get_by_id(topic_id)
    if not unit or not topic:
        return jsonify({"ok": False, "error": "Not found"}), 404

    slides_json = topic.get("slides_json", "{}")

    game_data = {}
    for set_no in [1, 2, 3]:
        questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        if questions:
            game_data[str(set_no)] = [
                {
                    "tile_no": q.get("tile_no", idx + 1),
                    "question": q["question"],
                    "answer": q["answer"],
                    "points": q.get("points", 10),
                }
                for idx, q in enumerate(questions)
            ]

    practice_questions = PracticeQuestion.get_by_topic(topic_id)
    practice_data = []
    for q in practice_questions:
        try:
            q_data = json.loads(q["question"])
            prompt = q_data.get("prompt", "")
            choices = q_data.get("choices", [])
            correct_answer = q.get("correct_answer", "")
            correct_index = 0
            for idx, choice in enumerate(choices):
                if str(choice).strip() == str(correct_answer).strip():
                    correct_index = idx
                    break
            practice_data.append({"question": prompt, "choices": choices, "correct_index": correct_index})
        except Exception:
            practice_data.append({"question": q["question"], "choices": [], "correct_index": 0})

    LibraryUnit.update(
        unit_id,
        slides_json=slides_json,
        game_json=json.dumps(game_data, ensure_ascii=False) if game_data else "",
        practice_json=json.dumps(practice_data, ensure_ascii=False) if practice_data else "",
    )
    return jsonify({"ok": True})


# ==============================================================================
# Admin Payments
# ==============================================================================
@admin_bp.route("/admin/payments")
@login_required
def admin_payments():
    if not _is_admin():
        abort(403)
    transactions = PaymentTransaction.get_all_for_admin(100)
    return render_template("admin/payments.html", transactions=transactions)


# ==============================================================================
# Admin Users
# ==============================================================================
@admin_bp.route("/admin/users")
@login_required
def admin_users():
    if not _is_admin():
        abort(403)

    q = (request.args.get("q") or "").strip()
    now = datetime.utcnow().isoformat()

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    row = c.fetchone()
    total_users = int(row[0]) if row and row[0] is not None else 0

    try:
        c.execute("""
            SELECT COUNT(DISTINCT user_id)
            FROM user_subscriptions
            WHERE status='active' AND expires_at > ?
        """, (now,))
        pr = c.fetchone()
        total_premium_active = int(pr[0]) if pr and pr[0] is not None else 0
    except Exception:
        total_premium_active = 0

    base_sql = """
        SELECT
            u.id, u.email, u.role, u.created_at,
            us.id as sub_id, us.plan_id, us.status as sub_status, us.started_at, us.expires_at, us.payment_ref,
            sp.name as plan_name, sp.price as plan_price
        FROM users u
        LEFT JOIN (
            SELECT s1.*
            FROM user_subscriptions s1
            JOIN (
                SELECT user_id, MAX(expires_at) AS max_exp
                FROM user_subscriptions
                GROUP BY user_id
            ) mx
            ON s1.user_id = mx.user_id AND s1.expires_at = mx.max_exp
        ) us ON us.user_id = u.id
        LEFT JOIN subscription_plans sp ON sp.id = us.plan_id
    """

    if q:
        c.execute(base_sql + " WHERE u.email LIKE ? ORDER BY u.id DESC LIMIT 300", (f"%{q}%",))
    else:
        c.execute(base_sql + " ORDER BY u.id DESC LIMIT 300")

    rows = c.fetchall()
    conn.close()

    users = []
    for r in rows:
        expires_at = r["expires_at"] if "expires_at" in r.keys() else None
        is_prem = False
        if expires_at:
            try:
                is_prem = (r["sub_status"] == "active") and (expires_at > now)
            except Exception:
                is_prem = False
        users.append({
            "id": r["id"],
            "email": r["email"],
            "role": r["role"] or "",
            "created_at": r["created_at"] or "",
            "sub_id": r["sub_id"],
            "plan_id": r["plan_id"],
            "plan_name": r["plan_name"] or "",
            "plan_price": r["plan_price"] if "plan_price" in r.keys() else None,
            "sub_status": r["sub_status"] or "",
            "started_at": r["started_at"] or "",
            "expires_at": expires_at or "",
            "payment_ref": r["payment_ref"] or "",
            "is_premium": is_prem,
        })

    return render_template(
        "admin/users.html",
        total_users=total_users,
        total_premium_active=total_premium_active,
        users=users,
        q=q,
        now_utc=now,
    )


@admin_bp.route("/admin/users/<int:user_id>/adjust-expiry", methods=["POST"])
@login_required
def admin_adjust_user_expiry(user_id: int):
    if not _is_admin():
        abort(403)
    delta_days_raw = (request.form.get("days") or "").strip()
    try:
        delta_days = int(delta_days_raw)
    except Exception:
        delta_days = 0

    if delta_days == 0:
        flash("\u0e08\u0e33\u0e19\u0e27\u0e19\u0e27\u0e31\u0e19\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07", "error")
        return redirect(url_for("admin.admin_users", q=request.args.get("q") or ""))

    try:
        sub = UserSubscription.get_active_subscription(user_id)
        if sub:
            UserSubscription.adjust_expiry(sub["id"], delta_days)
            flash(f"\u0e1b\u0e23\u0e31\u0e1a\u0e27\u0e31\u0e19\u0e2b\u0e21\u0e14\u0e2d\u0e32\u0e22\u0e38 {delta_days:+d} \u0e27\u0e31\u0e19 \u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
        else:
            UserSubscription.grant_premium(user_id, max(delta_days, 1), reason="admin_adjust")
            flash(f"\u0e2a\u0e23\u0e49\u0e32\u0e07 Premium \u0e43\u0e2b\u0e21\u0e48 {max(delta_days, 1)} \u0e27\u0e31\u0e19 \u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    except Exception as e:
        flash(f"\u0e1b\u0e23\u0e31\u0e1a\u0e27\u0e31\u0e19\u0e2b\u0e21\u0e14\u0e2d\u0e32\u0e22\u0e38\u0e44\u0e21\u0e48\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08: {e}", "error")

    return redirect(url_for("admin.admin_users", q=request.args.get("q") or ""))


# ==============================================================================
# Cleanup Spam / Unverified Accounts
# ==============================================================================
@admin_bp.route("/admin/users/cleanup-spam", methods=["POST"])
@admin_required
def admin_cleanup_spam():
    """Delete unverified accounts older than 1 day (bot registrations)."""
    try:
        conn = get_db()
        c = conn.cursor()

        # Count first
        c.execute("""
            SELECT COUNT(*) FROM users
            WHERE is_verified = 0
              AND role != 'admin'
              AND created_at < datetime('now', '-1 day')
        """)
        count = c.fetchone()[0]

        if count == 0:
            conn.close()
            flash("\u0e44\u0e21\u0e48\u0e21\u0e35\u0e1a\u0e31\u0e0d\u0e0a\u0e35 spam \u0e17\u0e35\u0e48\u0e15\u0e49\u0e2d\u0e07\u0e25\u0e1a", "info")
            return redirect(url_for("admin.admin_users"))

        # Get spam user IDs
        c.execute("""
            SELECT id FROM users
            WHERE is_verified = 0 AND role != 'admin'
              AND created_at < datetime('now', '-1 day')
        """)
        spam_ids = [r[0] for r in c.fetchall()]

        # Disable FK checks, bulk delete, re-enable
        c.execute("PRAGMA foreign_keys = OFF")
        for uid in spam_ids:
            _delete_user_cascade(c, uid)
        c.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        conn.close()

        flash(f"\u2705 \u0e25\u0e1a\u0e1a\u0e31\u0e0d\u0e0a\u0e35 spam {count} \u0e1a\u0e31\u0e0d\u0e0a\u0e35\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    except Exception as e:
        flash(f"\u274c \u0e40\u0e01\u0e34\u0e14\u0e02\u0e49\u0e2d\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14: {e}", "error")

    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    """Delete a single user and all related data."""
    try:
        conn = get_db()
        c = conn.cursor()

        # Safety: never delete admin
        c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            flash("\u0e44\u0e21\u0e48\u0e1e\u0e1a user", "error")
            conn.close()
            return redirect(url_for("admin.admin_users"))
        if row[0] == "admin":
            flash("\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e25\u0e1a admin \u0e44\u0e14\u0e49", "error")
            conn.close()
            return redirect(url_for("admin.admin_users"))

        c.execute("PRAGMA foreign_keys = OFF")
        _delete_user_cascade(c, user_id)
        c.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        conn.close()
        flash(f"\u2705 \u0e25\u0e1a user #{user_id} \u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    except Exception as e:
        flash(f"\u274c \u0e40\u0e01\u0e34\u0e14\u0e02\u0e49\u0e2d\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14: {e}", "error")

    return redirect(url_for("admin.admin_users"))


def _delete_user_cascade(cursor, user_id):
    """Delete all data related to a user across all tables."""
    c = cursor
    uid = user_id

    # Get user's topic IDs
    c.execute("SELECT id FROM topics WHERE owner_id = ?", (uid,))
    topic_ids = [r[0] for r in c.fetchall()]

    # Get user's classroom IDs
    c.execute("SELECT id FROM classrooms WHERE owner_id = ?", (uid,))
    classroom_ids = [r[0] for r in c.fetchall()]

    # Get user's practice_link IDs
    c.execute("SELECT id FROM practice_links WHERE created_by = ?", (uid,))
    link_ids = [r[0] for r in c.fetchall()]

    # Delete from children tables
    for tid in topic_ids:
        c.execute("DELETE FROM game_questions WHERE topic_id = ?", (tid,))
        c.execute("DELETE FROM practice_questions WHERE topic_id = ?", (tid,))
        c.execute("DELETE FROM practice_links WHERE topic_id = ?", (tid,))
        c.execute("DELETE FROM game_sessions WHERE topic_id = ?", (tid,))

    for lid in link_ids:
        c.execute("DELETE FROM practice_submissions WHERE link_id = ?", (lid,))

    for cid in classroom_ids:
        c.execute("DELETE FROM assignments WHERE classroom_id = ?", (cid,))
        c.execute("DELETE FROM classroom_students WHERE classroom_id = ?", (cid,))

    c.execute("DELETE FROM assignments WHERE created_by = ?", (uid,))
    c.execute("DELETE FROM classrooms WHERE owner_id = ?", (uid,))
    c.execute("DELETE FROM game_sessions WHERE created_by = ?", (uid,))
    c.execute("DELETE FROM attempt_history WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM library_clones WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM library_ratings WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM user_subscriptions WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM user_usage WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM topics WHERE owner_id = ?", (uid,))
    c.execute("DELETE FROM users WHERE id = ?", (uid,))

    return redirect(url_for("admin.admin_users"))
