# ==============================================================================
# FILE: blueprints/classroom.py
# Classroom Blueprint: classrooms, students, assignments
# ==============================================================================

import secrets
import json

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, jsonify

from models import (
    Classroom, ClassroomStudent, Assignment, Topic, PracticeLink,
    PracticeQuestion, PracticeSubmission, UsageLimits,
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
    return render_template("classrooms.html", classrooms=cls_list, total_students=total_students, total_assignments=len(assignments))


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
                if sub_name == student_name_lower or (sub_no and sub_no == student_no):
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

    return render_template(
        "classroom_detail.html",
        classroom=cls, students=students, assignments=assignments, topics=topics,
        submission_stats=submission_stats, scores_by_student=scores_by_student,
        assignment_stats=assignment_stats, class_avg=class_avg,
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
    topic_id = int(request.form.get("topic_id") or 0)
    if not topic_id:
        flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e25\u0e37\u0e2d\u0e01 Topic", "error")
        return redirect(url_for("classroom.classroom_detail", classroom_id=classroom_id))
    topic = Topic.get_by_id(topic_id)
    if not topic:
        abort(404)
    exercise_type = request.form.get("exercise_type", "mcq")
    link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12), exercise_type)
    title = (request.form.get("title") or "").strip() or topic["name"]
    due_date = request.form.get("due_date") or None
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
    topic = Topic.get_by_id(a["topic_id"])
    status = Assignment.get_submissions_status(assignment_id)
    practice_link = PracticeLink.get_by_id(a.get("practice_link_id")) if a.get("practice_link_id") else None
    student_url = (request.url_root.rstrip("/") + url_for("practice.public_practice", token=practice_link["token"])) if practice_link else None
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
    )


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
