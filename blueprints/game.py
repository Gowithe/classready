# ==============================================================================
# FILE: blueprints/game.py
# Game Blueprint: game hub, memory, millionaire, sentence builder
# ==============================================================================

import json

from flask import Blueprint, render_template, request, jsonify, session

from models import (
    get_db, Topic, GameQuestion, GameSession, PracticeQuestion,
)
from blueprints.helpers import login_required, _get_topic_or_404, _json_error

game_bp = Blueprint("game", __name__)


# ==============================================================================
# Shared Helpers (game-specific)
# ==============================================================================
def _topic_slides_obj(topic):
    """Parse topic['slides_json'] into dict. Always returns dict."""
    try:
        raw = topic.get("slides_json") or ""
        obj = json.loads(raw) if raw else {}
        if isinstance(obj, list):
            return {"slides": obj}
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"slides": []}


def _topic_get_sentence_builder_custom(topic):
    obj = _topic_slides_obj(topic)
    items = obj.get("sentence_builder_custom") or []
    out = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                th = (it.get("th") or "").strip()
                en = (it.get("en") or "").strip()
                if th or en:
                    out.append({"th": th, "en": en})
    return out


def _topic_save_sentence_builder_custom(topic_id, items):
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return False
    obj = _topic_slides_obj(topic)
    cleaned = []
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            th = (it.get("th") or "").strip()
            en = (it.get("en") or "").strip()
            if not th and not en:
                continue
            cleaned.append({"th": th[:500], "en": en[:500]})
    obj["sentence_builder_custom"] = cleaned
    Topic.update(topic_id, topic["name"], topic.get("description") or "", json.dumps(obj, ensure_ascii=False), topic.get("pdf_file"))
    return True


def _normalize_practice_questions(rows):
    """Normalize practice question rows (same as in app.py)."""
    out = []
    for r in rows:
        q = dict(r)
        if q.get("choices"):
            try:
                q["choices"] = json.loads(q["choices"]) if isinstance(q["choices"], str) else q["choices"]
            except Exception:
                q["choices"] = []
        else:
            q["choices"] = []
        out.append(q)
    return out


def _get_practice_data_from_slides(topic):
    """Extract fill-in-the-blank sentences from slides."""
    sentences = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
            for slide in slides:
                if slide.get("type") in ("grammar", "reading", "activity"):
                    for ex in (slide.get("examples") or []):
                        if isinstance(ex, str) and ex.strip():
                            sentences.append(ex.strip())
                        elif isinstance(ex, dict):
                            s = ex.get("sentence") or ex.get("en") or ex.get("text") or ""
                            if s.strip():
                                sentences.append(s.strip())
                    for s in (slide.get("sentences") or []):
                        if isinstance(s, str) and s.strip():
                            sentences.append(s.strip())
                        elif isinstance(s, dict):
                            txt = s.get("sentence") or s.get("en") or s.get("text") or ""
                            if txt.strip():
                                sentences.append(txt.strip())
        except Exception:
            pass
    return sentences


# ==============================================================================
# Game Hub
# ==============================================================================
@game_bp.route("/topic/<int:topic_id>/game")
@login_required
def game(topic_id):
    topic = _get_topic_or_404(topic_id)
    last_session = GameSession.get_latest_by_topic_and_user(topic_id, session["user_id"])
    return render_template("game.html", topic=topic, last_session=last_session)


# ==============================================================================
# Game APIs: sets & sessions
# ==============================================================================
@game_bp.route("/api/game/<int:topic_id>/sets")
@login_required
def api_game_sets(topic_id):
    _get_topic_or_404(topic_id)
    sets_data = {}
    for set_no in range(1, 4):
        questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        if questions:
            sets_data[str(set_no)] = [
                {"id": q["id"], "tile_no": q["tile_no"], "question": q["question"], "answer": q["answer"], "points": q["points"]}
                for q in questions
            ]
    return jsonify(sets_data)


@game_bp.route("/api/game/<int:topic_id>/sessions", methods=["GET", "POST"])
@login_required
def api_game_sessions(topic_id):
    _get_topic_or_404(topic_id)
    if request.method == "GET":
        return jsonify({"ok": True, "sessions": GameSession.get_by_topic(topic_id)})
    data = request.get_json(silent=True) or {}
    sess = GameSession.create(topic_id, session["user_id"], data.get("title") or "Session", json.dumps(data.get("settings") or {}), json.dumps(data.get("state") or {}))
    return jsonify({"ok": True, "session": sess})


@game_bp.route("/api/game/session/<int:session_id>")
@login_required
def api_game_session_get(session_id):
    sess = GameSession.get_by_id(session_id)
    return jsonify({"ok": True, "session": sess}) if sess else _json_error("Not found", 404)


@game_bp.route("/api/game/session/<int:session_id>/save", methods=["POST"])
@login_required
def api_game_session_save(session_id):
    sess = GameSession.get_by_id(session_id)
    if not sess:
        return _json_error("Not found", 404)
    data = request.get_json(silent=True) or {}
    GameSession.update(session_id, data.get("title") or sess["title"], json.dumps(data.get("settings") or {}), json.dumps(data.get("state") or {}))
    return jsonify({"ok": True})


# ==============================================================================
# Memory Match Game
# ==============================================================================
@game_bp.route("/topic/<int:topic_id>/game/memory")
@login_required
def game_memory(topic_id):
    topic = _get_topic_or_404(topic_id)

    vocabulary = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
            for slide in slides:
                if slide.get("type") == "vocabulary" and slide.get("vocabulary"):
                    for v in slide["vocabulary"]:
                        if v.get("word") and v.get("meaning"):
                            vocabulary.append({"word": v["word"], "meaning": v["meaning"]})
        except Exception:
            pass

    questions = []
    for set_no in range(1, 4):
        qs = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        for q in qs:
            questions.append({"question": q["question"], "answer": q["answer"]})

    game_data = {"vocabulary": vocabulary, "questions": questions}
    return render_template("game_memory.html", topic=topic, game_data=game_data)


# ==============================================================================
# Millionaire Game
# ==============================================================================
@game_bp.route("/topic/<int:topic_id>/game/millionaire")
@login_required
def game_millionaire(topic_id):
    topic = _get_topic_or_404(topic_id)
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    return render_template("game_millionaire.html", topic=topic, questions=questions)


# ==============================================================================
# Sentence Builder Game
# ==============================================================================
@game_bp.route("/api/topic/<int:topic_id>/sentence-builder/custom", methods=["GET", "POST"])
@login_required
def api_sentence_builder_custom(topic_id):
    topic = _get_topic_or_404(topic_id)
    if request.method == "GET":
        return jsonify({"ok": True, "items": _topic_get_sentence_builder_custom(topic)})
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    ok = _topic_save_sentence_builder_custom(topic_id, items)
    return jsonify({"ok": bool(ok), "items": _topic_get_sentence_builder_custom(Topic.get_by_id(topic_id))})


@game_bp.route("/topic/<int:topic_id>/game/sentence-builder")
@login_required
def game_sentence_builder(topic_id):
    topic = _get_topic_or_404(topic_id)
    game_data = _get_practice_data_from_slides(topic)

    # NOTE: _sentence_builder_enrich_game_data_with_th remains in app.py (AI translation)
    # Import from app if needed or move translation logic here later
    try:
        from app import _sentence_builder_enrich_game_data_with_th
        game_data = _sentence_builder_enrich_game_data_with_th(topic, game_data)
    except ImportError:
        pass

    students = []
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT cs.student_name
        FROM classroom_students cs
        JOIN assignments a ON a.classroom_id = cs.classroom_id
        WHERE a.topic_id = ?
        ORDER BY cs.student_no, cs.student_name
    """, (topic_id,))
    rows = c.fetchall()
    conn.close()
    students = [r["student_name"] for r in rows] if rows else []

    return render_template("game_sentence_builder.html", topic=topic, game_data=game_data, students=students)
