# ==============================================================================
# FILE: blueprints/student.py
# Student Portal: login with join_code, dashboard, view assignments & scores
# ==============================================================================

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort

from models import (
    Classroom, ClassroomStudent, Assignment, PracticeLink,
    PracticeSubmission, get_db,
)

student_bp = Blueprint("student", __name__)


def _student_logged_in():
    """Check if student is logged in via session."""
    return "student_id" in session and "student_classroom_id" in session


def _get_student_or_redirect():
    """Get current student or redirect to login."""
    if not _student_logged_in():
        return None
    student = ClassroomStudent.get_by_id(session["student_id"])
    if not student or student["classroom_id"] != session["student_classroom_id"]:
        session.pop("student_id", None)
        session.pop("student_classroom_id", None)
        session.pop("student_name", None)
        return None
    return student


# ==============================================================================
# Student Login
# ==============================================================================
@student_bp.route("/student", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        step = request.form.get("step", "code")

        if step == "code":
            # Step 1: Enter join code
            join_code = (request.form.get("join_code") or "").strip().upper()
            if not join_code:
                flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e01\u0e23\u0e2d\u0e01\u0e23\u0e2b\u0e31\u0e2a\u0e2b\u0e49\u0e2d\u0e07\u0e40\u0e23\u0e35\u0e22\u0e19", "error")
                return render_template("student_login.html", step="code")

            classroom = Classroom.get_by_join_code(join_code)
            if not classroom:
                flash("\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e2b\u0e49\u0e2d\u0e07\u0e40\u0e23\u0e35\u0e22\u0e19 \u0e01\u0e23\u0e38\u0e13\u0e32\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e23\u0e2b\u0e31\u0e2a\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07", "error")
                return render_template("student_login.html", step="code")

            students = ClassroomStudent.get_by_classroom(classroom["id"])
            if not students:
                flash("\u0e2b\u0e49\u0e2d\u0e07\u0e40\u0e23\u0e35\u0e22\u0e19\u0e19\u0e35\u0e49\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e21\u0e35\u0e23\u0e32\u0e22\u0e0a\u0e37\u0e48\u0e2d\u0e19\u0e31\u0e01\u0e40\u0e23\u0e35\u0e22\u0e19", "error")
                return render_template("student_login.html", step="code")

            return render_template("student_login.html", step="select",
                                   classroom=classroom, students=students, join_code=join_code)

        elif step == "select":
            # Step 2: Select student name
            join_code = (request.form.get("join_code") or "").strip().upper()
            student_id = request.form.get("student_id")

            classroom = Classroom.get_by_join_code(join_code)
            if not classroom:
                flash("\u0e40\u0e01\u0e34\u0e14\u0e02\u0e49\u0e2d\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14", "error")
                return render_template("student_login.html", step="code")

            student = ClassroomStudent.get_by_id(int(student_id)) if student_id else None
            if not student or student["classroom_id"] != classroom["id"]:
                flash("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e25\u0e37\u0e2d\u0e01\u0e0a\u0e37\u0e48\u0e2d\u0e02\u0e2d\u0e07\u0e04\u0e38\u0e13", "error")
                students = ClassroomStudent.get_by_classroom(classroom["id"])
                return render_template("student_login.html", step="select",
                                       classroom=classroom, students=students, join_code=join_code)

            # Login success
            session["student_id"] = student["id"]
            session["student_classroom_id"] = classroom["id"]
            session["student_name"] = student.get("student_name", "")
            return redirect(url_for("student.student_dashboard"))

    return render_template("student_login.html", step="code")


# ==============================================================================
# Student Dashboard
# ==============================================================================
@student_bp.route("/student/dashboard")
def student_dashboard():
    student = _get_student_or_redirect()
    if not student:
        return redirect(url_for("student.student_login"))

    classroom = Classroom.get_by_id(session["student_classroom_id"])
    if not classroom:
        return redirect(url_for("student.student_login"))

    assignments = Assignment.get_by_classroom(classroom["id"])

    # Build assignment data with student's submission status
    assignment_data = []
    total_score = 0
    total_possible = 0
    completed_count = 0

    s_name = (student.get("student_name") or "").strip().lower()
    s_no = (student.get("student_no") or "").strip()

    for a in assignments:
        link = PracticeLink.get_by_id(a.get("practice_link_id")) if a.get("practice_link_id") else None
        my_submission = None

        if link:
            submissions = PracticeSubmission.get_by_link(link["id"])
            for sub in submissions:
                sub_name = (sub.get("student_name") or "").strip().lower()
                sub_no = (sub.get("student_no") or "").strip()
                if (s_name and sub_name == s_name) or (s_no and sub_no and sub_no == s_no):
                    my_submission = sub
                    break

        ptype = link.get("practice_type", "mcq") if link else "mcq"

        item = {
            "id": a["id"],
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "topic_name": a.get("topic_name", ""),
            "due_date": a.get("due_date", ""),
            "created_at": a.get("created_at", ""),
            "practice_type": ptype,
            "practice_type_label": {"mcq": "MCQ", "fill": "Fill Blanks", "unscramble": "Unscramble"}.get(ptype, "MCQ"),
            "link_token": link["token"] if link else None,
            "submission": my_submission,
        }

        if my_submission:
            completed_count += 1
            total_score += my_submission.get("score", 0)
            total_possible += my_submission.get("total", 0)

        assignment_data.append(item)

    overall_pct = (total_score / total_possible * 100) if total_possible > 0 else 0

    return render_template(
        "student_dashboard.html",
        student=student,
        classroom=classroom,
        assignments=assignment_data,
        completed_count=completed_count,
        total_assignments=len(assignments),
        total_score=total_score,
        total_possible=total_possible,
        overall_pct=overall_pct,
    )


# ==============================================================================
# Student Logout
# ==============================================================================
@student_bp.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    session.pop("student_classroom_id", None)
    session.pop("student_name", None)
    return redirect(url_for("student.student_login"))
