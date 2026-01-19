# ==============================================================================
# FILE: ai_generator.py
# Generate lesson bundle as JSON (stable, classroom-friendly patterns)
# - slides: 18–24 slides (enough for ~60–90 minutes)
# - game: 3 sets x 24 tiles
# - practice: 20–30 MCQ (4 choices)
#
# IMPORTANT
# - Uses OpenAI Responses API with json_object output
# - Normalizes/repairs output so the web app never breaks
# ==============================================================================

import os
import json
from typing import Any, Dict, Optional, List

from openai import OpenAI


# -----------------------------
# Slide helpers
# -----------------------------

ALLOWED_SLIDE_TYPES = {
    "hook",
    "objectives",
    "context",
    "vocabulary",
    "concept",
    "pronunciation",
    "examples",
    "guided_practice",
    "dialogue",
    "production",
    "exit_ticket",
    "review",
}


def _extract_first_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _safe_json_loads(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        maybe = _extract_first_json_object(text)
        if maybe:
            return json.loads(maybe)
        raise


def _clamp_int(x: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(x)
    except Exception:
        v = default
    return max(lo, min(hi, v))


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _pick(d: Dict[str, Any], keys: List[str], default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _ensure_slide_has_content(slide: Dict[str, Any]) -> Dict[str, Any]:
    """Make sure each slide has something to render (content/examples/items/etc.)."""
    t = (slide.get("type") or "slide").strip()

    # If unknown type, downgrade to "context" with content.
    if t not in ALLOWED_SLIDE_TYPES:
        slide["type"] = "context"
        t = "context"

    # Provide minimal defaults per type
    if t == "hook":
        slide.setdefault("prompt", "Warm-up: What would you say in this situation?")
        slide.setdefault("keywords", ["real life", "simple", "useful"])

    elif t == "objectives":
        objs = _as_list(slide.get("objectives"))
        if len(objs) < 2:
            slide["objectives"] = objs + ["Understand the key idea", "Use it in speaking"]
            slide["objectives"] = slide["objectives"][:3]

    elif t == "context":
        c = slide.get("content")
        if not c:
            slide["content"] = [
                "Where do we use this in real life?",
                "Who are you talking to?",
                "What do you want to achieve?",
            ]

    elif t == "vocabulary":
        # Support both keys:
        # - "vocabulary": [{word, meaning, example, ...}]
        # - "items": [{word, meaning, example_en/example_th, ...}]  (legacy)
        vocab = _as_list(slide.get("vocabulary"))
        items = _as_list(slide.get("items"))
        if not vocab and items:
            slide["vocabulary"] = items
            vocab = _as_list(slide.get("vocabulary"))

        if not vocab:
            slide["vocabulary"] = [
                {
                    "word": "example",
                    "meaning": "ตัวอย่าง / an example",
                    "example": "This is an example.",
                }
            ]

    elif t == "concept":
        if not (slide.get("pattern") or slide.get("structure") or slide.get("content")):
            slide["pattern"] = "Structure / Pattern here"
        hl = _as_list(slide.get("highlights"))
        if len(hl) < 2:
            slide["highlights"] = [
                {"label": "Key part", "note": "What it means"},
                {"label": "Example", "note": "How to use"},
            ]
        cm = _as_list(slide.get("common_mistakes"))
        if len(cm) < 1:
            slide["common_mistakes"] = ["Common mistake example"]

    elif t == "pronunciation":
        # Keep it simple: lists + examples
        if not slide.get("content"):
            slide["content"] = [
                "Say the ending clearly.",
                "Practice slowly → natural speed.",
            ]
        if not slide.get("examples"):
            slide["examples"] = [
                {"en": "worked /wɜːrkt/", "th": "ลงท้ายเสียง /t/"},
                {"en": "wanted /ˈwɒntɪd/", "th": "ลงท้ายเสียง /ɪd/"},
            ]

    elif t == "examples":
        ex = _as_list(slide.get("examples"))
        if not ex:
            slide["examples"] = [
                {"en": "Example sentence 1", "th": "ตัวอย่าง 1"},
                {"en": "Example sentence 2", "th": "ตัวอย่าง 2"},
            ]

    elif t == "guided_practice":
        items = _as_list(slide.get("items"))
        if not items:
            slide["items"] = [
                {
                    "q": "Choose the best answer.",
                    "choices": ["A", "B", "C", "D"],
                    "answer": "A",
                }
            ]

    elif t == "dialogue":
        if not slide.get("scenario"):
            slide["scenario"] = "Role-play scenario"
        lines = _as_list(slide.get("lines"))
        if len(lines) < 6:
            slide["lines"] = (
                lines
                + [
                    {"speaker": "A", "text": "Hello."},
                    {"speaker": "B", "text": "Hi."},
                    {"speaker": "A", "text": "How can I help you?"},
                    {"speaker": "B", "text": "I’d like …"},
                    {"speaker": "A", "text": "Sure."},
                    {"speaker": "B", "text": "Thank you."},
                ]
            )[:10]

    elif t == "production":
        # Output task / speaking task
        if not slide.get("tasks"):
            slide["tasks"] = [
                "Pair work: create 3 sentences using today’s pattern.",
                "Role-play: use 6 lines in a short dialogue.",
            ]

    elif t == "review":
        if not slide.get("summary"):
            slide["summary"] = ["Key point 1", "Key point 2", "Key point 3"]

    elif t == "exit_ticket":
        qs = _as_list(slide.get("questions"))
        if len(qs) < 2:
            slide["questions"] = ["Write 1 sentence.", "Say it to your partner."]

    # Title fallback
    if not (slide.get("title") or "").strip():
        slide["title"] = "Slide"
    slide.setdefault("subtitle", "")

    # Notes fallback (optional)
    tn = (slide.get("teacher_notes") or "").strip()
    if not tn:
        slide["teacher_notes"] = ""

    return slide


def _normalize_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ValueError("bundle must be dict")

    # ---------------- Slides ----------------
    slides = bundle.get("slides", []) or []
    if isinstance(slides, dict) and "slides" in slides:
        slides = slides.get("slides", [])
    if not isinstance(slides, list):
        slides = []

    clean_slides: List[Dict[str, Any]] = []
    for s in slides:
        if not isinstance(s, dict):
            continue

        ns = dict(s)
        ns["type"] = (ns.get("type") or "context").strip()
        ns["title"] = (ns.get("title") or "").strip()
        ns["subtitle"] = (ns.get("subtitle") or "").strip()
        if ns.get("teacher_notes") is not None:
            ns["teacher_notes"] = (ns.get("teacher_notes") or "").strip()
        ns = _ensure_slide_has_content(ns)
        clean_slides.append(ns)

    # Guarantee enough slides (18–24). If fewer, pad with review/context slides.
    while len(clean_slides) < 18:
        clean_slides.append(
            {
                "type": "review",
                "title": f"Review {len(clean_slides) - 16}",
                "subtitle": "Check understanding",
                "summary": [
                    "Recall key vocabulary",
                    "Recall the pattern",
                    "Use it in a short sentence",
                ],
                "teacher_notes": "Quick recap. Ask 2–3 students to answer.",
            }
        )

    # If too many, keep max 24
    clean_slides = clean_slides[:24]

    # ---------------- Game ----------------
    game = bundle.get("game", {}) or {}
    if not isinstance(game, dict):
        game = {}

    for k in ["1", "2", "3"]:
        if k not in game or not isinstance(game[k], list):
            game[k] = []

        fixed = []
        for it in game[k][:24]:
            if not isinstance(it, dict):
                continue
            q = (it.get("question") or "").strip()
            a = (it.get("answer") or "").strip()
            pts = _clamp_int(it.get("points", 10), 5, 50, 10)
            if pts not in (10, 15, 20):
                pts = 10
            if q and a:
                fixed.append({"question": q, "answer": a, "points": pts})

        while len(fixed) < 24:
            fixed.append(
                {
                    "question": f"Bonus Q{len(fixed) + 1}",
                    "answer": "Any reasonable answer",
                    "points": 10,
                }
            )

        game[k] = fixed[:24]

    # ---------------- Practice (worksheet) ----------------
    practice = bundle.get("practice")
    if practice is None:
        for key in ["practices", "quiz", "worksheet", "practice_questions"]:
            if key in bundle:
                practice = bundle.get(key)
                break
    practice = practice or []
    if not isinstance(practice, list):
        practice = []

    clean_practice = []
    for it in practice:
        if not isinstance(it, dict):
            continue
        q = (it.get("question") or it.get("prompt") or "").strip()
        choices = it.get("choices") or it.get("options") or []
        ci = it.get("correct_index")
        if not q or not isinstance(choices, list):
            continue

        choices = [str(c).strip() for c in choices if str(c).strip()]
        while len(choices) < 4:
            choices.append(f"Option {len(choices) + 1}")
        if len(choices) > 4:
            choices = choices[:4]

        ci = _clamp_int(ci, 0, 3, 0)

        clean_practice.append(
            {
                "question": q,
                "choices": choices,
                "correct_index": ci,
                "explain": (it.get("explain") or "").strip(),
            }
        )

    # Ensure at least 20 questions
    while len(clean_practice) < 20:
        clean_practice.append(
            {
                "question": f"(Q{len(clean_practice) + 1}) Choose the best answer.",
                "choices": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explain": "",
            }
        )

    # Cap to 30
    clean_practice = clean_practice[:30]

    return {"slides": clean_slides, "game": game, "practice": clean_practice}


def _fallback_bundle(title: str, level: str, language: str, style: str) -> Dict[str, Any]:
    # A robust fallback with enough slides + vocab table.
    slides = [
        {
            "type": "hook",
            "title": title,
            "subtitle": f"Level: {level}",
            "prompt": "Warm-up: What would you say in this situation?",
            "keywords": ["real life", "simple", "useful"],
            "teacher_notes": "Ask students to answer freely first, then guide to the target language.",
        },
        {
            "type": "objectives",
            "title": "Today’s Goals",
            "objectives": [
                "Learn key vocabulary",
                "Use a key pattern",
                "Practice speaking in pairs",
            ],
            "teacher_notes": "Read objectives aloud. Keep it short.",
        },
        {
            "type": "context",
            "title": "Context",
            "content": [
                "Where are you?",
                "Who are you talking to?",
                "What do you want?",
            ],
            "teacher_notes": "Elicit ideas from students.",
        },
        {
            "type": "vocabulary",
            "title": "Vocabulary",
            "subtitle": "Key words",
            "items": [
                {
                    "word": "order",
                    "meaning": "สั่ง (อาหาร/เครื่องดื่ม)",
                    "example_en": "I'd like to order a latte.",
                    "example_th": "ฉันอยากสั่งลาเต้",
                },
                {
                    "word": "menu",
                    "meaning": "เมนู",
                    "example_en": "Can I see the menu?",
                    "example_th": "ขอดูเมนูได้ไหม",
                },
                {
                    "word": "bill",
                    "meaning": "บิล/เช็ค",
                    "example_en": "Could we have the bill, please?",
                    "example_th": "ขอบิลด้วยครับ/ค่ะ",
                },
                {
                    "word": "to go",
                    "meaning": "กลับบ้าน",
                    "example_en": "Can I get it to go?",
                    "example_th": "ขอใส่กลับบ้านได้ไหม",
                },
                {
                    "word": "recommend",
                    "meaning": "แนะนำ",
                    "example_en": "What do you recommend?",
                    "example_th": "แนะนำอะไรดี",
                },
            ],
            "teacher_notes": "Teach meaning + drill pronunciation quickly.",
        },
        {
            "type": "concept",
            "title": "Key Pattern",
            "subtitle": "Polite requests",
            "pattern": "Can I + verb ...?\nCould I + verb ...? (more polite)",
            "highlights": [
                {"label": "Can I", "note": "polite request"},
                {"label": "Could I", "note": "more polite request"},
            ],
            "common_mistakes": [
                "Wrong word order",
                "Too direct without please",
            ],
            "teacher_notes": "Model 3 sentences and let students repeat.",
        },
        {
            "type": "examples",
            "title": "Examples",
            "subtitle": "Say it naturally",
            "examples": [
                {"en": "Can I have a coffee, please?", "th": "ขอกาแฟแก้วนึงได้ไหมครับ/คะ"},
                {"en": "Could I get it to go?", "th": "ขอใส่กลับบ้านได้ไหมครับ/คะ"},
                {"en": "How much is it?", "th": "ราคาเท่าไหร่ครับ/คะ"},
            ],
            "teacher_notes": "Choral repetition: slow → natural speed.",
        },
        {
            "type": "guided_practice",
            "title": "Guided Practice",
            "subtitle": "Choose the best answer",
            "items": [
                {
                    "q": "… a latte, please.",
                    "choices": ["Can I have", "I want", "Give me", "I take"],
                    "answer": "Can I have",
                },
                {
                    "q": "… it to go?",
                    "choices": ["Could I get", "I want", "Give", "Need"],
                    "answer": "Could I get",
                },
                {
                    "q": "… the menu?",
                    "choices": ["Can I see", "I see", "Look", "Give"],
                    "answer": "Can I see",
                },
                {
                    "q": "… do you recommend?",
                    "choices": ["What", "When", "Where", "Who"],
                    "answer": "What",
                },
            ],
            "teacher_notes": "Pairs answer, then check together.",
        },
        {
            "type": "dialogue",
            "title": "Role-play Dialogue",
            "scenario": "At a coffee shop",
            "lines": [
                {"speaker": "A", "text": "Hi! What can I get you?"},
                {"speaker": "B", "text": "Can I have a latte, please?"},
                {"speaker": "A", "text": "Sure. Hot or iced?"},
                {"speaker": "B", "text": "Iced, please."},
                {"speaker": "A", "text": "Anything else?"},
                {"speaker": "B", "text": "That’s all. How much is it?"},
                {"speaker": "A", "text": "It’s 95 baht."},
                {"speaker": "B", "text": "Here you go. Thank you!"},
            ],
            "teacher_notes": "Students read once, then role-play with their own items.",
        },
        {
            "type": "production",
            "title": "Speaking Task",
            "subtitle": "Make it your own",
            "tasks": [
                "Pair work: Create 3 polite requests using Can I / Could I.",
                "Role-play: Customer + staff. Use at least 6 lines.",
            ],
            "teacher_notes": "Walk around and give quick feedback.",
        },
        {
            "type": "review",
            "title": "Review",
            "subtitle": "Quick check",
            "summary": [
                "Key words: order, menu, bill, to go",
                "Pattern: Can I / Could I + verb",
                "Be polite: please",
            ],
            "teacher_notes": "Ask 3 students to say one sentence each.",
        },
        {
            "type": "exit_ticket",
            "title": "Exit Ticket",
            "questions": [
                "Write 1 polite request.",
                "Say it to your partner.",
            ],
            "teacher_notes": "Collect answers or check quickly.",
        },
    ]

    # pad slides to at least 18
    while len(slides) < 18:
        slides.insert(-2, {
            "type": "vocabulary",
            "title": f"More Vocabulary {len(slides)-10}",
            "subtitle": "Extra practice",
            "items": [
                {"word": "sweet", "meaning": "หวาน", "example_en": "It’s too sweet.", "example_th": "หวานไป"},
                {"word": "bitter", "meaning": "ขม", "example_en": "It tastes bitter.", "example_th": "รสขม"},
                {"word": "spicy", "meaning": "เผ็ด", "example_en": "It’s very spicy.", "example_th": "เผ็ดมาก"},
                {"word": "sour", "meaning": "เปรี้ยว", "example_en": "It’s sour.", "example_th": "เปรี้ยว"},
            ],
            "teacher_notes": "Students describe their favorite food using 2 adjectives.",
        })

    game = {
        "1": [{"question": "Translate: ขอดูเมนูได้ไหม", "answer": "Can I see the menu?", "points": 10} for _ in range(24)],
        "2": [{"question": "Make a sentence with Could I…?", "answer": "Could I get …, please?", "points": 10} for _ in range(24)],
        "3": [{"question": "What does 'to go' mean?", "answer": "Take away / carry out", "points": 10} for _ in range(24)],
    }
    practice = [
        {
            "question": f"(Q{i+1}) Choose the correct option.",
            "choices": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explain": "",
        }
        for i in range(20)
    ]
    return _normalize_bundle({"slides": slides, "game": game, "practice": practice})


def generate_lesson_bundle(
    title: str,
    level: str = "Secondary",
    language: str = "EN",
    style: str = "Minimal",
    text_model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """
    language:
      - EN: English only
      - EN+TH: English with Thai support (gloss/translation)
      - TH: Thai only
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_bundle(title, level, language, style)

    client = OpenAI(api_key=api_key)

    # NOTE: slides_viewer.html already supports these slide types.
    instruction = f"""
You are an expert teacher who designs READY-TO-TEACH lesson decks.

Return ONE JSON object ONLY (valid JSON, no extra text) with:
{{
  "slides": [...],
  "game": {{"1":[...24], "2":[...24], "3":[...24]}},
  "practice": [...20-30]
}}

========================
A) SLIDES
========================
- Total slides: 18–24 (important: enough content for a full class)
- One slide = ONE teaching purpose
- Use classroom-friendly language
- Add "teacher_notes" in MOST slides (1–2 short sentences)
- Every slide MUST include some content (do not return empty slides)

Use these slide types (exact spelling):
1) type="hook"
   fields: title, subtitle, prompt, keywords (3-6), hero_image (optional), teacher_notes
2) type="objectives"
   fields: title, objectives (3-5), teacher_notes
3) type="context"
   fields: title, content (4-8 short lines), teacher_notes
4) type="vocabulary"  (IMPORTANT: table slide)
   fields: title, subtitle(optional), vocabulary (8-14 items)
   item fields (use EXACT keys):
     - word
     - meaning
     - example
   optional item fields:
     - example_th (only when language is EN+TH)
     - ipa
     - pronunciation_tip
5) type="concept"
   fields: title, subtitle(optional), pattern (2-6 lines), highlights (2-4 items: {{label,note}}),
           common_mistakes (2-4), teacher_notes
6) type="pronunciation"
   fields: title, subtitle(optional), content (3-6 bullets), examples (3-6: {{en, th(optional)}}), teacher_notes
7) type="examples"
   fields: title, subtitle(optional), examples (6-10 items: {{en, th(optional)}}), teacher_notes
8) type="guided_practice"
   fields: title, subtitle(optional), items (6-10 items: {{q, choices[4], answer}}), teacher_notes
9) type="dialogue"
   fields: title, scenario, lines (8-12 lines: {{speaker:"A/B", text}}), teacher_notes
10) type="production" (speaking/writing output task)
   fields: title, subtitle(optional), tasks (3-6 bullets), teacher_notes
11) type="review"
   fields: title, subtitle(optional), summary (4-8 bullets), teacher_notes
12) type="exit_ticket"
   fields: title, questions (2-4 short), teacher_notes

Language mode rules:
- If language="EN": everything in English. (No Thai)
- If language="EN+TH": keep English as main, but provide Thai support in meaning/example_th.
- If language="TH": everything in Thai (still keep structure; for examples use Thai sentences).

========================
B) GAME REQUIREMENTS
========================
- game must include keys "1","2","3"
- each set exactly 24 tiles
- tile object: {{"question":"", "answer":"", "points":10|15|20}}
- Align with slides (vocab/pattern/dialogue)

========================
C) PRACTICE REQUIREMENTS
========================
- 20–30 MCQs
- Each: {{"question":"", "choices":["A","B","C","D"], "correct_index":0-3, "explain":""}}
- Align with slides (concept + examples + dialogue)

Topic: "{title}"
Level: "{level}"
Language mode: "{language}"
Style: "{style}"

Return ONLY JSON.
""".strip()

    try:
        resp = client.responses.create(
            model=text_model,
            input=instruction,
            text={"format": {"type": "json_object"}},
        )
        data = _safe_json_loads(resp.output_text)
        return _normalize_bundle(data)
    except Exception as e:
        print("[AI] Bundle generation error:", e)
        return _fallback_bundle(title, level, language, style)
