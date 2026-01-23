# ==============================================================================
# FILE: app.py
# Teacher Platform MVP (Flask + SQLite)
# UPDATED: Classroom Management + Assignments + Game Sessions + Practice Export
# FIXED: Sentence Builder Syntax Error
# ==============================================================================

import os
import json
import secrets
import traceback
import base64
import csv
import re
from io import BytesIO, StringIO
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory, abort, Response
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from models import (
    get_db, init_db, User, Topic, GameQuestion, PracticeQuestion, AttemptHistory,
    PracticeLink, PracticeSubmission, GameSession, Classroom, ClassroomStudent, Assignment,
)
from ai_generator import generate_lesson_bundle

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename): return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
def allowed_image(filename): return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

with app.app_context():
    init_db()
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@teacherplatform.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    if not User.get_by_email(admin_email):
        User.create(admin_email, admin_password, "admin")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        user = User.get_by_id(session["user_id"])
        if not user or user.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

def _is_admin(): return session.get("role") == "admin"
def _can_access_topic(topic): return _is_admin() or int(topic.get("owner_id") or 0) == int(session.get("user_id") or 0)
def _get_topic_or_404(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic: abort(404)
    if not _can_access_topic(topic): abort(403)
    return topic

def _wants_json_response(): return request.path.startswith("/api/") or "application/json" in (request.headers.get("Accept") or "").lower()
def _json_error(message, status=400): return jsonify({"ok": False, "error": message}), status


# ==============================================================================
# Auth & Landing
# ==============================================================================
@app.route("/")
def landing(): return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        confirm = (request.form.get("confirm_password") or "").strip()
        if not email or not password:
            flash("Email and password required.", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if User.get_by_email(email):
            flash("Email already registered.", "error")
            return render_template("register.html")
        User.create(email, password, "teacher")
        flash("Registration successful!", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        user = User.get_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename): return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ==============================================================================
# Dashboard
# ==============================================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    my_topics = Topic.get_by_owner(user_id)
    all_topics = Topic.get_all() if _is_admin() else my_topics
    recent = AttemptHistory.get_recent_by_user(user_id, limit=5)
    classrooms = Classroom.get_by_owner(user_id)
    return render_template("dashboard.html", my_topics=my_topics, topics=all_topics, recent=recent, classrooms=classrooms)

@app.route("/topic/<int:topic_id>")
@login_required
def topic_detail(topic_id):
    topic = _get_topic_or_404(topic_id)
    AttemptHistory.track_view(session["user_id"], topic_id)
    is_owner = int(topic.get("owner_id") or 0) == int(session["user_id"])
    has_game = len(GameQuestion.get_by_topic_and_set(topic_id, 1) or []) > 0
    has_practice = len(PracticeQuestion.get_by_topic(topic_id) or []) > 0
    has_slides = False
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
            has_slides = len(slides) > 0
        except: pass
    return render_template("topic_detail.html", topic=topic, is_owner=is_owner, is_admin=_is_admin(), has_game=has_game, has_practice=has_practice, has_slides=has_slides)


# ==============================================================================
# My Topics CRUD
# ==============================================================================
@app.route("/my/topics/create", methods=["GET", "POST"])
@login_required
def my_create_topic():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Topic name required.", "error")
            return render_template("my_topic_edit.html", topic=None, mode="create")
        topic = Topic.create(session["user_id"], name, description, json.dumps({"slides": []}, ensure_ascii=False), "manual", None)
        return redirect(url_for("my_edit_topic", topic_id=topic["id"]))
    return render_template("my_topic_edit.html", topic=None, mode="create")

@app.route("/my/topics/<int:topic_id>/edit", methods=["GET", "POST"])
@login_required
def my_edit_topic(topic_id):
    topic = _get_topic_or_404(topic_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        slides_json = (request.form.get("slides_json") or "").strip()
        if not name:
            flash("Topic name required.", "error")
            return render_template("my_topic_edit.html", topic=topic, mode="edit")
        try: json.loads(slides_json)
        except:
            flash("Invalid JSON.", "error")
            return render_template("my_topic_edit.html", topic=topic, mode="edit")
        pdf_filename = topic.get("pdf_file")
        file = request.files.get("pdf_file")
        if file and file.filename and allowed_file(file.filename):
            safe_name = secure_filename(file.filename)
            final_name = f"user{session['user_id']}_topic{topic_id}_{secrets.token_hex(6)}_{safe_name}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], final_name))
            pdf_filename = final_name
        Topic.update(topic_id, name, description, slides_json, pdf_filename)
        flash("Saved.", "success")
        return redirect(url_for("topic_detail", topic_id=topic_id))
    return render_template("my_topic_edit.html", topic=topic, mode="edit")

@app.route("/my/topics/<int:topic_id>/delete", methods=["POST"])
@login_required
def my_delete_topic(topic_id):
    _get_topic_or_404(topic_id)
    Topic.delete(topic_id)
    return redirect(url_for("dashboard"))


# ==============================================================================
# Slides
# ==============================================================================
@app.route("/topic/<int:topic_id>/slides")
@login_required
def view_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    
    # Check if topic has generated slides first
    slides = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
        except: pass
    
    # If has slides, show slides viewer
    if slides:
        return render_template("slides_viewer.html", topic=topic, slides=slides)
    
    # If no slides but has PDF, show PDF presentation
    if topic.get("pdf_file"):
        return render_template("slides_pdf_presentation.html", topic=topic, pdf_url=url_for("uploaded_file", filename=topic["pdf_file"]))
    
    # No slides and no PDF - show empty slides viewer
    return render_template("slides_viewer.html", topic=topic, slides=[])

@app.route("/topic/<int:topic_id>/slides/edit")
@login_required
def edit_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    return render_template("slides_editor.html", topic=topic)

@app.route("/api/topic/<int:topic_id>/slides", methods=["POST"])
@login_required
def api_save_slides(topic_id):
    topic = _get_topic_or_404(topic_id)
    data = request.get_json(silent=True) or {}
    slides = data.get("slides", [])
    processed = []
    for i, slide in enumerate(slides):
        ps = dict(slide)
        img_url = slide.get("image_url", "")
        if img_url and img_url.startswith("data:image"):
            try:
                header, b64 = img_url.split(",", 1)
                ext = "png" if "png" in header else "gif" if "gif" in header else "jpg"
                fn = f"slide_img_{topic_id}_{i}_{secrets.token_hex(6)}.{ext}"
                with open(os.path.join(app.config["UPLOAD_FOLDER"], fn), "wb") as f:
                    f.write(base64.b64decode(b64))
                ps["image_url"] = url_for("uploaded_file", filename=fn)
            except: pass
        processed.append(ps)
    Topic.update(topic_id, topic["name"], topic["description"], json.dumps({"slides": processed}, ensure_ascii=False), topic.get("pdf_file"))
    return jsonify({"ok": True})


# ==============================================================================
# Download Slides as PDF
# ==============================================================================
@app.route("/topic/<int:topic_id>/slides/download")
@login_required
def download_slides_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)
    
    # Parse slides
    slides = []
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
        except: pass
    
    if not slides:
        flash("ไม่มีสไลด์", "error")
        return redirect(url_for("topic_detail", topic_id=topic_id))
    
    # Generate PDF
    pdf_bytes = _generate_slides_pdf(topic["name"], slides)
    
    # Clean filename
    safe_name = "".join(c for c in topic["name"] if c.isalnum() or c in " -_").strip()[:50] or "slides"
    
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_slides.pdf"}
    )


def _generate_slides_pdf(title, slides):
    """Generate a PDF from slides data - supports all slide types + Thai language"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import textwrap
    import urllib.request
    import tempfile
    
    buf = BytesIO()
    page_size = landscape(A4)
    c = canvas.Canvas(buf, pagesize=page_size)
    w, h = page_size
    
    # Register Thai font
    thai_font = "Helvetica"
    thai_font_bold = "Helvetica-Bold"
    thai_font_italic = "Helvetica-Oblique"
    
    # Try to find and register a Thai-compatible font
    font_paths = [
        # Windows fonts
        "C:/Windows/Fonts/THSarabunNew.ttf",
        "C:/Windows/Fonts/thsarabunnew.ttf",
        "C:/Windows/Fonts/Tahoma.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/cordia.ttf",
        "C:/Windows/Fonts/CordiaNew.ttf",
        "C:/Windows/Fonts/angsana.ttf",
        # Linux fonts
        "/usr/share/fonts/truetype/thai/TH Sarabun New.ttf",
        "/usr/share/fonts/truetype/tlwg/TlwgTypo.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        # Mac fonts
        "/Library/Fonts/Thonburi.ttf",
        "/System/Library/Fonts/Thonburi.ttc",
    ]
    
    font_bold_paths = [
        "C:/Windows/Fonts/THSarabunNew Bold.ttf",
        "C:/Windows/Fonts/thsarabunnew-bold.ttf",
        "C:/Windows/Fonts/tahomabd.ttf",
        "C:/Windows/Fonts/cordiab.ttf",
    ]
    
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("ThaiFont", fp))
                thai_font = "ThaiFont"
                thai_font_italic = "ThaiFont"
                print(f"Registered Thai font: {fp}")
                break
            except Exception as e:
                print(f"Failed to register font {fp}: {e}")
    
    for fp in font_bold_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("ThaiFontBold", fp))
                thai_font_bold = "ThaiFontBold"
                break
            except:
                pass
    
    # If no Thai font found, try to use THSarabun from uploads folder
    custom_font_path = os.path.join(app.config["UPLOAD_FOLDER"], "THSarabunNew.ttf")
    if thai_font == "Helvetica" and os.path.exists(custom_font_path):
        try:
            pdfmetrics.registerFont(TTFont("ThaiFont", custom_font_path))
            thai_font = "ThaiFont"
            thai_font_italic = "ThaiFont"
        except:
            pass
    
    # Colors
    primary_color = HexColor("#667eea")
    dark_color = HexColor("#1e293b")
    muted_color = HexColor("#64748b")
    bg_color = HexColor("#f8fafc")
    accent_color = HexColor("#10b981")
    
    # Adjust font size for Thai fonts (they're usually larger)
    base_size = 14 if thai_font != "Helvetica" else 12
    title_size = 24 if thai_font != "Helvetica" else 22
    
    def draw_bullet(x, y, text, max_width, font_size=None):
        """Draw a bullet point and return new y position"""
        if font_size is None:
            font_size = base_size
        if y < 2*cm:
            return y
        c.setFillColor(primary_color)
        c.circle(x, y + 0.12*cm, 0.1*cm, fill=1, stroke=0)
        c.setFillColor(dark_color)
        c.setFont(thai_font, font_size)
        wrapped = textwrap.wrap(str(text), width=int(max_width / 6))
        for line in wrapped[:3]:
            c.drawString(x + 0.5*cm, y, line)
            y -= 0.55*cm
        return y - 0.15*cm
    
    def extract_content_from_slide(slide):
        """Extract displayable content from any slide type"""
        slide_type = slide.get("type", "")
        items = []
        
        # Get content from various possible keys
        content = slide.get("content", [])
        if isinstance(content, str):
            items.append(content)
        elif isinstance(content, list):
            for ct in content:
                if isinstance(ct, str):
                    items.append(ct)
                elif isinstance(ct, dict):
                    en = ct.get("en") or ct.get("text") or ""
                    th = ct.get("th") or ct.get("meaning") or ""
                    if en:
                        items.append(f"{en}" + (f" ({th})" if th else ""))
        
        # Objectives
        objectives = slide.get("objectives", [])
        if isinstance(objectives, list):
            for obj in objectives:
                if isinstance(obj, str):
                    items.append(f"• {obj}")
        
        # Vocabulary
        vocabulary = slide.get("vocabulary", []) or slide.get("items", [])
        if isinstance(vocabulary, list) and slide_type in ["vocabulary", ""]:
            for v in vocabulary[:8]:
                if isinstance(v, dict):
                    word = v.get("word", "")
                    meaning = v.get("meaning", "") or v.get("th", "")
                    example = v.get("example", "") or v.get("example_en", "")
                    if word:
                        line = f"• {word}"
                        if meaning:
                            line += f" - {meaning}"
                        items.append(line)
                        if example:
                            items.append(f"  Ex: {example}")
        
        # Examples (en/th format)
        examples = slide.get("examples", [])
        if isinstance(examples, list):
            for ex in examples[:6]:
                if isinstance(ex, dict):
                    en = ex.get("en", "")
                    th = ex.get("th", "")
                    if en:
                        items.append(f"• {en}" + (f" ({th})" if th else ""))
                elif isinstance(ex, str):
                    items.append(f"• {ex}")
        
        # Highlights (for concept slides)
        highlights = slide.get("highlights", [])
        if isinstance(highlights, list):
            for hl in highlights[:5]:
                if isinstance(hl, dict):
                    label = hl.get("label", "")
                    note = hl.get("note", "")
                    if label:
                        items.append(f"• {label}: {note}" if note else f"• {label}")
        
        # Pattern/Structure (for concept slides)
        pattern = slide.get("pattern") or slide.get("structure", "")
        if pattern and isinstance(pattern, str):
            items.insert(0, f"📝 {pattern}")
        
        # Prompt (for hook slides)
        prompt = slide.get("prompt", "")
        if prompt and isinstance(prompt, str):
            items.insert(0, prompt)
        
        # Keywords
        keywords = slide.get("keywords", [])
        if isinstance(keywords, list) and keywords:
            items.append(f"Keywords: {', '.join(str(k) for k in keywords)}")
        
        # Dialogue lines
        lines = slide.get("lines", [])
        if isinstance(lines, list):
            for line in lines[:8]:
                if isinstance(line, dict):
                    speaker = line.get("speaker", "")
                    text = line.get("en") or line.get("text", "")
                    if speaker and text:
                        items.append(f"{speaker}: {text}")
                elif isinstance(line, str):
                    items.append(line)
        
        # Scenario
        scenario = slide.get("scenario", "")
        if scenario and isinstance(scenario, str):
            items.insert(0, f"🎭 {scenario}")
        
        # Guided practice items
        practice_items = slide.get("items", [])
        if isinstance(practice_items, list) and slide_type == "guided_practice":
            for pi in practice_items[:4]:
                if isinstance(pi, dict):
                    q = pi.get("q") or pi.get("question", "")
                    if q:
                        items.append(f"Q: {q}")
                    choices = pi.get("choices", [])
                    if choices:
                        items.append(f"   A) {choices[0] if len(choices) > 0 else ''}")
                        items.append(f"   B) {choices[1] if len(choices) > 1 else ''}")
                        items.append(f"   C) {choices[2] if len(choices) > 2 else ''}")
                        items.append(f"   D) {choices[3] if len(choices) > 3 else ''}")
        
        # Common mistakes
        mistakes = slide.get("common_mistakes", [])
        if isinstance(mistakes, list) and mistakes:
            items.append("")
            items.append("⚠️ Common mistakes:")
            for m in mistakes[:3]:
                items.append(f"  • {m}")
        
        # Bullets (generic)
        bullets = slide.get("bullets", [])
        if isinstance(bullets, list):
            for b in bullets:
                if isinstance(b, str):
                    items.append(f"• {b}")
        
        return items
    
    for i, slide in enumerate(slides):
        slide_title = slide.get("title", f"Slide {i+1}")
        slide_type = slide.get("type", "")
        image_url = slide.get("image_url", "")
        
        # Background
        c.setFillColor(bg_color)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        
        # Header bar
        c.setFillColor(primary_color)
        c.rect(0, h - 2.5*cm, w, 2.5*cm, fill=1, stroke=0)
        
        # Slide number
        c.setFillColor(HexColor("#ffffff"))
        c.setFont("Helvetica", 10)
        c.drawRightString(w - 1*cm, h - 1.5*cm, f"{i+1} / {len(slides)}")
        
        # Slide type badge
        if slide_type:
            c.setFont("Helvetica", 8)
            c.drawRightString(w - 1*cm, h - 2*cm, f"[{slide_type}]")
        
        # Title
        c.setFillColor(HexColor("#ffffff"))
        c.setFont(thai_font_bold, title_size)
        display_title = slide_title[:55] + "..." if len(slide_title) > 55 else slide_title
        c.drawString(1.5*cm, h - 1.7*cm, display_title)
        
        y = h - 4*cm
        content_width = w - 3*cm
        
        # Check if there's an image
        img_x = None
        if image_url and not image_url.startswith("data:"):
            content_width = w * 0.55
            img_x = w * 0.58
        
        # Extract and draw content
        content_items = extract_content_from_slide(slide)
        
        c.setFillColor(dark_color)
        c.setFont(thai_font, base_size)
        
        for item in content_items:
            if y < 2*cm:
                break
            
            item_str = str(item).strip()
            if not item_str:
                y -= 0.3*cm
                continue
            
            # Check for special formatting
            if item_str.startswith("•"):
                y = draw_bullet(1.5*cm, y, item_str[1:].strip(), content_width, base_size)
            elif item_str.startswith("  •"):
                y = draw_bullet(2.2*cm, y, item_str[3:].strip(), content_width - 0.7*cm, base_size - 1)
            elif item_str.startswith("📝") or item_str.startswith("🎭") or item_str.startswith("⚠️"):
                c.setFont(thai_font_bold, base_size + 1)
                c.setFillColor(accent_color)
                wrapped = textwrap.wrap(item_str, width=int(content_width / 7))
                for line in wrapped[:2]:
                    c.drawString(1.5*cm, y, line)
                    y -= 0.6*cm
                c.setFillColor(dark_color)
                c.setFont(thai_font, base_size)
                y -= 0.2*cm
            elif item_str.startswith("Q:"):
                c.setFont(thai_font_bold, base_size)
                wrapped = textwrap.wrap(item_str, width=int(content_width / 7))
                for line in wrapped[:2]:
                    c.drawString(1.5*cm, y, line)
                    y -= 0.55*cm
                c.setFont(thai_font, base_size)
            elif item_str.startswith("   "):
                c.setFont(thai_font, base_size - 1)
                c.drawString(2*cm, y, item_str.strip())
                y -= 0.5*cm
                c.setFont(thai_font, base_size)
            elif item_str.startswith("Ex:") or item_str.startswith("  Ex:"):
                c.setFont(thai_font_italic, base_size - 1)
                c.setFillColor(muted_color)
                wrapped = textwrap.wrap(item_str, width=int(content_width / 6.5))
                for line in wrapped[:2]:
                    c.drawString(2*cm, y, line)
                    y -= 0.5*cm
                c.setFillColor(dark_color)
                c.setFont(thai_font, base_size)
            elif ":" in item_str and not item_str.startswith("Keywords"):
                parts = item_str.split(":", 1)
                c.setFont(thai_font_bold, base_size - 1)
                c.drawString(1.5*cm, y, parts[0] + ":")
                c.setFont(thai_font, base_size - 1)
                if len(parts) > 1:
                    wrapped = textwrap.wrap(parts[1].strip(), width=int(content_width / 7))
                    first = True
                    for line in wrapped[:2]:
                        if first:
                            c.drawString(1.5*cm + c.stringWidth(parts[0] + ": ", thai_font_bold, base_size - 1), y, line)
                            first = False
                        else:
                            c.drawString(2*cm, y, line)
                        y -= 0.55*cm
                else:
                    y -= 0.55*cm
                c.setFont(thai_font, base_size)
            else:
                wrapped = textwrap.wrap(item_str, width=int(content_width / 7))
                for line in wrapped[:3]:
                    c.drawString(1.5*cm, y, line)
                    y -= 0.55*cm
                y -= 0.1*cm
        
        # Image
        if image_url and img_x:
            try:
                img_path = None
                
                if image_url.startswith("/uploads/"):
                    img_path = os.path.join(app.config["UPLOAD_FOLDER"], image_url.split("/uploads/")[-1])
                elif image_url.startswith("http"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        urllib.request.urlretrieve(image_url, tmp.name)
                        img_path = tmp.name
                
                if img_path and os.path.exists(img_path):
                    img_max_w = w * 0.38
                    img_max_h = h - 5*cm
                    
                    from reportlab.lib.utils import ImageReader
                    img = ImageReader(img_path)
                    iw, ih = img.getSize()
                    
                    scale = min(img_max_w / iw, img_max_h / ih)
                    draw_w = iw * scale
                    draw_h = ih * scale
                    
                    img_y = (h - 2.5*cm - draw_h) / 2
                    
                    c.drawImage(img_path, img_x, img_y, width=draw_w, height=draw_h, preserveAspectRatio=True)
            except Exception as e:
                print(f"Error loading image: {e}")
        
        # Footer
        c.setFillColor(muted_color)
        c.setFont(thai_font, 10)
        c.drawString(1.5*cm, 0.8*cm, title)
        
        c.showPage()
    
    c.save()
    return buf.getvalue()


# ==============================================================================
# Game
# ==============================================================================
@app.route("/topic/<int:topic_id>/game")
@login_required
def game(topic_id):
    topic = _get_topic_or_404(topic_id)
    last_session = GameSession.get_latest_by_topic_and_user(topic_id, session["user_id"])
    return render_template("game.html", topic=topic, last_session=last_session)

@app.route("/api/game/<int:topic_id>/sets")
@login_required
def api_game_sets(topic_id):
    _get_topic_or_404(topic_id)
    sets_data = {}
    for set_no in range(1, 4):
        questions = GameQuestion.get_by_topic_and_set(topic_id, set_no)
        if questions:
            sets_data[str(set_no)] = [{"id": q["id"], "tile_no": q["tile_no"], "question": q["question"], "answer": q["answer"], "points": q["points"]} for q in questions]
    return jsonify(sets_data)

@app.route("/api/game/<int:topic_id>/sessions", methods=["GET", "POST"])
@login_required
def api_game_sessions(topic_id):
    _get_topic_or_404(topic_id)
    if request.method == "GET":
        return jsonify({"ok": True, "sessions": GameSession.get_by_topic(topic_id)})
    data = request.get_json(silent=True) or {}
    sess = GameSession.create(topic_id, session["user_id"], data.get("title") or "Session", json.dumps(data.get("settings") or {}), json.dumps(data.get("state") or {}))
    return jsonify({"ok": True, "session": sess})

@app.route("/api/game/session/<int:session_id>")
@login_required
def api_game_session_get(session_id):
    sess = GameSession.get_by_id(session_id)
    return jsonify({"ok": True, "session": sess}) if sess else _json_error("Not found", 404)

@app.route("/api/game/session/<int:session_id>/save", methods=["POST"])
@login_required
def api_game_session_save(session_id):
    sess = GameSession.get_by_id(session_id)
    if not sess: return _json_error("Not found", 404)
    data = request.get_json(silent=True) or {}
    GameSession.update(session_id, data.get("title") or sess["title"], json.dumps(data.get("settings") or {}), json.dumps(data.get("state") or {}))
    return jsonify({"ok": True})


# ==============================================================================
# Memory Match Game
# ==============================================================================
@app.route("/topic/<int:topic_id>/game/memory")
@login_required
def game_memory(topic_id):
    topic = _get_topic_or_404(topic_id)
    
    # Get vocabulary from slides
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
        except:
            pass
    
    # Get game questions as fallback
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
@app.route("/topic/<int:topic_id>/game/millionaire")
@login_required
def game_millionaire(topic_id):
    topic = _get_topic_or_404(topic_id)
    
    # Get practice questions (MCQ)
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    
    return render_template("game_millionaire.html", topic=topic, questions=questions)


# ==============================================================================
# Sentence Builder: Helpers & Logic
# ==============================================================================
def _topic_slides_obj(topic):
    """Parse topic['slides_json'] into dict. Always returns dict."""
    try:
        raw = topic.get("slides_json") or ""
        obj = json.loads(raw) if raw else {}
        if isinstance(obj, list):
            # legacy list of slides
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

# ==============================================================================
# Sentence Builder Game
# ==============================================================================

# API: Save custom sentences
@app.route("/api/topic/<int:topic_id>/sentence-builder/custom", methods=["GET", "POST"])
@login_required
def api_sentence_builder_custom(topic_id):
    topic = _get_topic_or_404(topic_id)
    if request.method == "GET":
        return jsonify({"ok": True, "items": _topic_get_sentence_builder_custom(topic)})
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    ok = _topic_save_sentence_builder_custom(topic_id, items)
    return jsonify({"ok": bool(ok), "items": _topic_get_sentence_builder_custom(Topic.get_by_id(topic_id))})

# Main View
@app.route("/topic/<int:topic_id>/game/sentence-builder")
@login_required
def game_sentence_builder(topic_id):
    """Game: เรียงประโยคภาษาอังกฤษจากประโยคภาษาไทย"""
    topic = _get_topic_or_404(topic_id)
    game_data = _get_practice_data_from_slides(topic)
    game_data = _sentence_builder_enrich_game_data_with_th(topic, game_data)
    
    # Get students from classroom if linked
    students = []
    # Try to get students from classroom assignments
    conn = get_db()
    c = conn.cursor()
    # ดึงข้อมูลจาก classroom_students โดยตรง และ join กับ assignments
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


# ==============================================================================
# Practice Helpers
# ==============================================================================
def _normalize_practice_questions(rows):
    out = []
    for r in rows:
        q = dict(r)
        prompt, choices = "", []
        raw = q.get("question") or ""
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                prompt = (obj.get("prompt") or "").strip()
                choices = [str(x) for x in (obj.get("choices") or [])]
            else: prompt = str(obj)
        except: prompt = str(raw)
        out.append({"id": q.get("id"), "prompt": prompt, "choices": choices, "correct_answer": q.get("correct_answer") or ""})
    return out

def _build_practice_pdf(topic_title, questions, include_answers=False):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    mx, y, lh, mw = 2*cm, h-2*cm, 14, w-4*cm
    def draw(lines, y0):
        y = y0
        for ln in lines:
            if y < 2*cm: c.showPage(); y = h-2*cm
            c.drawString(mx, y, ln); y -= lh
        return y
    c.setFont("Helvetica-Bold", 16)
    y = draw([f"Practice: {topic_title}"], y)
    c.setFont("Helvetica", 11)
    y = draw(["Name: ________________________   Class: __________", ""], y)
    for i, q in enumerate(questions, 1):
        c.setFont("Helvetica-Bold", 12)
        y = draw(simpleSplit(f"{i}. {q.get('prompt','')}", "Helvetica-Bold", 12, mw), y)
        c.setFont("Helvetica", 11)
        ch = q.get("choices") or []
        if len(ch) == 4:
            for lab, cv in zip(["A","B","C","D"], ch):
                y = draw(simpleSplit(f"   ({lab}) {cv}", "Helvetica", 11, mw), y)
        if include_answers: y = draw([f"   Answer: {q.get('correct_answer','')}"], y)
        y = draw([""], y)
    c.showPage(); c.save()
    return buf.getvalue()


# ==============================================================================
# Practice
# ==============================================================================
@app.route("/topic/<int:topic_id>/practice")
@login_required
def practice(topic_id):
    topic = _get_topic_or_404(topic_id)
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    student_url = (request.url_root.rstrip("/") + url_for("public_practice", token=link["token"])) if link else None
    return render_template("practice.html", topic=topic, questions=questions, student_url=student_url)


def _get_practice_data_from_slides(topic):
    """Extract vocabulary, examples, dialogues from slides for practice activities"""
    data = {"vocabulary": [], "examples": [], "dialogues": [], "questions": [], "mcq_questions": []}
    
    # From slides
    if topic.get("slides_json"):
        try:
            obj = json.loads(topic["slides_json"])
            slides = obj.get("slides", obj) if isinstance(obj, dict) else obj
            for slide in slides:
                slide_type = slide.get("type", "")
                
                # Vocabulary
                if slide_type == "vocabulary" and slide.get("vocabulary"):
                    for v in slide["vocabulary"]:
                        if v.get("word") and v.get("meaning"):
                            data["vocabulary"].append({
                                "word": v["word"],
                                "meaning": v["meaning"],
                                "example": v.get("example", "")
                            })
                
                # Examples
                if slide.get("examples"):
                    for ex in slide["examples"]:
                        if isinstance(ex, dict) and ex.get("en"):
                            data["examples"].append({"en": ex["en"], "th": ex.get("th", "")})
                        elif isinstance(ex, str):
                            data["examples"].append({"en": ex, "th": ""})
                
                # Dialogues
                if slide_type == "dialogue" and slide.get("lines"):
                    for line in slide["lines"]:
                        if isinstance(line, dict) and line.get("text"):
                            data["dialogues"].append({"speaker": line.get("speaker", ""), "text": line["text"]})
        except:
            pass
    
    # From game questions
    for set_no in range(1, 4):
        qs = GameQuestion.get_by_topic_and_set(topic["id"], set_no)
        for q in qs:
            data["questions"].append({"question": q["question"], "answer": q["answer"]})
    
    # From MCQ practice questions
    mcq_rows = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic["id"]))
    data["mcq_questions"] = mcq_rows
    
    return data


# ------------------------------------------------------------------------------
# Sentence Builder helpers (Auto-generate Thai translations from slides if missing)
# ------------------------------------------------------------------------------
def _extract_first_json_array(s: str):
    """Best-effort: extract first JSON array from a string."""
    if not s:
        return None
    s = s.strip()
    # already json
    if s.startswith('[') and s.endswith(']'):
        try:
            return json.loads(s)
        except Exception:
            pass
    # find first [...]
    start = s.find('[')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                chunk = s[start:i+1]
                try:
                    return json.loads(chunk)
                except Exception:
                    return None
    return None

def _ai_translate_en_to_th(sentences, model="gpt-4o-mini"):
    """Translate a list of short English sentences to Thai (returns list of dicts: {en, th})."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_APIKEY") or os.environ.get("OPENAI_KEY")
    if not api_key:
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception:
        return []

    # Keep it strict JSON to parse reliably
    sys = (
        "You translate English teaching examples into natural Thai. "
        "Return ONLY valid JSON array. No markdown. No extra text."
    )
    user = {
        "task": "translate_en_to_th",
        "rules": [
            "Keep meaning faithful and natural for Thai students.",
            "Do not add explanations.",
            "Do not number items.",
            "Return format: [{\"en\":...,\"th\":...}, ...] in same order."
        ],
        "sentences": sentences[:40]  # safety cap
    }
    try:
        # Compatible with OpenAI Python SDK 1.x
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
            ],
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception:
        # Fallback: newer responses API if present
        try:
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
                ],
                temperature=0.2,
            )
            content = (resp.output_text or "").strip()
        except Exception:
            return []

    arr = _extract_first_json_array(content)
    if not isinstance(arr, list):
        return []
    out = []
    for it in arr:
        if isinstance(it, dict) and it.get("en") and it.get("th"):
            out.append({"en": str(it["en"]).strip(), "th": str(it["th"]).strip()})
    return out

def _sentence_builder_enrich_game_data_with_th(topic, game_data):
    """Ensure examples contain Thai prompts for Sentence Builder."""
    if not game_data:
        return game_data

    examples = (game_data.get("examples") or [])
    if not isinstance(examples, list) or not examples:
        return game_data

    # Collect EN sentences that are missing Thai (or Thai is not actually Thai characters)
    need_en = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        en = (ex.get("en") or "").strip()
        th = (ex.get("th") or "").strip()
        has_thai = bool(th and re.search(r"[ก-๙]", th))
        if en and not has_thai:
            if en not in need_en:
                need_en.append(en)

    # Nothing to translate
    if not need_en:
        return game_data

    translated = _ai_translate_en_to_th(need_en)
    if not translated:
        return game_data

    mapping = {str(t.get("en") or "").strip(): str(t.get("th") or "").strip()
               for t in translated if isinstance(t, dict)}

    new_examples = []
    for ex in examples:
        if isinstance(ex, dict) and ex.get("en"):
            en = str(ex.get("en") or "").strip()
            th = str(ex.get("th") or "").strip()
            has_thai = bool(th and re.search(r"[ก-๙]", th))
            if (not has_thai) and en in mapping and mapping[en]:
                th = mapping[en]
            new_examples.append({"en": en, "th": th})
        else:
            new_examples.append(ex)

    game_data["examples"] = new_examples
    return game_data


@app.route("/topic/<int:topic_id>/practice/fill-blanks")
@login_required
def practice_fill_blanks(topic_id):
    topic = _get_topic_or_404(topic_id)
    practice_data = _get_practice_data_from_slides(topic)
    link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    student_url = None
    if link:
        student_url = request.url_root.rstrip("/") + url_for("public_fill_blanks", token=link["token"])
    return render_template("practice_fill_blanks.html", topic=topic, practice_data=practice_data, student_url=student_url)


@app.route("/api/practice/<int:topic_id>/fill-blanks/link", methods=["POST"])
@login_required
def api_fill_blanks_create_link(topic_id):
    _get_topic_or_404(topic_id)
    old = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    if not old:
        link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    else:
        link = old
    return jsonify({"url": request.url_root.rstrip("/") + url_for("public_fill_blanks", token=link["token"])})


@app.route("/topic/<int:topic_id>/practice/fill-blanks/scores")
@login_required
def practice_fill_blanks_scores(topic_id):
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.id DESC LIMIT 500", (topic_id,))
    submissions = [dict(r) for r in c.fetchall()]
    conn.close()
    return render_template("practice_scores.html", topic=topic, submissions=submissions, practice_type="Fill in the Blanks")


@app.route("/p/fill/<token>")
def public_fill_blanks(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link["is_active"]:
        return "ลิงก์ไม่ถูกต้องหรือหมดอายุ", 404
    topic = Topic.get_by_id(link["topic_id"])
    if not topic:
        return "Topic not found", 404
    practice_data = _get_practice_data_from_slides(topic)
    return render_template("practice_fill_blanks_public.html", topic=topic, practice_data=practice_data, token=token)


@app.route("/api/public/fill/<token>/submit", methods=["POST"])
def api_public_fill_blanks_submit(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link["is_active"]:
        return _json_error("Invalid link", 404)
    data = request.get_json() or {}
    student_name = (data.get("student_name") or data.get("name") or "Anonymous").strip()[:100]
    student_no = (data.get("student_no") or "").strip()[:20]
    classroom = (data.get("classroom") or "").strip()[:30]
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    pct = (score/total*100) if total else 0
    PracticeSubmission.create(link["id"], student_name, student_no, classroom, json.dumps(data.get("answers", {})), score, total, pct)
    return jsonify({"ok": True, "score": score, "total": total, "percentage": pct})


@app.route("/topic/<int:topic_id>/practice/unscramble")
@login_required
def practice_unscramble(topic_id):
    topic = _get_topic_or_404(topic_id)
    practice_data = _get_practice_data_from_slides(topic)
    link = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    student_url = None
    if link:
        student_url = request.url_root.rstrip("/") + url_for("public_unscramble", token=link["token"])
    return render_template("practice_unscramble.html", topic=topic, practice_data=practice_data, student_url=student_url)


@app.route("/api/practice/<int:topic_id>/unscramble/link", methods=["POST"])
@login_required
def api_unscramble_create_link(topic_id):
    _get_topic_or_404(topic_id)
    old = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    if not old:
        link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    else:
        link = old
    return jsonify({"url": request.url_root.rstrip("/") + url_for("public_unscramble", token=link["token"])})


@app.route("/topic/<int:topic_id>/practice/unscramble/scores")
@login_required
def practice_unscramble_scores(topic_id):
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.id DESC LIMIT 500", (topic_id,))
    submissions = [dict(r) for r in c.fetchall()]
    conn.close()
    return render_template("practice_scores.html", topic=topic, submissions=submissions, practice_type="Sentence Unscramble")


@app.route("/p/unscramble/<token>")
def public_unscramble(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link["is_active"]:
        return "ลิงก์ไม่ถูกต้องหรือหมดอายุ", 404
    topic = Topic.get_by_id(link["topic_id"])
    if not topic:
        return "Topic not found", 404
    practice_data = _get_practice_data_from_slides(topic)
    return render_template("practice_unscramble_public.html", topic=topic, practice_data=practice_data, token=token)


@app.route("/api/public/unscramble/<token>/submit", methods=["POST"])
def api_public_unscramble_submit(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link["is_active"]:
        return _json_error("Invalid link", 404)
    data = request.get_json() or {}
    student_name = (data.get("student_name") or data.get("name") or "Anonymous").strip()[:100]
    student_no = (data.get("student_no") or "").strip()[:20]
    classroom = (data.get("classroom") or "").strip()[:30]
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    pct = (score/total*100) if total else 0
    PracticeSubmission.create(link["id"], student_name, student_no, classroom, json.dumps(data.get("answers", {})), score, total, pct)
    return jsonify({"ok": True, "score": score, "total": total, "percentage": pct})

@app.route("/api/practice/<int:topic_id>/submit", methods=["POST"])
@login_required
def api_practice_submit(topic_id):
    _get_topic_or_404(topic_id)
    data = request.get_json() or {}
    answers = data.get("answers", {})
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id))
    score, total, feedback = 0, len(questions), {}
    for q in questions:
        qid = str(q["id"])
        ua = (answers.get(qid, "") or "").strip().lower()
        ca = (q.get("correct_answer") or "").strip().lower()
        correct = ua == ca
        if correct: score += 1
        feedback[qid] = {"is_correct": correct, "user_answer": answers.get(qid, ""), "correct_answer": q.get("correct_answer")}
    pct = (score/total*100) if total else 0
    AttemptHistory.create(session["user_id"], topic_id, score, total, pct)
    return jsonify({"score": score, "total": total, "percentage": pct, "feedback": feedback})

@app.route("/api/practice/<int:topic_id>/link", methods=["POST"])
@login_required
def api_practice_create_link(topic_id):
    _get_topic_or_404(topic_id)
    old = PracticeLink.get_latest_active_by_topic_and_user(topic_id, session["user_id"])
    if old: PracticeLink.deactivate(old["id"])
    link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    return jsonify({"url": request.url_root.rstrip("/") + url_for("public_practice", token=link["token"])})

@app.route("/topic/<int:topic_id>/practice/pdf")
@login_required
def practice_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)
    include_answers = request.args.get("answers") == "1"
    pdf = _build_practice_pdf(topic["name"], _normalize_practice_questions(PracticeQuestion.get_by_topic(topic_id)), include_answers)
    return (pdf, 200, {"Content-Type": "application/pdf", "Content-Disposition": f"attachment; filename=practice_{topic_id}.pdf"})

@app.route("/topic/<int:topic_id>/practice/scores")
@login_required
def practice_scores(topic_id):
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.id DESC LIMIT 1000", (topic_id,))
    submissions = [dict(r) for r in c.fetchall()]
    conn.close()
    classrooms = sorted(set(s.get("classroom") or "" for s in submissions if s.get("classroom")))
    return render_template("practice_scores.html", topic=topic, submissions=submissions, classrooms=classrooms)

@app.route("/topic/<int:topic_id>/practice/scores/csv")
@login_required
def practice_scores_csv(topic_id):
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.classroom,ps.student_no", (topic_id,))
    rows = c.fetchall()
    conn.close()
    out = StringIO()
    w = csv.writer(out)
    w.writerow(["#", "Name", "No", "Class", "Score", "Total", "%", "Time"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["student_name"], r["student_no"] or "", r["classroom"] or "", r["score"], r["total"], f"{r['percentage']:.0f}%", r["created_at"]])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=scores_{topic_id}.csv"})

@app.route("/topic/<int:topic_id>/practice/scores/excel")
@login_required
def practice_scores_excel(topic_id):
    topic = _get_topic_or_404(topic_id)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    except: return redirect(url_for("practice_scores_csv", topic_id=topic_id))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ps.* FROM practice_submissions ps JOIN practice_links pl ON ps.link_id=pl.id WHERE pl.topic_id=? ORDER BY ps.classroom,ps.student_no", (topic_id,))
    rows = c.fetchall()
    conn.close()
    wb = Workbook()
    ws = wb.active
    ws.title = "Scores"
    hf, hfill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="667eea")
    bd = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
    ws.merge_cells('A1:H1')
    ws['A1'] = f"Practice Scores: {topic['name']}"
    ws['A1'].font = Font(bold=True, size=14)
    for col, h in enumerate(["#", "Name", "No", "Class", "Score", "Total", "%", "Time"], 1):
        cell = ws.cell(3, col, h)
        cell.font, cell.fill, cell.border = hf, hfill, bd
    for i, r in enumerate(rows, 1):
        for col, v in enumerate([i, r["student_name"], r["student_no"] or "", r["classroom"] or "", r["score"], r["total"], f"{r['percentage']:.0f}%", str(r["created_at"])[:19]], 1):
            cell = ws.cell(i+3, col, v)
            cell.border = bd
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=scores_{topic_id}.xlsx"})


@app.route("/topic/<int:topic_id>/practice/all-scores")
@login_required
def practice_all_scores(topic_id):
    """ดูคะแนนรวมทุกแบบฝึกหัด (MCQ, Fill Blanks, Unscramble)"""
    topic = _get_topic_or_404(topic_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT ps.*, pl.token FROM practice_submissions ps 
        JOIN practice_links pl ON ps.link_id=pl.id 
        WHERE pl.topic_id=? 
        ORDER BY ps.id DESC LIMIT 1000
    """, (topic_id,))
    rows = c.fetchall()
    conn.close()
    
    # Add practice_type based on the link token/url pattern
    all_submissions = []
    for r in rows:
        s = dict(r)
        # Determine type - we'll mark based on submission data
        # For now, default to 'mcq', you can enhance this with a practice_type column
        s['practice_type'] = 'mcq'  # default
        all_submissions.append(s)
    
    classrooms = sorted(set(s.get("classroom") or "" for s in all_submissions if s.get("classroom")))
    return render_template("practice_all_scores.html", topic=topic, all_submissions=all_submissions, classrooms=classrooms)


@app.route("/topic/<int:topic_id>/practice/all-scores/excel")
@login_required
def practice_all_scores_excel(topic_id):
    """Export คะแนนรวมทุกแบบฝึกหัดเป็น Excel"""
    topic = _get_topic_or_404(topic_id)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side
    except:
        return redirect(url_for("practice_scores_csv", topic_id=topic_id))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT ps.* FROM practice_submissions ps 
        JOIN practice_links pl ON ps.link_id=pl.id 
        WHERE pl.topic_id=? 
        ORDER BY ps.classroom, ps.student_no
    """, (topic_id,))
    rows = c.fetchall()
    conn.close()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "All Scores"
    hf = Font(bold=True, color="FFFFFF")
    hfill = PatternFill("solid", fgColor="667eea")
    bd = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
    
    ws.merge_cells('A1:H1')
    ws['A1'] = f"Practice Scores (All Types): {topic['name']}"
    ws['A1'].font = Font(bold=True, size=14)
    
    headers = ["#", "Name", "No", "Class", "Score", "Total", "%", "Time"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(3, col, h)
        cell.font, cell.fill, cell.border = hf, hfill, bd
    
    for i, r in enumerate(rows, 1):
        for col, v in enumerate([i, r["student_name"], r["student_no"] or "", r["classroom"] or "", r["score"], r["total"], f"{r['percentage']:.0f}%", str(r["created_at"])[:19]], 1):
            cell = ws.cell(i+3, col, v)
            cell.border = bd
    
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=all_scores_{topic_id}.xlsx"})


# ==============================================================================
# Public Practice
# ==============================================================================
@app.route("/p/<token>")
def public_practice(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link.get("is_active"): return render_template("error.html", error_code=404, error_msg="ลิงก์หมดอายุ"), 404
    topic = Topic.get_by_id(link["topic_id"])
    if not topic: return render_template("error.html", error_code=404, error_msg="Topic not found"), 404
    return render_template("practice_public.html", topic=topic, questions=_normalize_practice_questions(PracticeQuestion.get_by_topic(topic["id"])), token=token)

@app.route("/api/p/<token>/submit", methods=["POST"])
def api_public_practice_submit(token):
    link = PracticeLink.get_by_token(token)
    if not link or not link.get("is_active"): return jsonify({"error": "Invalid link"}), 404
    data = request.get_json() or {}
    name = (data.get("student_name") or "").strip()
    if not name: return jsonify({"error": "Name required"}), 400
    questions = _normalize_practice_questions(PracticeQuestion.get_by_topic(link["topic_id"]))
    answers = data.get("answers", {})
    score, total, feedback = 0, len(questions), {}
    for q in questions:
        qid = str(q["id"])
        ua = (answers.get(qid, "") or "").strip().lower()
        ca = (q.get("correct_answer") or "").strip().lower()
        correct = ua == ca
        if correct: score += 1
        feedback[qid] = {"is_correct": correct, "user_answer": answers.get(qid, ""), "correct_answer": q.get("correct_answer")}
    pct = (score/total*100) if total else 0
    PracticeSubmission.create(link["id"], name, data.get("student_no") or "", data.get("classroom") or "", json.dumps({"answers": answers}), score, total, pct)
    return jsonify({"score": score, "total": total, "percentage": pct, "feedback": feedback})


# ==============================================================================
# Classrooms
# ==============================================================================
@app.route("/classrooms")
@login_required
def classrooms():
    user_id = session["user_id"]
    cls_list = Classroom.get_by_owner(user_id)
    total_students = sum(c.get("student_count") or 0 for c in cls_list)
    assignments = Assignment.get_by_owner(user_id)
    # Add assignment count to each classroom
    for c in cls_list:
        c["assignment_count"] = len([a for a in assignments if a["classroom_id"] == c["id"]])
    return render_template("classrooms.html", classrooms=cls_list, total_students=total_students, total_assignments=len(assignments))

@app.route("/classrooms/create", methods=["POST"])
@login_required
def classroom_create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("กรุณาระบุชื่อห้อง", "error")
        return redirect(url_for("classrooms"))
    Classroom.create(session["user_id"], name, request.form.get("grade_level") or "", request.form.get("academic_year") or "", request.form.get("description") or "")
    flash("สร้างห้องเรียนแล้ว", "success")
    return redirect(url_for("classrooms"))

@app.route("/classroom/<int:classroom_id>")
@login_required
def classroom_detail(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    students = ClassroomStudent.get_by_classroom(classroom_id)
    assignments = Assignment.get_by_classroom(classroom_id)
    topics = Topic.get_by_owner(session["user_id"])
    
    # Get submission stats and scores for each assignment
    submission_stats = {}
    assignment_stats = {}
    scores_by_student = {s["id"]: {"assignments": {}, "total_score": 0, "total_possible": 0} for s in students}
    
    for a in assignments:
        status = Assignment.get_submissions_status(a["id"])
        submission_stats[a["id"]] = {"submitted": len(status["submitted"]), "not_submitted": len(status["not_submitted"])}
        
        # Calculate assignment average
        submissions = status.get("submissions") or []
        if submissions:
            avg = sum(s.get("percentage") or 0 for s in submissions) / len(submissions)
            assignment_stats[a["id"]] = {"avg": avg, "count": len(submissions)}
        else:
            assignment_stats[a["id"]] = {"avg": 0, "count": 0}
        
        # Map submissions to students
        for student in students:
            student_id = student["id"]
            student_name_lower = (student.get("student_name") or "").strip().lower()
            student_no = (student.get("student_no") or "").strip()
            
            # Find matching submission
            for sub in submissions:
                sub_name = (sub.get("student_name") or "").strip().lower()
                sub_no = (sub.get("student_no") or "").strip()
                if sub_name == student_name_lower or (sub_no and sub_no == student_no):
                    scores_by_student[student_id]["assignments"][a["id"]] = {
                        "score": sub.get("score", 0),
                        "total": sub.get("total", 0),
                        "percentage": sub.get("percentage", 0)
                    }
                    scores_by_student[student_id]["total_score"] += sub.get("score", 0)
                    scores_by_student[student_id]["total_possible"] += sub.get("total", 0)
                    break
    
    # Calculate class average
    class_avg = 0
    students_with_scores = [s for s in scores_by_student.values() if s["total_possible"] > 0]
    if students_with_scores:
        class_avg = sum((s["total_score"] / s["total_possible"] * 100) for s in students_with_scores) / len(students_with_scores)
    
    return render_template("classroom_detail.html", classroom=cls, students=students, assignments=assignments, topics=topics, submission_stats=submission_stats, scores_by_student=scores_by_student, assignment_stats=assignment_stats, class_avg=class_avg)

@app.route("/classroom/<int:classroom_id>/edit", methods=["POST"])
@login_required
def classroom_edit(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    Classroom.update(classroom_id, request.form.get("name") or cls["name"], request.form.get("grade_level") or "", request.form.get("academic_year") or "", request.form.get("description") or "")
    flash("บันทึกแล้ว", "success")
    return redirect(url_for("classrooms"))

@app.route("/classroom/<int:classroom_id>/delete", methods=["POST"])
@login_required
def classroom_delete(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    Classroom.delete(classroom_id)
    flash("ลบห้องเรียนแล้ว", "success")
    return redirect(url_for("classrooms"))

@app.route("/classroom/<int:classroom_id>/add-student", methods=["POST"])
@login_required
def classroom_add_student(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    name = (request.form.get("student_name") or "").strip()
    if name:
        ClassroomStudent.create(classroom_id, request.form.get("student_no") or "", name, request.form.get("nickname") or "")
        flash("เพิ่มนักเรียนแล้ว", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

@app.route("/classroom/<int:classroom_id>/import-students", methods=["POST"])
@login_required
def classroom_import_students(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    text = request.form.get("student_list") or ""
    students = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        parts = line.split("\t")
        if len(parts) >= 2:
            students.append({"student_no": parts[0].strip(), "student_name": parts[1].strip()})
        else:
            students.append({"student_no": "", "student_name": parts[0].strip()})
    count = ClassroomStudent.bulk_create(classroom_id, students)
    flash(f"Import {count} คนเรียบร้อย", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

@app.route("/classroom/student/<int:student_id>/edit", methods=["POST"])
@login_required
def classroom_student_edit(student_id):
    s = ClassroomStudent.get_by_id(student_id)
    if not s: abort(404)
    cls = Classroom.get_by_id(s["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    ClassroomStudent.update(student_id, request.form.get("student_no") or "", request.form.get("student_name") or s["student_name"], request.form.get("nickname") or "")
    return redirect(url_for("classroom_detail", classroom_id=s["classroom_id"]))

@app.route("/classroom/student/<int:student_id>/delete", methods=["POST"])
@login_required
def classroom_student_delete(student_id):
    s = ClassroomStudent.get_by_id(student_id)
    if not s: abort(404)
    cls = Classroom.get_by_id(s["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    classroom_id = s["classroom_id"]
    ClassroomStudent.delete(student_id)
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

@app.route("/classroom/<int:classroom_id>/assign", methods=["POST"])
@login_required
def classroom_assign(classroom_id):
    cls = Classroom.get_by_id(classroom_id)
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    topic_id = int(request.form.get("topic_id") or 0)
    if not topic_id:
        flash("กรุณาเลือก Topic", "error")
        return redirect(url_for("classroom_detail", classroom_id=classroom_id))
    topic = Topic.get_by_id(topic_id)
    if not topic: abort(404)
    # Create practice link
    link = PracticeLink.create(topic_id, session["user_id"], secrets.token_urlsafe(12))
    title = (request.form.get("title") or "").strip() or topic["name"]
    due_date = request.form.get("due_date") or None
    Assignment.create(classroom_id, topic_id, link["id"], title, request.form.get("description") or "", due_date, session["user_id"])
    flash("สั่งงานเรียบร้อย", "success")
    return redirect(url_for("classroom_detail", classroom_id=classroom_id))

@app.route("/assignment/<int:assignment_id>")
@login_required
def assignment_detail(assignment_id):
    a = Assignment.get_by_id(assignment_id)
    if not a: abort(404)
    cls = Classroom.get_by_id(a["classroom_id"])
    if not cls or cls["owner_id"] != session["user_id"]: abort(404)
    topic = Topic.get_by_id(a["topic_id"])
    status = Assignment.get_submissions_status(assignment_id)
    practice_link = PracticeLink.get_by_id(a.get("practice_link_id")) if a.get("practice_link_id") else None
    student_url = (request.url_root.rstrip("/") + url_for("public_practice", token=practice_link["token"])) if practice_link else None
    # Calculate average score
    avg = 0
    submissions = status.get("submissions") or []
    if submissions:
        avg = sum(s.get("percentage") or 0 for s in submissions) / len(submissions)
    return render_template("assignment_detail.html", assignment=a, classroom=cls, topic=topic, submitted=status["submitted"], not_submitted=status["not_submitted"], total_students=status["total"], submitted_count=len(status["submitted"]), not_submitted_count=len(status["not_submitted"]), avg_score=avg, practice_link=practice_link, student_url=student_url)


# ==============================================================================
# AI & Generate
# ==============================================================================
@app.route("/ai-slides", methods=["GET", "POST"])
@login_required
def ai_slides():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Topic title required.", "error")
            return render_template("ai_slides_form.html")
        bundle = generate_lesson_bundle(title=title, level=request.form.get("level", "Secondary"), language=request.form.get("language", "EN"), style=request.form.get("style", "Minimal"), text_model="gpt-4o-mini")
        slides = bundle.get("slides", []) or []
        topic = Topic.create(session["user_id"], title, f"AI generated", json.dumps({"slides": slides}, ensure_ascii=False), "ai", None)
        _save_game_and_practice(topic["id"], bundle.get("game") or {}, bundle.get("practice") or [])
        return redirect(url_for("topic_detail", topic_id=topic["id"]))
    return render_template("ai_slides_form.html")

def _extract_text_from_pdf(path):
    from pypdf import PdfReader
    return "\n\n".join(p.extract_text() or "" for p in PdfReader(path).pages).strip()

def _save_game_only(topic_id, game):
    GameQuestion.delete_by_topic(topic_id)
    for set_no in [1, 2, 3]:
        for tile_no, it in enumerate((game.get(str(set_no)) or [])[:24], 1):
            q, a = (it.get("question") or "").strip(), (it.get("answer") or "").strip()
            if q and a: GameQuestion.create(topic_id, set_no, tile_no, q, a, int(it.get("points") or 10))

def _save_practice_only(topic_id, practice):
    PracticeQuestion.delete_by_topic(topic_id)
    for it in (practice or []):
        prompt, choices = (it.get("question") or "").strip(), it.get("choices") or []
        if not prompt or len(choices) != 4: continue
        ci = max(0, min(int(it.get("correct_index") or 0), 3))
        PracticeQuestion.create(topic_id, "multiple_choice", json.dumps({"prompt": prompt, "choices": choices}), str(choices[ci]).strip())

def _save_slides_only(topic_id, slides):
    """Save generated slides to topic.slides_json"""
    topic = Topic.get_by_id(topic_id)
    if not topic:
        return
    slides_json = json.dumps({"slides": slides or []}, ensure_ascii=False)
    Topic.update(topic_id, topic["name"], topic.get("description") or "", slides_json, topic.get("pdf_file"))

def _save_game_and_practice(topic_id, game, practice):
    _save_game_only(topic_id, game)
    _save_practice_only(topic_id, practice)

def _save_all(topic_id, slides, game, practice):
    """Save slides, game, and practice all at once"""
    _save_slides_only(topic_id, slides)
    _save_game_only(topic_id, game)
    _save_practice_only(topic_id, practice)

@app.route("/api/topic/<int:topic_id>/generate", methods=["POST"])
@login_required
def api_generate_from_pdf(topic_id):
    topic = _get_topic_or_404(topic_id)
    if not topic.get("pdf_file"): return _json_error("No PDF", 400)
    mode = ((request.get_json(silent=True) or {}).get("mode") or "all").lower()
    path = os.path.join(app.config["UPLOAD_FOLDER"], topic["pdf_file"])
    if not os.path.exists(path): return _json_error("PDF not found", 404)
    try: text = _extract_text_from_pdf(path)
    except Exception as e: return _json_error(str(e), 400)
    try: bundle = generate_lesson_bundle(f"{topic['name']}\n\n[PDF]\n{text[:8000]}", "Secondary", "EN", "Minimal", "gpt-4o-mini")
    except Exception as e: return _json_error(str(e), 500)
    
    # Save based on mode
    if mode == "slides":
        _save_slides_only(topic_id, bundle.get("slides") or [])
    elif mode == "game":
        _save_game_only(topic_id, bundle.get("game") or {})
    elif mode == "practice":
        _save_practice_only(topic_id, bundle.get("practice") or [])
    else:  # mode == "all"
        _save_all(topic_id, bundle.get("slides") or [], bundle.get("game") or {}, bundle.get("practice") or [])
    
    return jsonify({"ok": True})


# ==============================================================================
# Admin
# ==============================================================================
@app.route("/admin")
@admin_required
def admin_dashboard(): return render_template("admin_dashboard.html", topics=Topic.get_all())

@app.route("/admin/topics/create", methods=["GET", "POST"])
@admin_required
def admin_create_topic():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name: flash("Name required.", "error"); return render_template("admin_create_topic.html")
        topic = Topic.create(session["user_id"], name, request.form.get("description") or "", json.dumps({"slides": []}), "manual", None)
        return redirect(url_for("admin_edit_topic", topic_id=topic["id"]))
    return render_template("admin_create_topic.html")

@app.route("/admin/topics/<int:topic_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_topic(topic_id):
    topic = Topic.get_by_id(topic_id)
    if not topic: return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slides_json = request.form.get("slides_json") or ""
        try: json.loads(slides_json)
        except: flash("Invalid JSON.", "error"); return render_template("admin_edit_topic.html", topic=topic)
        pdf_filename = topic.get("pdf_file")
        file = request.files.get("pdf_file")
        if file and file.filename and allowed_file(file.filename):
            fn = f"topic{topic_id}_{secrets.token_hex(6)}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
            pdf_filename = fn
        Topic.update(topic_id, name, request.form.get("description") or "", slides_json, pdf_filename)
        flash("Saved.", "success")
    return render_template("admin_edit_topic.html", topic=Topic.get_by_id(topic_id))

@app.route("/admin/topics/<int:topic_id>/delete", methods=["POST"])
@admin_required
def admin_delete_topic(topic_id):
    Topic.delete(topic_id)
    return redirect(url_for("admin_dashboard"))


# ==============================================================================
# Errors
# ==============================================================================
@app.errorhandler(403)
def forbidden(e): return (jsonify({"ok": False, "error": "Forbidden"}), 403) if _wants_json_response() else (render_template("error.html", error_code=403, error_msg="ไม่มีสิทธิ์"), 403)
@app.errorhandler(404)
def not_found(e): return (jsonify({"ok": False, "error": "Not found"}), 404) if _wants_json_response() else (render_template("error.html", error_code=404, error_msg="ไม่พบหน้านี้"), 404)
@app.errorhandler(500)
def server_error(e): return (jsonify({"ok": False, "error": "Server error"}), 500) if _wants_json_response() else (render_template("error.html", error_code=500, error_msg="เกิดข้อผิดพลาด"), 500)

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") == "development", host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
