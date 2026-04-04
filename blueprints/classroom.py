# ==============================================================================
# FILE: blueprints/classroom.py
# Classroom Blueprint: classrooms, students, assignments
# ==============================================================================

import secrets
import json

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, jsonify

from models import (
    Classroom, ClassroomStudent, Assignment, Topic, PracticeLink,
    PracticeQuestion, PracticeSubmission, UsageLimits, HomeworkSubmission,
    Attendance, StudentExtraScores, TeachingSchedule,
)
from blueprints.helpers import login_required, is_premium_user, _get_topic_or_404

classroom_bp = Blueprint("classroom", __name__)


# ==============================================================================
# Classrooms List
# ==============================================================================
@classroom_bp.route("/classrooms")
@login_required
def classrooms():
    user_id = session["user_id"]
    cls_list = Classroom.get_by_owner(user_id)
    total_students = sum(c.get("student_count") or 0 for c in cls_list)
    assignments = Assignment.get_by_owner(user_id)
    for c in cls_list:
        c["assignment_count"] = len([a for a in assignments if a["classroom_id"] == c["id"]])
    return render_template("classrooms.html", classrooms=cls_list, total_students=total_students,
                           total_assignments=len(assignments),
                           schedule=TeachingSchedule.get_by_owner(user_id))


# ==============================================================================
# Create Classroom
# ==============================================================================
@classroom_bp.route("/classrooms/create", methods=["POST"])
@login_required
def classroom_create():
    is_premium = is_premium_user(session["user_id"])
    can_create, msg = UsageLimits.can_create_classroom(session["user_id"], is_premium)

    if not can_create:
        flash(f"\u274c {msg} - \u0e2d\u0e31\u0e1b\u0e40\u0e01\u0e23\u0e14\u0e40\u0e1b\u0e47\u0e19 Premium!", "error")
        return redirect(url_for("payment.pricing"))

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e23\u0e30\u0e1a\u0e38\u0e0a\u0e37\u0e48\u0e2d\u0e2b\u0e49\u0e2d\u0e07", "error")
        return redirect(url_for("classroom.classrooms"))

    Classroom.create(
        session["user_id"],
        name,
        request.form.get("grade_level") or "",
        request.form.get("academic_year") or "",
        request.form.get("description") or "",
    )
    flash("\u2705 \u0e2a\u0e23\u0e49\u0e32\u0e07\u0e2b\u0e49\u0e2d\u0e07\u0e40\u0e23\u0e35\u0e22\u0e19\u0e41\u0e25\u0e49\u0e27", "success")
    return redirect(url_for("classroom.classrooms"))


# ==============================================================================
# Classroom Detail
# ==============================================================================
@classroom_bp.route("/classroom/<int:classroom_id>")
@login_required
def classroom_detail(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    students = ClassroomStudent.get_by_classroom(classroom_id)
    assignments = Assignment.get_by_classroom(classroom_id)
    topics = Topic.get_by_owner(session["user_id"])

    submission_stats = {}
    assignment_stats = {}
    scores_by_student = {s["id"]: {"assignments": {}, "total_score": 0, "total_possible": 0} for s in students}

    for a in assignments:
        exercise_type = a.get("exercise_type") or "mcq"

        if exercise_type == "homework":
            # Homework: get from homework_submissions
            hw_subs = HomeworkSubmission.get_by_assignment(a["id"])
            hw_student_ids = set(h["student_id"] for h in hw_subs)
            submitted_count = len(hw_student_ids)
            not_submitted_count = len(students) - submitted_count
            submission_stats[a["id"]] = {"submitted": submitted_count, "not_submitted": not_submitted_count}

            graded = [h for h in hw_subs if h.get("score") is not None]
            if graded:
                avg = sum(h["score"] / (h.get("max_score") or 10) * 100 for h in graded) / len(graded)
                assignment_stats[a["id"]] = {"avg": avg, "count": len(graded)}
            else:
                assignment_stats[a["id"]] = {"avg": 0, "count": 0}

            for student in students:
                student_id = student["id"]
                for h in hw_subs:
                    if h["student_id"] == student_id and h.get("score") is not None:
                        max_s = h.get("max_score") or 10
                        scores_by_student[student_id]["assignments"][a["id"]] = {
                            "score": h["score"],
                            "total": max_s,
                            "percentage": h["score"] / max_s * 100 if max_s else 0,
                        }
                        scores_by_student[student_id]["total_score"] += h["score"]
                        scores_by_student[student_id]["total_possible"] += max_s
                        break
        else:
            # MCQ/Fill/Unscramble: existing logic
            status = Assignment.get_submissions_status(a["id"])
            submission_stats[a["id"]] = {"submitted": len(status["submitted"]), "not_submitted": len(status["not_submitted"])}

            submissions = status.get("submissions") or []
            if submissions:
                avg = sum(s.get("percentage") or 0 for s in submissions) / len(submissions)
                assignment_stats[a["id"]] = {"avg": avg, "count": len(submissions)}
            else:
                assignment_stats[a["id"]] = {"avg": 0, "count": 0}

            for student in students:
                student_id = student["id"]
                student_name_lower = (student.get("student_name") or "").strip().lower()
                student_no = (student.get("student_no") or "").strip()

                for sub in submissions:
                    sub_name = (sub.get("student_name") or "").strip().lower()
                    sub_no = (sub.get("student_no") or "").strip()
                    if (student_name_lower and sub_name == student_name_lower) or (sub_no and sub_no == student_no):
                        scores_by_student[student_id]["assignments"][a["id"]] = {
                            "score": sub.get("score", 0),
                            "total": sub.get("total", 0),
                            "percentage": sub.get("percentage", 0),
                        }
                        scores_by_student[student_id]["total_score"] += sub.get("score", 0)
                        scores_by_student[student_id]["total_possible"] += sub.get("total", 0)
                        break

    class_avg = 0
    students_with_scores = [s for s in scores_by_student.values() if s["total_possible"] > 0]
    if students_with_scores:
        class_avg = sum((s["total_score"] / s["total_possible"] * 100) for s in students_with_scores) / len(students_with_scores)

    # Attendance summary
    attendance_summary = Attendance.get_summary(classroom_id)
    attendance_dates = Attendance.get_dates(classroom_id)

    # Extra scores (attitude, midterm, final)
    extra_scores = StudentExtraScores.get_by_classroom(classroom_id)

    # Grade calculation per student
    from datetime import date
    today = date.today().isoformat()

    grades = {}
    for s in students:
        sid = s["id"]
        sbs = scores_by_student.get(sid, {})
        es = extra_scores.get(sid, {})

        total_earned = sbs.get("total_score", 0)
        total_max = sbs.get("total_possible", 0)

        # Add extra scores
        for field, total_field in [("attitude_score", "attitude_total"),
                                    ("midterm_score", "midterm_total"),
                                    ("final_score", "final_total")]:
            val = es.get(field)
            if val is not None:
                total_earned += float(val)
                total_max += float(es.get(total_field) or 10)

        pct = (total_earned / total_max * 100) if total_max > 0 else 0
        grades[sid] = {
            "total_earned": total_earned,
            "total_max": total_max,
            "percentage": pct,
            "grade": StudentExtraScores.calc_grade(pct),
        }

    return render_template(
        "classroom_detail.html",
        classroom=cls, students=students, assignments=assignments, topics=topics,
        submission_stats=submission_stats, scores_by_student=scores_by_student,
        assignment_stats=assignment_stats, class_avg=class_avg,
        attendance_summary=attendance_summary, attendance_dates=attendance_dates,
        extra_scores=extra_scores, grades=grades, today=today,
    )


# ==============================================================================
# Edit / Delete Classroom
# ==============================================================================
@classroom_bp.route("/classroom/<int:classroom_id>/edit", methods=["POST"])
@login_required
def classroom_edit(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    Classroom.update(
        classroom_id,
        request.form.get("name") or cls["name"],
        request.form.get("grade_level") or "",
        request.form.get("academic_year") or "",
        request.form.get("description") or "",
    )
    flash("\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e41\u0e25\u0e49\u0e27", "success")
    return redirect(url_for("classroom.classrooms"))


@classroom_bp.route("/classroom/<int:classroom_id>/delete", methods=["POST"])
@login_required
def classroom_delete(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    Classroom.delete(classroom_id)
    flash("\u0e25\u0e1a\u0e2b\u0e49\u0e2d\u0e07\u0e40\u0e23\u0e35\u0e22\u0e19\u0e41\u0e25\u0e49\u0e27", "success")
    return redirect(url_for("classroom.classrooms"))


# ==============================================================================
# Attendance (เช็กชื่อ)
# ==============================================================================
@classroom_bp.route("/classroom/<int:classroom_id>/attendance", methods=["POST"])
@login_required
def classroom_attendance_save(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    check_date = request.form.get("check_date") or ""
    if not check_date:
        flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e25\u0e37\u0e2d\u0e01\u0e27\u0e31\u0e19\u0e17\u0e35\u0e48", "error")
        return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))

    students = ClassroomStudent.get_by_classroom(classroom_id)
    records = []
    for s in students:
        status = request.form.get(f"status_{s['id']}", "present")
        note = request.form.get(f"note_{s['id']}", "")
        records.append({"student_id": s["id"], "status": status, "note": note})

    Attendance.save_bulk(classroom_id, check_date, records)
    flash(f"\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e40\u0e0a\u0e47\u0e01\u0e0a\u0e37\u0e48\u0e2d\u0e27\u0e31\u0e19\u0e17\u0e35\u0e48 {check_date} \u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))


@classroom_bp.route("/api/classroom/<int:classroom_id>/attendance/<check_date>")
@login_required
def api_classroom_attendance(classroom_id, check_date):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        return jsonify({"error": "Not found"}), 404
    records = Attendance.get_by_date(classroom_id, check_date)
    return jsonify({"records": {r["student_id"]: {"status": r["status"], "note": r.get("note", "")} for r in records}})


# ==============================================================================
# Extra Scores (จิตพิสัย, สอบกลางภาค, สอบปลายภาค)
# ==============================================================================
@classroom_bp.route("/classroom/<int:classroom_id>/extra-scores", methods=["POST"])
@login_required
def classroom_extra_scores_save(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)

    students = ClassroomStudent.get_by_classroom(classroom_id)

    for s in students:
        sid = s["id"]
        data = {}
        for field in ("attitude_score", "attitude_total", "midterm_score", "midterm_total",
                      "final_score", "final_total"):
            raw = request.form.get(f"{field}_{sid}", "").strip()
            if raw != "":
                try:
                    data[field] = float(raw)
                except ValueError:
                    pass
        if data:
            StudentExtraScores.save(classroom_id, sid, **data)

    flash("\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e04\u0e30\u0e41\u0e19\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))


# ==============================================================================
# Teaching Schedule (ตารางสอน — per teacher)
# ==============================================================================
@classroom_bp.route("/classrooms/schedule", methods=["POST"])
@login_required
def classroom_schedule_save():
    entries = []
    for day in range(5):
        for period in range(1, 9):
            subject = request.form.get(f"subj_{day}_{period}", "").strip()
            room = request.form.get(f"room_{day}_{period}", "").strip()
            entries.append({"day_of_week": day, "period": period, "subject": subject, "room": room})

    TeachingSchedule.save_bulk(session["user_id"], entries)
    flash("\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e15\u0e32\u0e23\u0e32\u0e07\u0e2a\u0e2d\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("classroom.classrooms"))


# ==============================================================================
# Students CRUD
# ==============================================================================
@classroom_bp.route("/classroom/<int:classroom_id>/add-student", methods=["POST"])
@login_required
def classroom_add_student(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    name = (request.form.get("student_name") or "").strip()
    if name:
        ClassroomStudent.create(classroom_id, request.form.get("student_no") or "", name, request.form.get("nickname") or "")
        flash("\u0e40\u0e1e\u0e34\u0e48\u0e21\u0e19\u0e31\u0e01\u0e40\u0e23\u0e35\u0e22\u0e19\u0e41\u0e25\u0e49\u0e27", "success")
    return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))


@classroom_bp.route("/classroom/<int:classroom_id>/import-students", methods=["POST"])
@login_required
def classroom_import_students(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    text = request.form.get("student_list") or ""
    students = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            students.append({"student_no": parts[0].strip(), "student_name": parts[1].strip()})
        else:
            students.append({"student_no": "", "student_name": parts[0].strip()})
    count = ClassroomStudent.bulk_create(classroom_id, students)
    flash(f"Import {count} \u0e04\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))


@classroom_bp.route("/classroom/student/<int:student_id>/edit", methods=["POST"])
@login_required
def classroom_student_edit(student_id):
    s = ClassroomStudent.get_by_id(student_id)
    if not s:
        abort(404)
    cls = Classroom.get_by_id(s["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    ClassroomStudent.update(student_id, request.form.get("student_no") or "", request.form.get("student_name") or s["student_name"], request.form.get("nickname") or "")
    return redirect(url_for("classroom.classroom_detail", classroom_id=s["classroom_id"]))


@classroom_bp.route("/classroom/student/<int:student_id>/delete", methods=["POST"])
@login_required
def classroom_student_delete(student_id):
    s = ClassroomStudent.get_by_id(student_id)
    if not s:
        abort(404)
    cls = Classroom.get_by_id(s["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    classroom_id = s["classroom_id"]
    ClassroomStudent.delete(student_id)
    return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))


# ==============================================================================
# Assignments
# ==============================================================================
@classroom_bp.route("/classroom/<int:classroom_id>/assign", methods=["POST"])
@login_required
def classroom_assign(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)

    exercise_type = request.form.get("exercise_type", "mcq")
    title = (request.form.get("title") or "").strip()
    due_date = request.form.get("due_date") or None

    if exercise_type == "homework":
        # Homework: no topic/practice_link needed
        if not title:
            title = "\u0e01\u0e32\u0e23\u0e1a\u0e49\u0e32\u0e19"
        max_score = int(request.form.get("max_score") or 10)
        Assignment.create_homework(
            classroom_id, title,
            request.form.get("description") or "",
            due_date, session["user_id"], max_score
        )
    else:
        # MCQ / Fill / Unscramble: need topic
        topic_id = int(request.form.get("topic_id") or 0)
        if not topic_id:
            flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e25\u0e37\u0e2d\u0e01 Topic", "error")
            return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))
        topic = Topic.get_by_id(topic_id)
        if not topic:
            abort(404)
        link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12), exercise_type)
        if not title:
            title = topic["name"]
        Assignment.create(classroom_id, topic_id, link["id"], title, request.form.get("description") or "", due_date, session["user_id"])

    flash("\u0e2a\u0e31\u0e48\u0e07\u0e07\u0e32\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))


@classroom_bp.route("/assignment/<int:assignment_id>")
@login_required
def assignment_detail(assignment_id):
    a = Assignment.get_by_id(assignment_id)
    if not a:
        abort(404)
    cls = Classroom.get_by_id(a["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    topic = Topic.get_by_id(a["topic_id"]) if a.get("topic_id") else None
    exercise_type = a.get("exercise_type") or "mcq"

    # Homework type
    if exercise_type == "homework":
        students = ClassroomStudent.get_by_classroom(a["classroom_id"])
        hw_submissions = HomeworkSubmission.get_by_assignment(assignment_id)
        hw_student_ids = set(s["student_id"] for s in hw_submissions)
        submitted = [s for s in students if s["id"] in hw_student_ids]
        not_submitted = [s for s in students if s["id"] not in hw_student_ids]
        return render_template(
            "assignment_detail.html",
            assignment=a, classroom=cls, topic=topic,
            submitted=submitted, not_submitted=not_submitted,
            total_students=len(students),
            submitted_count=len(submitted),
            not_submitted_count=len(not_submitted),
            avg_score=0, practice_link=None, student_url=None,
            exercise_type="homework", hw_submissions=hw_submissions,
        )

    # MCQ/Fill/Unscramble type
    status = Assignment.get_submissions_status(assignment_id)
    practice_link = PracticeLink.get_by_id(a.get("practice_link_id")) if a.get("practice_link_id") else None
    student_url = None
    if practice_link:
        ptype = practice_link.get("practice_type", "mcq")
        if ptype == "fill":
            student_url = request.url_root.rstrip("/") + url_for("practice.public_fill_blanks", token=practice_link["token"])
        elif ptype == "unscramble":
            student_url = request.url_root.rstrip("/") + url_for("practice.public_unscramble", token=practice_link["token"])
        else:
            student_url = request.url_root.rstrip("/") + url_for("practice.public_practice", token=practice_link["token"])
    avg = 0
    submissions = status.get("submissions") or []
    if submissions:
        avg = sum(s.get("percentage") or 0 for s in submissions) / len(submissions)
    return render_template(
        "assignment_detail.html",
        assignment=a, classroom=cls, topic=topic,
        submitted=status["submitted"], not_submitted=status["not_submitted"],
        total_students=status["total"],
        submitted_count=len(status["submitted"]),
        not_submitted_count=len(status["not_submitted"]),
        avg_score=avg, practice_link=practice_link, student_url=student_url,
        exercise_type=exercise_type, hw_submissions=[],
    )


@classroom_bp.route("/assignment/<int:assignment_id>/grade/<int:sub_id>", methods=["POST"])
@login_required
def homework_grade(assignment_id, sub_id):
    a = Assignment.get_by_id(assignment_id)
    if not a:
        abort(404)
    cls = Classroom.get_by_id(a["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]:
        abort(404)
    score = int(request.form.get("score") or 0)
    max_score = int(request.form.get("max_score") or 10)
    comment = (request.form.get("comment") or "").strip()
    HomeworkSubmission.grade(sub_id, score, max_score, comment)
    flash("\u0e43\u0e2b\u0e49\u0e04\u0e30\u0e41\u0e19\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22", "success")
    return redirect(url_for("classroom.assignment_detail", assignment_id=assignment_id))


# ==============================================================================
# Classroom APIs
# ==============================================================================
@classroom_bp.route("/api/classrooms")
@login_required
def api_get_classrooms():
    user_id = session["user_id"]
    cls_list = Classroom.get_by_owner(user_id)
    return jsonify({"classrooms": [{"id": c["id"], "name": c["name"]} for c in cls_list]})


@classroom_bp.route("/api/classroom/<int:classroom_id>/students")
@login_required
def api_get_classroom_students(classroom_id):
    classroom = Classroom.get_by_id(classroom_id)
    if not classroom or classroom.get("owner_id") != session["user_id"]:
        return jsonify({"error": "Not found"}), 404
    students = ClassroomStudent.get_by_classroom(classroom_id)
    return jsonify({
        "students": [
            {"id": s["id"], "student_no": s.get("student_no") or "", "student_name": s.get("student_name") or ""}
            for s in students
        ]
    })


@classroom_bp.route("/api/public/classroom/<int:classroom_id>/students")
def api_public_classroom_students(classroom_id):
    students = ClassroomStudent.get_by_classroom(classroom_id)
    return jsonify([{"id": s["id"], "student_no": s.get("student_no") or "", "student_name": s.get("student_name") or ""} for s in students])
