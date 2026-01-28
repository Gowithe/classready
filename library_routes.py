# ==============================================================================
# LIBRARY SYSTEM - Routes
# เพิ่มใน app.py
# ==============================================================================

# ==============================================================================
# Library - คลังบทเรียน
# ==============================================================================

@app.route("/library")
@login_required
def library():
    """หน้าแรกคลังบทเรียน - แสดงวิชาทั้งหมด"""
    subjects = LibrarySubject.get_all_active()
    popular_units = LibraryUnit.get_popular_units(6)
    free_units = LibraryUnit.get_free_units(6)
    is_premium = UserSubscription.is_premium(session["user_id"])
    
    return render_template("library/index.html", 
                           subjects=subjects, 
                           popular_units=popular_units,
                           free_units=free_units,
                           is_premium=is_premium)


@app.route("/library/subject/<int:subject_id>")
@login_required
def library_subject(subject_id):
    """หน้าแสดงบทเรียนในวิชา"""
    subject = LibrarySubject.get_by_id(subject_id)
    if not subject:
        abort(404)
    
    units = LibraryUnit.get_by_subject(subject_id)
    is_premium = UserSubscription.is_premium(session["user_id"])
    
    # Mark which units user has cloned
    user_clones = {c["unit_id"]: c for c in LibraryClone.get_by_user(session["user_id"])}
    
    return render_template("library/subject.html",
                           subject=subject,
                           units=units,
                           is_premium=is_premium,
                           user_clones=user_clones)


@app.route("/library/unit/<int:unit_id>")
@login_required
def library_unit_detail(unit_id):
    """หน้ารายละเอียดบทเรียน"""
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        abort(404)
    
    # Increment view count
    LibraryUnit.increment_view(unit_id)
    
    is_premium = UserSubscription.is_premium(session["user_id"])
    can_access = unit["is_free"] == 1 or is_premium
    has_cloned = LibraryClone.has_cloned(session["user_id"], unit_id)
    user_rating = LibraryRating.get_user_rating(session["user_id"], unit_id)
    
    # Parse slides for preview
    slides_preview = []
    if unit.get("slides_json"):
        try:
            slides_data = json.loads(unit["slides_json"])
            slides = slides_data.get("slides", slides_data) if isinstance(slides_data, dict) else slides_data
            # Show limited slides if not premium and not free
            if can_access:
                slides_preview = slides
            else:
                slides_preview = slides[:unit.get("preview_slides", 3)]
        except:
            pass
    
    return render_template("library/unit_detail.html",
                           unit=unit,
                           is_premium=is_premium,
                           can_access=can_access,
                           has_cloned=has_cloned,
                           user_rating=user_rating,
                           slides_preview=slides_preview,
                           total_slides=len(slides_preview) if can_access else "?")


@app.route("/library/unit/<int:unit_id>/clone", methods=["POST"])
@login_required
def library_clone_unit(unit_id):
    """Clone บทเรียนไปเป็น Topic ของตัวเอง"""
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        return jsonify({"ok": False, "error": "Unit not found"}), 404
    
    is_premium = UserSubscription.is_premium(session["user_id"])
    can_access = unit["is_free"] == 1 or is_premium
    
    if not can_access:
        return jsonify({"ok": False, "error": "Premium required"}), 403
    
    # Check if already cloned
    if LibraryClone.has_cloned(session["user_id"], unit_id):
        # Return existing topic
        clones = LibraryClone.get_by_user(session["user_id"])
        for c in clones:
            if c["unit_id"] == unit_id:
                return jsonify({"ok": True, "topic_id": c["topic_id"], "already_cloned": True})
    
    # Create new topic from unit
    topic = Topic.create(
        owner_id=session["user_id"],
        name=unit["name"],
        description=unit.get("description") or f"จาก Library: {unit.get('subject_name', '')}",
        slides_json=unit.get("slides_json") or "{}",
        topic_type="library",
        pdf_file=None
    )
    
    # Copy game questions if available
    if unit.get("game_json"):
        try:
            game_data = json.loads(unit["game_json"])
            for set_no, questions in game_data.items():
                if isinstance(questions, list):
                    for q in questions:
                        GameQuestion.create(
                            topic_id=topic["id"],
                            set_no=int(set_no),
                            question=q.get("question", ""),
                            answer=q.get("answer", ""),
                            points=q.get("points", 10)
                        )
        except:
            pass
    
    # Copy practice questions if available
    if unit.get("practice_json"):
        try:
            practice_data = json.loads(unit["practice_json"])
            if isinstance(practice_data, list):
                for q in practice_data:
                    PracticeQuestion.create(
                        topic_id=topic["id"],
                        question=q.get("question", ""),
                        choices=q.get("choices", []),
                        correct_index=q.get("correct_index", 0),
                        explanation=q.get("explain", q.get("explanation", ""))
                    )
        except:
            pass
    
    # Record clone
    LibraryClone.create(session["user_id"], unit_id, topic["id"])
    
    return jsonify({"ok": True, "topic_id": topic["id"]})


@app.route("/library/unit/<int:unit_id>/rate", methods=["POST"])
@login_required
def library_rate_unit(unit_id):
    """Rate บทเรียน"""
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        return jsonify({"ok": False, "error": "Unit not found"}), 404
    
    data = request.get_json() or {}
    rating = int(data.get("rating", 0))
    review = (data.get("review") or "").strip()
    
    if rating < 1 or rating > 5:
        return jsonify({"ok": False, "error": "Rating must be 1-5"}), 400
    
    LibraryRating.rate(session["user_id"], unit_id, rating, review)
    
    # Get updated unit
    updated_unit = LibraryUnit.get_by_id(unit_id)
    
    return jsonify({"ok": True, "avg_rating": updated_unit.get("avg_rating", 0)})


@app.route("/library/search")
@login_required
def library_search():
    """ค้นหาบทเรียน"""
    q = request.args.get("q", "").strip()
    subject_id = request.args.get("subject_id", type=int)
    free_only = request.args.get("free_only") == "1"
    
    results = []
    if q:
        results = LibraryUnit.search(q, subject_id, free_only)
    
    is_premium = UserSubscription.is_premium(session["user_id"])
    subjects = LibrarySubject.get_all_active()
    
    return render_template("library/search.html",
                           query=q,
                           results=results,
                           subjects=subjects,
                           selected_subject=subject_id,
                           free_only=free_only,
                           is_premium=is_premium)


# ==============================================================================
# Premium / Subscription
# ==============================================================================

@app.route("/premium")
@login_required
def premium_page():
    """หน้าแนะนำ Premium"""
    plans = SubscriptionPlan.get_all_active()
    current_sub = UserSubscription.get_active_subscription(session["user_id"])
    
    return render_template("library/premium.html",
                           plans=plans,
                           current_sub=current_sub)


@app.route("/premium/subscribe/<int:plan_id>", methods=["POST"])
@login_required
def premium_subscribe(plan_id):
    """สมัคร Premium (สำหรับ demo - จริงๆ ต้องผ่าน payment gateway)"""
    plan = SubscriptionPlan.get_by_id(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "Plan not found"}), 404
    
    # TODO: Integrate with payment gateway (Stripe, Omise, etc.)
    # For now, just create subscription directly (demo mode)
    
    sub = UserSubscription.create(
        user_id=session["user_id"],
        plan_id=plan_id,
        duration_days=plan["duration_days"],
        payment_ref="demo_" + str(int(datetime.utcnow().timestamp()))
    )
    
    flash(f"สมัคร {plan['name']} สำเร็จ!", "success")
    return jsonify({"ok": True, "subscription_id": sub["id"]})


# ==============================================================================
# Admin - Library Management
# ==============================================================================

@app.route("/admin/library")
@login_required
def admin_library():
    """Admin: จัดการคลังบทเรียน"""
    if not _is_admin():
        abort(403)
    
    subjects = LibrarySubject.get_all_active()
    return render_template("admin/library.html", subjects=subjects)


@app.route("/admin/library/subject/create", methods=["GET", "POST"])
@login_required
def admin_library_subject_create():
    """Admin: สร้างวิชาใหม่"""
    if not _is_admin():
        abort(403)
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("กรุณาใส่ชื่อวิชา", "error")
            return render_template("admin/library_subject_edit.html", subject=None)
        
        subject = LibrarySubject.create(
            name=name,
            description=request.form.get("description", ""),
            grade_level=request.form.get("grade_level", ""),
            subject_type=request.form.get("subject_type", "english"),
            icon=request.form.get("icon", "📚"),
            color=request.form.get("color", "#667eea")
        )
        flash("สร้างวิชาสำเร็จ", "success")
        return redirect(url_for("admin_library"))
    
    return render_template("admin/library_subject_edit.html", subject=None)


@app.route("/admin/library/subject/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
def admin_library_subject_edit(subject_id):
    """Admin: แก้ไขวิชา"""
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
            icon=request.form.get("icon", "📚"),
            color=request.form.get("color", "#667eea")
        )
        flash("บันทึกสำเร็จ", "success")
        return redirect(url_for("admin_library"))
    
    return render_template("admin/library_subject_edit.html", subject=subject)


@app.route("/admin/library/unit/create/<int:subject_id>", methods=["GET", "POST"])
@login_required
def admin_library_unit_create(subject_id):
    """Admin: สร้างบทเรียนใหม่"""
    if not _is_admin():
        abort(403)
    
    subject = LibrarySubject.get_by_id(subject_id)
    if not subject:
        abort(404)
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("กรุณาใส่ชื่อบทเรียน", "error")
            return render_template("admin/library_unit_edit.html", subject=subject, unit=None)
        
        unit = LibraryUnit.create(
            subject_id=subject_id,
            name=name,
            unit_number=int(request.form.get("unit_number", 1)),
            description=request.form.get("description", ""),
            is_free=request.form.get("is_free") == "1",
            estimated_time=int(request.form.get("estimated_time", 60))
        )
        flash("สร้างบทเรียนสำเร็จ", "success")
        return redirect(url_for("admin_library_unit_edit", unit_id=unit["id"]))
    
    return render_template("admin/library_unit_edit.html", subject=subject, unit=None)


@app.route("/admin/library/unit/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
def admin_library_unit_edit(unit_id):
    """Admin: แก้ไขบทเรียน"""
    if not _is_admin():
        abort(403)
    
    unit = LibraryUnit.get_by_id(unit_id)
    if not unit:
        abort(404)
    
    subject = LibrarySubject.get_by_id(unit["subject_id"])
    
    if request.method == "POST":
        LibraryUnit.update(
            unit_id,
            name=request.form.get("name", "").strip(),
            unit_number=int(request.form.get("unit_number", 1)),
            description=request.form.get("description", ""),
            is_free=1 if request.form.get("is_free") == "1" else 0,
            estimated_time=int(request.form.get("estimated_time", 60)),
            slides_json=request.form.get("slides_json", ""),
            game_json=request.form.get("game_json", ""),
            practice_json=request.form.get("practice_json", "")
        )
        flash("บันทึกสำเร็จ", "success")
        return redirect(url_for("admin_library_unit_edit", unit_id=unit_id))
    
    return render_template("admin/library_unit_edit.html", subject=subject, unit=unit)


@app.route("/admin/library/unit/<int:unit_id>/import-from-topic/<int:topic_id>", methods=["POST"])
@login_required
def admin_library_import_from_topic(unit_id, topic_id):
    """Admin: Import เนื้อหาจาก Topic ที่มีอยู่"""
    if not _is_admin():
        abort(403)
    
    unit = LibraryUnit.get_by_id(unit_id)
    topic = Topic.get_by_id(topic_id)
    
    if not unit or not topic:
        return jsonify({"ok": False, "error": "Not found"}), 404
    
    # Copy slides
    slides_json = topic.get("slides_json", "{}")
    
    # Copy game questions
    game_data = {}
    for set_no in [1, 2, 3]:
        questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        if questions:
            game_data[str(set_no)] = [{"question": q["question"], "answer": q["answer"], "points": q["points"]} for q in questions]
    
    # Copy practice questions
    practice_questions = PracticeQuestion.get_by_topic(topic_id)
    practice_data = [{"question": q["question"], "choices": json.loads(q["choices_json"]) if q.get("choices_json") else [], "correct_index": q["correct_index"], "explain": q.get("explanation", "")} for q in practice_questions]
    
    LibraryUnit.update(
        unit_id,
        slides_json=slides_json,
        game_json=json.dumps(game_data, ensure_ascii=False) if game_data else "",
        practice_json=json.dumps(practice_data, ensure_ascii=False) if practice_data else ""
    )
    
    return jsonify({"ok": True})
