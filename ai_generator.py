# ==============================================================================
# FILE: ai_generator.py
# Generate PROFESSIONAL, CLASSROOM-READY lesson bundle as JSON
# - slides: 24–30 slides (full 60-90 minute lesson with rich content)
# - game: 3 sets x 24 tiles
# - practice: 25–35 MCQ (4 choices)
#
# IMPORTANT
# - Uses OpenAI Chat Completions API with json_object response format
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
        if len(objs) < 3:
            slide["objectives"] = objs + ["Understand the key idea", "Use it in speaking", "Practice with a partner"]
            slide["objectives"] = slide["objectives"][:5]

    elif t == "context":
        c = slide.get("content")
        if not c:
            slide["content"] = [
                "Where do we use this in real life?",
                "Who are you talking to?",
                "What do you want to achieve?",
            ]

    elif t == "vocabulary":
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
                    {"speaker": "B", "text": "I'd like …"},
                    {"speaker": "A", "text": "Sure."},
                    {"speaker": "B", "text": "Thank you."},
                ]
            )[:12]

    elif t == "production":
        if not slide.get("tasks"):
            slide["tasks"] = [
                "Pair work: create 3 sentences using today's pattern.",
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

    # Guarantee enough slides (24–30). If fewer, pad with review/context slides.
    while len(clean_slides) < 24:
        clean_slides.append(
            {
                "type": "review",
                "title": f"Review {len(clean_slides) - 20}",
                "subtitle": "Check understanding",
                "summary": [
                    "Recall key vocabulary",
                    "Recall the pattern",
                    "Use it in a short sentence",
                ],
                "teacher_notes": "Quick recap. Ask 2–3 students to answer.",
            }
        )

    # If too many, keep max 30
    clean_slides = clean_slides[:30]

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

    # Ensure at least 25 questions
    while len(clean_practice) < 25:
        clean_practice.append(
            {
                "question": f"(Q{len(clean_practice) + 1}) Choose the best answer.",
                "choices": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explain": "",
            }
        )

    # Cap to 35
    clean_practice = clean_practice[:35]

    return {"slides": clean_slides, "game": game, "practice": clean_practice}


def _fallback_bundle(title: str, level: str, language: str, style: str) -> Dict[str, Any]:
    """A robust fallback with rich content - enough for a real classroom."""
    slides = [
        # === OPENING (3 slides) ===
        {
            "type": "hook",
            "title": title,
            "subtitle": f"Level: {level}",
            "prompt": "Think about this: When was the last time you needed to use English in real life? What did you want to say?",
            "keywords": ["real-world", "practical", "everyday", "communication", "confidence"],
            "hero_image": "classroom",
            "teacher_notes": "Ask 2-3 students to share their experiences. Accept all answers warmly. This activates prior knowledge.",
        },
        {
            "type": "objectives",
            "title": "🎯 Today's Learning Goals",
            "objectives": [
                "Learn 12+ essential vocabulary words with correct pronunciation",
                "Master the key grammar pattern and use it confidently",
                "Practice real conversations through role-play activities",
                "Build fluency through speaking exercises with partners",
                "Apply what you learned in realistic situations",
            ],
            "teacher_notes": "Read objectives aloud. Ask: 'Which goal are you most excited about?' This creates buy-in.",
        },
        {
            "type": "context",
            "title": "📍 Real-Life Context",
            "subtitle": "When and where do we use this?",
            "content": [
                "🏪 At shops, restaurants, and cafés",
                "🏥 At hospitals, clinics, and pharmacies", 
                "🏫 At school talking to teachers and friends",
                "🏠 At home with family members",
                "📱 On the phone or sending messages",
                "✈️ When traveling to new places",
                "💼 In job interviews and at work",
                "🤝 Meeting new people and making friends",
            ],
            "teacher_notes": "Point to each context. Ask: 'Have you been in this situation?' Build relevance.",
        },
        
        # === VOCABULARY (3 slides with 18+ words total) ===
        {
            "type": "vocabulary",
            "title": "📚 Essential Vocabulary (Part 1)",
            "subtitle": "Core words you must know",
            "vocabulary": [
                {"word": "order", "meaning": "สั่ง (อาหาร/เครื่องดื่ม)", "example": "I'd like to order a coffee.", "ipa": "/ˈɔːrdər/"},
                {"word": "menu", "meaning": "เมนู/รายการ", "example": "Can I see the menu, please?", "ipa": "/ˈmenjuː/"},
                {"word": "bill", "meaning": "บิล/ใบเสร็จ", "example": "Could we have the bill?", "ipa": "/bɪl/"},
                {"word": "recommend", "meaning": "แนะนำ", "example": "What do you recommend?", "ipa": "/ˌrekəˈmend/"},
                {"word": "reserve", "meaning": "จอง", "example": "I'd like to reserve a table.", "ipa": "/rɪˈzɜːrv/"},
                {"word": "available", "meaning": "ว่าง/มี", "example": "Is this table available?", "ipa": "/əˈveɪləbl/"},
            ],
            "teacher_notes": "Teach each word: 1) Show word 2) Say it 3) Students repeat 3x 4) Show example 5) Students make their own sentence.",
        },
        {
            "type": "vocabulary",
            "title": "📚 Essential Vocabulary (Part 2)",
            "subtitle": "More useful expressions",
            "vocabulary": [
                {"word": "to go / takeaway", "meaning": "ซื้อกลับ", "example": "Can I get it to go?", "ipa": "/tuː ɡoʊ/"},
                {"word": "for here", "meaning": "ทานที่นี่", "example": "For here, please.", "ipa": "/fɔːr hɪr/"},
                {"word": "change", "meaning": "เงินทอน", "example": "Here's your change.", "ipa": "/tʃeɪndʒ/"},
                {"word": "receipt", "meaning": "ใบเสร็จ", "example": "Can I have a receipt?", "ipa": "/rɪˈsiːt/"},
                {"word": "tip", "meaning": "ทิป", "example": "Is tip included?", "ipa": "/tɪp/"},
                {"word": "special", "meaning": "พิเศษ/เมนูพิเศษ", "example": "What's today's special?", "ipa": "/ˈspeʃəl/"},
            ],
            "teacher_notes": "Quick drill: Teacher says Thai → Students say English. Then reverse. Make it a game!",
        },
        {
            "type": "vocabulary",
            "title": "📚 Essential Vocabulary (Part 3)",
            "subtitle": "Advanced expressions",
            "vocabulary": [
                {"word": "allergy", "meaning": "แพ้", "example": "I have a nut allergy.", "ipa": "/ˈælərdʒi/"},
                {"word": "vegetarian", "meaning": "มังสวิรัติ", "example": "Do you have vegetarian options?", "ipa": "/ˌvedʒəˈteriən/"},
                {"word": "spicy", "meaning": "เผ็ด", "example": "Not too spicy, please.", "ipa": "/ˈspaɪsi/"},
                {"word": "portion", "meaning": "ขนาด/ส่วน", "example": "Is this a large portion?", "ipa": "/ˈpɔːrʃn/"},
                {"word": "refill", "meaning": "เติม/รีฟิล", "example": "Can I get a refill?", "ipa": "/ˈriːfɪl/"},
                {"word": "complain", "meaning": "ร้องเรียน", "example": "I'd like to complain about the service.", "ipa": "/kəmˈpleɪn/"},
            ],
            "teacher_notes": "These are bonus words for stronger students. Spend less time here if class is struggling.",
        },
        
        # === GRAMMAR/CONCEPT (3 slides) ===
        {
            "type": "concept",
            "title": "🧠 Key Grammar Pattern",
            "subtitle": "Making polite requests",
            "pattern": "Can I + verb + (object) + please?\nCould I + verb + (object) + please?\nMay I + verb + (object) + please?",
            "highlights": [
                {"label": "Can I", "note": "Polite - use with friends, casual situations"},
                {"label": "Could I", "note": "More polite - use with strangers, formal situations"},
                {"label": "May I", "note": "Most polite - use with teachers, bosses, elderly"},
                {"label": "please", "note": "Always add 'please' to sound more polite!"},
            ],
            "common_mistakes": [
                "❌ 'I want coffee.' → ✅ 'Can I have a coffee, please?'",
                "❌ 'Give me the menu.' → ✅ 'Could I see the menu, please?'",
                "❌ 'Bill!' → ✅ 'May I have the bill, please?'",
                "❌ Using 'Can you...' when asking for yourself",
            ],
            "teacher_notes": "Write pattern on board. Demonstrate with gestures. Students copy in notebooks.",
        },
        {
            "type": "concept",
            "title": "🧠 More Useful Patterns",
            "subtitle": "Offering and responding",
            "pattern": "Would you like + noun/to + verb?\nI'd like + noun/to + verb.\nYes, please. / No, thank you.",
            "highlights": [
                {"label": "Would you like...?", "note": "Polite way to offer something"},
                {"label": "I'd like...", "note": "Polite way to say what you want (= I would like)"},
                {"label": "Yes, please.", "note": "Accepting an offer politely"},
                {"label": "No, thank you.", "note": "Refusing an offer politely"},
            ],
            "common_mistakes": [
                "❌ 'You want coffee?' → ✅ 'Would you like some coffee?'",
                "❌ 'I want to order.' → ✅ 'I'd like to order, please.'",
                "❌ 'No.' → ✅ 'No, thank you.'",
            ],
            "teacher_notes": "Model a mini-dialogue. Then students practice in pairs: offer → accept/refuse.",
        },
        {
            "type": "pronunciation",
            "title": "🎤 Pronunciation Focus",
            "subtitle": "Sound natural and confident",
            "content": [
                "🔊 Stress the important words: 'Can I HAVE a COFFEE, please?'",
                "🔊 Link words together: 'Can-I' sounds like 'CanI' /kænai/",
                "🔊 'Could I' sounds like /kʊdai/ - the 'L' is silent!",
                "🔊 Rise your voice at the end of questions ↗️",
                "🔊 'Please' at the end: lower and softer ↘️",
                "🔊 Practice: slow → medium → natural speed",
            ],
            "examples": [
                {"en": "Can I have... /kænai hæv/", "th": "เชื่อมเสียง Can + I"},
                {"en": "Could I get... /kʊdai ɡet/", "th": "ตัว L เงียบ"},
                {"en": "Would you like... /wʊdʒuː laɪk/", "th": "เชื่อมเสียง Would + you"},
                {"en": "I'd like... /aɪd laɪk/", "th": "ย่อจาก I would"},
            ],
            "teacher_notes": "Play audio if available. Otherwise, model clearly and have students repeat. Focus on linking sounds.",
        },
        
        # === EXAMPLES (2 slides with 15+ examples) ===
        {
            "type": "examples",
            "title": "💬 Example Sentences (Part 1)",
            "subtitle": "Ordering and requesting",
            "examples": [
                {"en": "Can I have a latte, please?", "th": "ขอลาเต้แก้วนึงค่ะ/ครับ"},
                {"en": "Could I see the menu?", "th": "ขอดูเมนูหน่อยได้ไหมคะ/ครับ"},
                {"en": "May I have the bill, please?", "th": "ขอบิลด้วยค่ะ/ครับ"},
                {"en": "I'd like to order now.", "th": "ฉันอยากสั่งตอนนี้ค่ะ/ครับ"},
                {"en": "Can I get this to go?", "th": "ขอใส่กลับบ้านได้ไหมคะ/ครับ"},
                {"en": "Could I have some water?", "th": "ขอน้ำเปล่าหน่อยได้ไหมคะ/ครับ"},
                {"en": "What do you recommend?", "th": "แนะนำอะไรดีคะ/ครับ"},
                {"en": "Is this spicy?", "th": "อันนี้เผ็ดไหมคะ/ครับ"},
            ],
            "teacher_notes": "Choral repetition: Teacher says → Whole class repeats. Then individual students.",
        },
        {
            "type": "examples",
            "title": "💬 Example Sentences (Part 2)",
            "subtitle": "Responding and clarifying",
            "examples": [
                {"en": "Yes, please. That sounds great.", "th": "ค่ะ/ครับ ฟังดูดี"},
                {"en": "No, thank you. I'm fine.", "th": "ไม่ค่ะ/ครับ ขอบคุณ"},
                {"en": "Sorry, could you repeat that?", "th": "ขอโทษค่ะ/ครับ พูดอีกทีได้ไหม"},
                {"en": "How much is this?", "th": "อันนี้ราคาเท่าไหร่คะ/ครับ"},
                {"en": "Do you have anything cheaper?", "th": "มีอะไรถูกกว่านี้ไหมคะ/ครับ"},
                {"en": "Can I pay by card?", "th": "จ่ายบัตรได้ไหมคะ/ครับ"},
                {"en": "Keep the change.", "th": "ไม่ต้องทอนค่ะ/ครับ"},
            ],
            "teacher_notes": "Students practice in pairs: Student A reads English, Student B says Thai meaning.",
        },
        
        # === GUIDED PRACTICE (2 slides) ===
        {
            "type": "guided_practice",
            "title": "✏️ Practice Exercise 1",
            "subtitle": "Choose the best answer",
            "items": [
                {"q": "_____ a coffee, please.", "choices": ["Can I have", "I want", "Give me", "I take"], "answer": "Can I have"},
                {"q": "_____ see the menu?", "choices": ["Could I", "I can", "Want I", "Let me"], "answer": "Could I"},
                {"q": "_____ some sugar, please?", "choices": ["May I have", "I need", "Bring me", "Want"], "answer": "May I have"},
                {"q": "I _____ to order the steak.", "choices": ["'d like", "wanting", "will want", "am want"], "answer": "'d like"},
                {"q": "_____ you like anything else?", "choices": ["Would", "Do", "Are", "Can"], "answer": "Would"},
            ],
            "teacher_notes": "Students work individually (2 min), then check with partner, then check as class. Discuss wrong answers.",
        },
        {
            "type": "guided_practice",
            "title": "✏️ Practice Exercise 2",
            "subtitle": "Complete the conversation",
            "items": [
                {"q": "Waiter: Are you ready to _____?", "choices": ["order", "menu", "bill", "tip"], "answer": "order"},
                {"q": "Customer: Yes, _____ the pasta, please.", "choices": ["I'd like", "I want", "Give", "Bring"], "answer": "I'd like"},
                {"q": "Waiter: Would you like anything to _____?", "choices": ["drink", "drinking", "drank", "drinks"], "answer": "drink"},
                {"q": "Customer: _____, I'll have water.", "choices": ["Yes, please", "Yes, I want", "Give me", "I need"], "answer": "Yes, please"},
                {"q": "Customer: Can I have the _____, please?", "choices": ["bill", "tip", "order", "menu"], "answer": "bill"},
            ],
            "teacher_notes": "Read the conversation aloud together. Then students role-play in pairs.",
        },
        
        # === DIALOGUE (2 slides) ===
        {
            "type": "dialogue",
            "title": "🎭 Role-Play Dialogue 1",
            "subtitle": "At a coffee shop",
            "scenario": "A customer orders at a coffee shop. Practice with a partner!",
            "lines": [
                {"speaker": "Staff", "text": "Hi! Welcome to Star Coffee. What can I get you?"},
                {"speaker": "Customer", "text": "Hi! Can I have a latte, please?"},
                {"speaker": "Staff", "text": "Sure! Would you like it hot or iced?"},
                {"speaker": "Customer", "text": "Iced, please."},
                {"speaker": "Staff", "text": "What size? Small, medium, or large?"},
                {"speaker": "Customer", "text": "Medium, please. How much is it?"},
                {"speaker": "Staff", "text": "That's 85 baht. For here or to go?"},
                {"speaker": "Customer", "text": "To go, please. Here you are."},
                {"speaker": "Staff", "text": "Thank you! Your drink will be ready in a moment."},
                {"speaker": "Customer", "text": "Thanks!"},
            ],
            "teacher_notes": "Demo with a strong student first. Then all students practice in pairs. Switch roles!",
        },
        {
            "type": "dialogue",
            "title": "🎭 Role-Play Dialogue 2",
            "subtitle": "At a restaurant",
            "scenario": "A customer orders food at a restaurant. Practice with a partner!",
            "lines": [
                {"speaker": "Waiter", "text": "Good evening! Here's the menu. I'll give you a moment."},
                {"speaker": "Customer", "text": "Thank you. Actually, I'm ready to order."},
                {"speaker": "Waiter", "text": "What would you like?"},
                {"speaker": "Customer", "text": "I'd like the grilled chicken, please."},
                {"speaker": "Waiter", "text": "Excellent choice. Would you like any sides?"},
                {"speaker": "Customer", "text": "Could I have some salad?"},
                {"speaker": "Waiter", "text": "Of course. Anything to drink?"},
                {"speaker": "Customer", "text": "Just water, please."},
                {"speaker": "Waiter", "text": "Perfect. Your order will be ready soon."},
                {"speaker": "Customer", "text": "Thank you very much!"},
            ],
            "teacher_notes": "Students can change the food items to their preferences. Encourage creativity!",
        },
        
        # === PRODUCTION (2 slides) ===
        {
            "type": "production",
            "title": "🎤 Speaking Task 1",
            "subtitle": "Create your own sentences",
            "tasks": [
                "📝 Write 5 polite requests using 'Can I / Could I / May I'",
                "💬 Practice saying each sentence 3 times",
                "👥 Share your sentences with a partner",
                "🔄 Listen to your partner's sentences and respond appropriately",
                "⭐ Choose your best sentence to share with the class",
            ],
            "teacher_notes": "Walk around and help students who are struggling. Give praise for good attempts!",
        },
        {
            "type": "production",
            "title": "🎤 Speaking Task 2",
            "subtitle": "Role-play challenge",
            "tasks": [
                "👥 Work with a partner",
                "🎭 Create your OWN dialogue (minimum 8 lines)",
                "📍 Choose a setting: coffee shop, restaurant, store, or hotel",
                "💡 Use at least 5 vocabulary words from today's lesson",
                "✨ Use at least 3 polite request patterns",
                "🎬 Perform your dialogue for another pair or the class",
            ],
            "teacher_notes": "Give students 5-7 minutes to prepare. Then have 2-3 pairs perform. Give positive feedback!",
        },
        
        # === REVIEW (2 slides) ===
        {
            "type": "review",
            "title": "📋 Lesson Summary",
            "subtitle": "What we learned today",
            "summary": [
                "📚 Key vocabulary: order, menu, bill, recommend, reserve, to go, receipt, tip",
                "🧠 Pattern 1: Can I / Could I / May I + verb + please?",
                "🧠 Pattern 2: Would you like...? / I'd like...",
                "🔊 Pronunciation: Link sounds together, stress important words",
                "🎭 Practice: Role-play ordering at a café and restaurant",
                "💡 Remember: Always use 'please' and 'thank you' to be polite!",
            ],
            "teacher_notes": "Quick recap. Ask students to tell you one thing they remember without looking at notes.",
        },
        {
            "type": "review",
            "title": "⚡ Quick Check",
            "subtitle": "Can you answer these?",
            "summary": [
                "❓ How do you politely ask for the menu?",
                "❓ How do you politely order a coffee?",
                "❓ What's the difference between 'Can I' and 'Could I'?",
                "❓ How do you ask for the bill?",
                "❓ What does 'to go' mean?",
                "❓ How do you respond to 'Would you like anything else?'",
            ],
            "teacher_notes": "Call on random students to answer. If they struggle, let a classmate help.",
        },
        
        # === EXIT TICKET (1 slide) ===
        {
            "type": "exit_ticket",
            "title": "🎫 Exit Ticket",
            "subtitle": "Before you leave...",
            "questions": [
                "✍️ Write ONE polite request you can use tomorrow",
                "💬 Say your sentence to your partner",
                "🤔 What was the most useful thing you learned today?",
                "⭐ Rate your confidence: 1-5 stars",
            ],
            "teacher_notes": "Collect exit tickets or have students share verbally. Use this to plan next lesson.",
        },
    ]

    # Generate game content
    game = {
        "1": [
            {"question": "Translate: ขอดูเมนูได้ไหม", "answer": "Can I see the menu?", "points": 10},
            {"question": "Translate: ขอกาแฟแก้วนึงค่ะ", "answer": "Can I have a coffee, please?", "points": 10},
            {"question": "Translate: ขอบิลด้วยค่ะ", "answer": "Could I have the bill, please?", "points": 10},
            {"question": "What does 'recommend' mean?", "answer": "แนะนำ", "points": 10},
            {"question": "What does 'reserve' mean?", "answer": "จอง", "points": 10},
            {"question": "What does 'available' mean?", "answer": "ว่าง/มี", "points": 10},
            {"question": "Translate: ซื้อกลับบ้าน", "answer": "To go / Takeaway", "points": 15},
            {"question": "Translate: ทานที่นี่", "answer": "For here", "points": 15},
            {"question": "What does 'receipt' mean?", "answer": "ใบเสร็จ", "points": 10},
            {"question": "What does 'tip' mean?", "answer": "ทิป", "points": 10},
            {"question": "Which is MORE polite: Can I or Could I?", "answer": "Could I", "points": 15},
            {"question": "What does 'allergy' mean?", "answer": "แพ้", "points": 10},
            {"question": "Complete: I ___ like to order.", "answer": "'d (would)", "points": 15},
            {"question": "How do you respond to 'Would you like anything else?' (Yes)", "answer": "Yes, please.", "points": 10},
            {"question": "How do you respond to 'Would you like anything else?' (No)", "answer": "No, thank you.", "points": 10},
            {"question": "What does 'vegetarian' mean?", "answer": "มังสวิรัติ", "points": 10},
            {"question": "Complete: ___ you like some water?", "answer": "Would", "points": 15},
            {"question": "What does 'portion' mean?", "answer": "ขนาด/ส่วน", "points": 10},
            {"question": "What does 'refill' mean?", "answer": "เติม/รีฟิล", "points": 10},
            {"question": "Translate: อันนี้เผ็ดไหม", "answer": "Is this spicy?", "points": 15},
            {"question": "Translate: จ่ายบัตรได้ไหม", "answer": "Can I pay by card?", "points": 15},
            {"question": "What does 'complain' mean?", "answer": "ร้องเรียน", "points": 10},
            {"question": "Translate: ราคาเท่าไหร่", "answer": "How much is it?", "points": 10},
            {"question": "What's another word for 'takeaway'?", "answer": "To go", "points": 10},
        ],
        "2": [
            {"question": "Make a request with 'Can I': coffee", "answer": "Can I have a coffee, please?", "points": 15},
            {"question": "Make a request with 'Could I': menu", "answer": "Could I see the menu, please?", "points": 15},
            {"question": "Make a request with 'May I': bill", "answer": "May I have the bill, please?", "points": 15},
            {"question": "Use 'I'd like' to order: steak", "answer": "I'd like the steak, please.", "points": 15},
            {"question": "Make a request with 'Can I': water", "answer": "Can I have some water, please?", "points": 15},
            {"question": "Make an offer with 'Would you like': dessert", "answer": "Would you like some dessert?", "points": 15},
            {"question": "Accept politely: 'Would you like more coffee?'", "answer": "Yes, please.", "points": 10},
            {"question": "Refuse politely: 'Would you like more coffee?'", "answer": "No, thank you.", "points": 10},
            {"question": "Ask for recommendation politely", "answer": "What do you recommend?", "points": 15},
            {"question": "Ask if something is spicy", "answer": "Is this spicy?", "points": 10},
            {"question": "Ask about the price", "answer": "How much is this?", "points": 10},
            {"question": "Request something 'to go'", "answer": "Can I get this to go, please?", "points": 15},
            {"question": "Make a request with 'Could I': table by window", "answer": "Could I have a table by the window?", "points": 20},
            {"question": "Say you're ready to order", "answer": "I'm ready to order.", "points": 10},
            {"question": "Ask for the receipt", "answer": "Can I have the receipt, please?", "points": 15},
            {"question": "Say 'keep the change'", "answer": "Keep the change.", "points": 10},
            {"question": "Ask if you can pay by card", "answer": "Can I pay by card?", "points": 15},
            {"question": "Make a reservation request", "answer": "I'd like to make a reservation.", "points": 15},
            {"question": "Ask if table is available", "answer": "Is this table available?", "points": 15},
            {"question": "Request less spicy food", "answer": "Not too spicy, please.", "points": 10},
            {"question": "Ask for vegetarian options", "answer": "Do you have vegetarian options?", "points": 15},
            {"question": "Request a refill", "answer": "Can I get a refill, please?", "points": 15},
            {"question": "Ask them to repeat", "answer": "Sorry, could you repeat that?", "points": 15},
            {"question": "Thank the server", "answer": "Thank you very much!", "points": 10},
        ],
        "3": [
            {"question": "What do you say first when entering a restaurant?", "answer": "Hello / Good evening", "points": 10},
            {"question": "Staff asks: 'For here or to go?' You want to eat there. What do you say?", "answer": "For here, please.", "points": 15},
            {"question": "You ordered the wrong food. How do you politely fix it?", "answer": "Excuse me, I ordered... not...", "points": 20},
            {"question": "The food is cold. How do you politely complain?", "answer": "Excuse me, this is cold.", "points": 20},
            {"question": "You need more time to decide. What do you say?", "answer": "Could I have a few more minutes?", "points": 15},
            {"question": "Staff asks: 'How was everything?' (It was good)", "answer": "It was delicious, thank you!", "points": 10},
            {"question": "You want to split the bill. What do you say?", "answer": "Can we split the bill?", "points": 15},
            {"question": "You need the WiFi password. Ask politely.", "answer": "Could I have the WiFi password?", "points": 15},
            {"question": "You're allergic to nuts. How do you ask?", "answer": "Does this have nuts? I have an allergy.", "points": 20},
            {"question": "You want to order the same as your friend. What do you say?", "answer": "I'll have the same, please.", "points": 15},
            {"question": "The waiter brings the wrong order. What do you say?", "answer": "Sorry, I think there's been a mistake.", "points": 20},
            {"question": "How do you get the waiter's attention politely?", "answer": "Excuse me...", "points": 10},
            {"question": "You want extra napkins. Ask politely.", "answer": "Could I have some extra napkins?", "points": 15},
            {"question": "You finished and want to pay. What do you say?", "answer": "Could I have the bill, please?", "points": 15},
            {"question": "How do you say 'I'm still deciding'?", "answer": "I'm still looking / I need more time.", "points": 15},
            {"question": "The service was great. How do you compliment?", "answer": "The service was excellent!", "points": 15},
            {"question": "You want to try before buying. Ask politely.", "answer": "Can I try this first?", "points": 15},
            {"question": "You want the food less sweet. What do you say?", "answer": "Not too sweet, please.", "points": 15},
            {"question": "Ask if the tip is included", "answer": "Is tip included?", "points": 15},
            {"question": "You want to take leftovers home. What do you say?", "answer": "Can I get a box for this?", "points": 15},
            {"question": "You're looking for the bathroom. Ask politely.", "answer": "Excuse me, where's the bathroom?", "points": 10},
            {"question": "You want to change your order. What do you say?", "answer": "Actually, can I change my order?", "points": 15},
            {"question": "Thank them at the end of the meal", "answer": "Thank you, everything was great!", "points": 10},
            {"question": "Say goodbye when leaving", "answer": "Thank you. Have a nice day!", "points": 10},
        ],
    }

    # Generate practice questions
    practice = [
        {"question": "How do you politely ask for a coffee?", "choices": ["Can I have a coffee, please?", "I want coffee.", "Give me coffee.", "Coffee!"], "correct_index": 0, "explain": "'Can I have... please?' is polite."},
        {"question": "Which is the MOST polite?", "choices": ["May I have the bill?", "Can I have the bill?", "I want the bill.", "Bill, please."], "correct_index": 0, "explain": "'May I' is the most polite form."},
        {"question": "'To go' means:", "choices": ["Take away", "Eat here", "Order more", "Pay now"], "correct_index": 0, "explain": "'To go' = takeaway = ซื้อกลับบ้าน"},
        {"question": "Staff: 'Would you like anything else?' You (No):", "choices": ["No, thank you.", "No.", "I don't want.", "Nothing."], "correct_index": 0, "explain": "'No, thank you' is polite."},
        {"question": "How do you ask for recommendation?", "choices": ["What do you recommend?", "What's good?", "Tell me food.", "Good food?"], "correct_index": 0, "explain": "'What do you recommend?' is natural and polite."},
        {"question": "'I'd like' is short for:", "choices": ["I would like", "I do like", "I did like", "I will like"], "correct_index": 0, "explain": "I'd = I would"},
        {"question": "Which is correct?", "choices": ["Could I see the menu?", "Could I see the menu?", "Can I to see the menu?", "I could see menu?"], "correct_index": 0, "explain": "Could I + verb (base form)"},
        {"question": "'Receipt' means:", "choices": ["ใบเสร็จ", "บิล", "เมนู", "ทิป"], "correct_index": 0, "explain": "Receipt = ใบเสร็จ"},
        {"question": "How do you say you're ready to order?", "choices": ["I'm ready to order.", "I want order.", "Order now.", "Ready."], "correct_index": 0, "explain": "'I'm ready to order' is natural."},
        {"question": "Fill in: _____ you like some dessert?", "choices": ["Would", "Do", "Are", "Is"], "correct_index": 0, "explain": "Would you like...? is the offer pattern."},
        {"question": "'Vegetarian' means:", "choices": ["มังสวิรัติ", "เผ็ด", "หวาน", "เปรี้ยว"], "correct_index": 0, "explain": "Vegetarian = ไม่ทานเนื้อสัตว์"},
        {"question": "How do you ask about the price?", "choices": ["How much is this?", "What price?", "How many?", "Cost?"], "correct_index": 0, "explain": "'How much is this?' is correct."},
        {"question": "Staff: 'For here or to go?' You (eat here):", "choices": ["For here, please.", "Here.", "I eat here.", "Stay."], "correct_index": 0, "explain": "'For here, please' is natural."},
        {"question": "'Allergy' means:", "choices": ["แพ้", "ชอบ", "ไม่ชอบ", "อร่อย"], "correct_index": 0, "explain": "Allergy = การแพ้"},
        {"question": "Which is NOT polite?", "choices": ["Give me the menu!", "Can I see the menu?", "Could I see the menu?", "May I see the menu?"], "correct_index": 0, "explain": "'Give me..!' sounds rude/commanding."},
        {"question": "How do you say 'ขอบิลด้วยค่ะ'?", "choices": ["Could I have the bill, please?", "Bill!", "I want bill.", "Give bill."], "correct_index": 0, "explain": "'Could I have the bill, please?' is polite."},
        {"question": "'Portion' means:", "choices": ["ขนาด/ส่วน", "ราคา", "รสชาติ", "สี"], "correct_index": 0, "explain": "Portion = ขนาด/ปริมาณ"},
        {"question": "How do you ask for a refill?", "choices": ["Can I get a refill?", "More drink!", "Refill!", "I want more."], "correct_index": 0, "explain": "'Can I get a refill?' is polite."},
        {"question": "'Keep the change' means:", "choices": ["ไม่ต้องทอน", "ขอเงินทอน", "จ่ายเงิน", "แพงไป"], "correct_index": 0, "explain": "Keep the change = ไม่ต้องทอน"},
        {"question": "Fill in: I _____ like the steak, please.", "choices": ["'d", "am", "will", "do"], "correct_index": 0, "explain": "I'd like = I would like"},
        {"question": "How do you ask someone to repeat?", "choices": ["Sorry, could you repeat that?", "What?", "Again!", "I don't understand."], "correct_index": 0, "explain": "'Could you repeat that?' is polite."},
        {"question": "'Spicy' means:", "choices": ["เผ็ด", "หวาน", "เค็ม", "เปรี้ยว"], "correct_index": 0, "explain": "Spicy = เผ็ด"},
        {"question": "What do you say when the food is delicious?", "choices": ["This is delicious!", "Good.", "I like.", "Yummy yummy."], "correct_index": 0, "explain": "'This is delicious!' is natural."},
        {"question": "How do you get the waiter's attention?", "choices": ["Excuse me...", "Hey!", "Waiter!", "Come here!"], "correct_index": 0, "explain": "'Excuse me' is polite."},
        {"question": "'Reserve' means:", "choices": ["จอง", "สั่ง", "จ่าย", "กิน"], "correct_index": 0, "explain": "Reserve = จอง"},
    ]

    return _normalize_bundle({"slides": slides, "game": game, "practice": practice})


def generate_lesson_bundle(
    title: str,
    level: str = "Secondary",
    language: str = "EN",
    style: str = "Detailed",
    text_model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """
    Generate a PROFESSIONAL, CLASSROOM-READY lesson bundle.
    
    language:
      - EN: English only
      - EN+TH: English with Thai support (gloss/translation)
      - TH: Thai only
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[AI] No API key found, using fallback bundle")
        return _fallback_bundle(title, level, language, style)

    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        print(f"[AI] Failed to create OpenAI client: {e}")
        print("[AI] This may be due to openai/httpx version mismatch. Using fallback bundle.")
        return _fallback_bundle(title, level, language, style)

    instruction = f"""
You are a MASTER TEACHER and curriculum designer who creates PROFESSIONAL, READY-TO-TEACH lesson materials.

Your slides should be SO GOOD that teachers can walk into class and teach immediately without any extra preparation.

Return ONE JSON object ONLY (valid JSON, no extra text) with:
{{
  "slides": [...],
  "game": {{"1":[...24], "2":[...24], "3":[...24]}},
  "practice": [...25-35]
}}

========================
A) SLIDES - CREATE 30-40 SLIDES (MORE IS BETTER!)
========================
Make this lesson RICH, DETAILED, and CLASSROOM-READY!

⚠️ CRITICAL RULE: SPLIT CONTENT INTO MULTIPLE SLIDES!
- Each slide should display content that fits on ONE SCREEN without scrolling
- NEVER put too much content on one slide - SPLIT into multiple slides instead
- More slides = Better! Teachers prefer many clear slides over few crowded ones

REQUIRED SLIDE SEQUENCE (follow this order):

1. hook (1 slide) - Engaging warm-up with thought-provoking question

2. objectives (1 slide) - 4-5 clear, measurable learning goals

3. context (1-2 slides) - Real-world situations where this language is used

4. vocabulary (5-8 slides) - SPLIT vocabulary across multiple slides!
   ⚠️ MAX 4-5 words per slide! If you have 20 words, create 4-5 vocabulary slides!
   - "Vocabulary 1" (words 1-4)
   - "Vocabulary 2" (words 5-8)
   - "Vocabulary 3" (words 9-12)
   - etc.

5. concept (2-3 slides) - Grammar patterns with highlights and common mistakes

6. pronunciation (1-2 slides) - Sound tips, stress patterns, linking

7. examples (3-5 slides) - SPLIT examples across multiple slides!
   ⚠️ MAX 4-5 examples per slide! If you have 15 examples, create 3-4 slides!
   - "Examples 1" (sentences 1-4)
   - "Examples 2" (sentences 5-8)
   - etc.

8. guided_practice (3-4 slides) - SPLIT practice questions!
   ⚠️ MAX 3-4 questions per slide!

9. dialogue (3-6 slides) - SPLIT dialogues across multiple slides!
   ⚠️ MAX 6 lines per slide! If dialogue has 12 lines, split into 2 slides!
   - "Dialogue Part 1" (lines 1-6)
   - "Dialogue Part 2" (lines 7-12)

10. production (2 slides) - Speaking/writing tasks for fluency

11. review (2 slides) - Summary + quick check questions

12. exit_ticket (1 slide) - Final assessment questions

SLIDE TYPE SPECIFICATIONS:

type="hook"
  fields: title, subtitle, prompt (engaging question), keywords (5-8), hero_image (optional), teacher_notes
  EXAMPLE: "Think about this: When was the last time you had to speak English? What did you want to say?"

type="objectives" 
  fields: title, objectives (4-5 specific, measurable goals), teacher_notes
  EXAMPLE: ["Learn 15+ vocabulary words", "Master the request pattern 'Can I/Could I'", "Practice ordering in role-play"]

type="context"
  fields: title, subtitle, content (4-6 bullet points max), teacher_notes
  
type="vocabulary" (⚠️ MAX 4-5 WORDS PER SLIDE!)
  fields: title, subtitle, vocabulary (4-5 items MAXIMUM per slide)
  Each vocabulary item MUST have:
    - word: the English word
    - meaning: Thai meaning
    - example: full sentence using the word
    - ipa: pronunciation in IPA (e.g., /ˈɔːrdər/)
  optional: example_th, pronunciation_tip
  ⚠️ If you have 20 vocabulary words, create 4-5 separate vocabulary slides!

type="concept"
  fields: title, subtitle, pattern (clear structure), highlights (3-4 items max), common_mistakes (2-3 max), teacher_notes

type="pronunciation"
  fields: title, subtitle, content (4-5 tips max), examples (3-4 max), teacher_notes

type="examples" (⚠️ MAX 4-5 EXAMPLES PER SLIDE!)
  fields: title, subtitle, examples (4-5 items MAXIMUM per slide, each with en and th), teacher_notes
  ⚠️ If you have 15 examples, create 3-4 separate example slides!

type="guided_practice" (⚠️ MAX 3-4 QUESTIONS PER SLIDE!)
  fields: title, subtitle, items (3-4 MCQ MAXIMUM per slide, each with q, choices[4], answer), teacher_notes

type="dialogue" (⚠️ MAX 6 LINES PER SLIDE!)
  fields: title, subtitle, scenario (situation description), lines (6 lines MAXIMUM per slide), teacher_notes
  ⚠️ If dialogue has 12 lines, split into "Part 1" and "Part 2" slides!

type="production"
  fields: title, subtitle, tasks (4-5 activities max), teacher_notes

type="review"
  fields: title, subtitle, summary (5-6 bullet points max), teacher_notes

type="exit_ticket"
  fields: title, subtitle, questions (3-4 questions max), teacher_notes

CRITICAL REQUIREMENTS:
- ⚠️ SPLIT CONTENT! Never crowd a slide - create more slides instead!
- Include teacher_notes for EVERY slide (1-3 helpful sentences)
- Vocabulary slides: Include IPA pronunciation for every word
- Examples: Always include both English and Thai translation
- Dialogues: Split long dialogues into Part 1, Part 2, etc.
- Guided practice: Questions should test understanding, not memory
- Make content PRACTICAL and relevant to students' real lives

========================
B) GAME - 3 SETS x 24 TILES EACH
========================
Create engaging game content that reinforces the lesson:

Set "1": Translation & Vocabulary (Thai ↔ English)
Set "2": Sentence Production (Create sentences with given patterns)
Set "3": Real-Life Situations (What would you say in this situation?)

Each tile: {{"question":"", "answer":"", "points": 10|15|20}}
- Easy questions: 10 points
- Medium questions: 15 points
- Hard questions: 20 points

========================
C) PRACTICE - 25-35 MCQ
========================
Create comprehensive practice questions:
- Each: {{"question":"", "choices":["A","B","C","D"], "correct_index":0-3, "explain":""}}
- Include questions testing vocabulary, grammar, usage, and comprehension
- Provide brief explanation for each answer
- Mix difficulty levels: 40% easy, 40% medium, 20% challenging

========================
TOPIC DETAILS
========================
Topic: "{title}"
Level: "{level}"
Language mode: "{language}"
Style: "{style}"

Language mode rules:
- EN: Everything in English (no Thai)
- EN+TH: English main content with Thai translations/meanings
- TH: Everything in Thai

========================
QUALITY STANDARDS
========================
- Content must be RICH ENOUGH for a 60-90 minute class
- Every slide must have SUBSTANTIAL content (no empty or minimal slides)
- Examples should be NATURAL and commonly used
- Make it PRACTICAL - students should be able to use this language TODAY
- Include TEACHER NOTES that actually help teachers teach better

Return ONLY valid JSON. No markdown, no extra text.
""".strip()

    try:
        resp = client.chat.completions.create(
            model=text_model,
            messages=[
                {"role": "system", "content": "You are an expert curriculum designer who creates professional, comprehensive lesson materials. Return only valid JSON, no markdown, no extra text."},
                {"role": "user", "content": instruction}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=16000,  # Increased for richer content
        )
        
        content = resp.choices[0].message.content
        data = _safe_json_loads(content)
        return _normalize_bundle(data)
        
    except Exception as e:
        print("[AI] Bundle generation error:", repr(e))
        import traceback
        traceback.print_exc()
        return _fallback_bundle(title, level, language, style)
