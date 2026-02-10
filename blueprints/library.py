# ==============================================================================
# FILE: blueprints/library.py
# Library blueprint – browse subjects/units, clone, rate, search, premium page
# ==============================================================================

import json

from flask import (
    Blueprint, request, session, jsonify, redirect, url_for,
    render_template, abort, flash,
)

from models import (
    Topic, LibrarySubject, LibraryUnit, LibraryClone, LibraryRating,
    UserSubscription, SubscriptionPlan, GameQuestion, PracticeQuestion,
    PaymentTransaction,
)
from blueprints.helpers import login_required, is_premium_user

library_bp = Blueprint("library", __name__)


# ==============================================================================
# Library Browsing
# ==============================================================================
@library_bp.route("/library")
@login_required
def library():
    subjects = LibrarySubject.get_all_active()
    popular_units = LibraryUnit.get_popular_units(6)
    free_units = LibraryUnit.get_free_units(6)
    is_premium = UserSubscription.is_premium(session["user_id"])
    return render_template(
        "library/index.html",
        subjects=subjects,
        popular_units=popular_units,
        free_units=free_units,
        is_premium=is_premium,
    )


@library_bp.route("/library/subject/<int:subject_id>")
@login_required
def library_subject(subject_id):
    subject = LibrarySubject.get_by_id(subject_id)
    if not subject:
        abort(404)
    units = LibraryUnit.get_by_subject(subject_id)
    is_premium = UserSubscription.is_premium(session["user_id"])
    user_clones = {c["unit_id"]: c for c in LibraryClone.get_by_user(session["user_id"])}
    return render_template(
        "library/subject.html",
        subject=subject,
        units=units,
        is_premium=is_premium,
        user_clones=user_clones,
    )


@library_bp.route("/library/unit/<int:unit_id>")
@login_required
def library_unit_detail(unit_id):
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        abort(404)
    LibraryUnit.increment_view(unit_id)

    is_premium = UserSubscription.is_premium(session["user_id"])
    can_access = unit["is_free"] == 1 or is_premium
    has_cloned = LibraryClone.has_cloned(session["user_id"], unit_id)
    user_rating = LibraryRating.get_user_rating(session["user_id"], unit_id)

    slides_preview = []
    if unit.get("slides_json"):
        try:
            slides_data = json.loads(unit["slides_json"])
            slides = slides_data.get("slides", slides_data) if isinstance(slides_data, dict) else slides_data
            if can_access:
                slides_preview = slides
            else:
                slides_preview = slides[: unit.get("preview_slides", 3)]
        except Exception:
            pass

    return render_template(
        "library/unit_detail.html",
        unit=unit,
        is_premium=is_premium,
        can_access=can_access,
        has_cloned=has_cloned,
        user_rating=user_rating,
        slides_preview=slides_preview,
        total_slides=len(slides_preview) if can_access else "?",
    )


# ==============================================================================
# Clone Unit → Topic
# ==============================================================================
@library_bp.route("/library/unit/<int:unit_id>/clone", methods=["POST"])
@login_required
def library_clone_unit(unit_id):
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        return jsonify({"ok": False, "error": "Unit not found"}), 404

    is_premium = UserSubscription.is_premium(session["user_id"])
    can_access = unit["is_free"] == 1 or is_premium
    if not can_access:
        return jsonify({"ok": False, "error": "Premium required"}), 403

    # Check if already cloned
    if LibraryClone.has_cloned(session["user_id"], unit_id):
        clones = LibraryClone.get_by_user(session["user_id"])
        for c in clones:
            if c["unit_id"] == unit_id:
                return jsonify({"ok": True, "topic_id": c["topic_id"], "already_cloned": True})

    # Create new topic from unit
    topic = Topic.create(
        owner_id=session["user_id"],
        name=unit["name"],
        description=unit.get("description") or f"\u0e08\u0e32\u0e01 Library: {unit.get('subject_name', '')}",
        slides_json=unit.get("slides_json") or "{}",
        topic_type="library",
        pdf_file=unit.get("pdf_file"),
    )

    # Copy game questions
    if unit.get("game_json"):
        try:
            game_data = json.loads(unit["game_json"])
            for set_no_str, questions in game_data.items():
                if isinstance(questions, list):
                    for idx, q in enumerate(questions):
                        GameQuestion.create(
                            topic_id=topic["id"],
                            set_no=int(set_no_str),
                            tile_no=q.get("tile_no", idx + 1),
                            question=q.get("question", ""),
                            answer=q.get("answer", ""),
                            points=q.get("points", 10),
                        )
        except Exception as e:
            print(f"Error copying game: {e}")

    # Copy practice questions
    if unit.get("practice_json"):
        try:
            practice_data = json.loads(unit["practice_json"])
            if isinstance(practice_data, list):
                for q in practice_data:
                    prompt = q.get("question", "")
                    choices = q.get("choices", [])
                    ci = q.get("correct_index", 0)
                    if prompt and choices:
                        correct_answer = str(choices[ci]).strip() if ci < len(choices) else ""
                        PracticeQuestion.create(
                            topic_id=topic["id"],
                            q_type="multiple_choice",
                            question=json.dumps({"prompt": prompt, "choices": choices}, ensure_ascii=False),
                            correct_answer=correct_answer,
                        )
        except Exception as e:
            print(f"Error copying practice: {e}")

    LibraryClone.create(session["user_id"], unit_id, topic["id"])
    return jsonify({"ok": True, "topic_id": topic["id"]})


# ==============================================================================
# Rate Unit
# ==============================================================================
@library_bp.route("/library/unit/<int:unit_id>/rate", methods=["POST"])
@login_required
def library_rate_unit(unit_id):
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        return jsonify({"ok": False, "error": "Unit not found"}), 404
    data = request.get_json() or {}
    rating = int(data.get("rating", 0))
    review = (data.get("review") or "").strip()
    if rating < 1 or rating > 5:
        return jsonify({"ok": False, "error": "Rating must be 1-5"}), 400
    LibraryRating.rate(session["user_id"], unit_id, rating, review)
    updated_unit = LibraryUnit.get_by_id(unit_id)
    return jsonify({"ok": True, "avg_rating": updated_unit.get("avg_rating", 0)})


# ==============================================================================
# Library Search
# ==============================================================================
@library_bp.route("/library/search")
@login_required
def library_search():
    q = request.args.get("q", "").strip()
    subject_id = request.args.get("subject_id", type=int)
    free_only = request.args.get("free_only") == "1"
    results = []
    if q:
        results = LibraryUnit.search(q, subject_id, free_only)
    is_premium = UserSubscription.is_premium(session["user_id"])
    subjects = LibrarySubject.get_all_active()
    return render_template(
        "library/search.html",
        query=q,
        results=results,
        subjects=subjects,
        selected_subject=subject_id,
        free_only=free_only,
        is_premium=is_premium,
    )


# ==============================================================================
# Premium Page
# ==============================================================================
@library_bp.route("/premium")
@login_required
def premium_page():
    plans = SubscriptionPlan.get_all_active()
    current_sub = UserSubscription.get_active_subscription(session["user_id"])
    return render_template("library/premium.html", plans=plans, current_sub=current_sub)


@library_bp.route("/premium/subscribe/<int:plan_id>", methods=["POST"])
@login_required
def premium_subscribe(plan_id):
    user_id = session["user_id"]
    if is_premium_user(user_id):
        return jsonify({"ok": False, "error": "\u0e04\u0e38\u0e13\u0e40\u0e1b\u0e47\u0e19 Premium \u0e2d\u0e22\u0e39\u0e48\u0e41\u0e25\u0e49\u0e27"}), 400

    plan = SubscriptionPlan.get_by_id(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e41\u0e1e\u0e47\u0e04\u0e40\u0e01\u0e08"}), 404

    pending = PaymentTransaction.get_pending_by_user(user_id, plan_id)
    if pending:
        return jsonify({"ok": True, "redirect": url_for("payment.payment_page", ref_code=pending["reference_code"])})

    txn = PaymentTransaction.create(user_id=user_id, plan_id=plan_id, amount=plan["price"])
    return jsonify({"ok": True, "redirect": url_for("payment.payment_page", ref_code=txn["reference_code"])})
