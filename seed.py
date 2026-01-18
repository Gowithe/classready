# ==============================================================================
# FILE: seed.py
# ==============================================================================
import json
from models import Topic, GameQuestion, PracticeQuestion

def seed_sample_data():
    """Create 3 sample topics with content."""
    
    # Topic 1: Present Simple
    topic1 = Topic.create(
        name="Present Simple Tense",
        description="Learn the basics of present simple tense in English",
        slides_json=json.dumps({
            "slides": [
                {"type": "title", "title": "Present Simple Tense", "subtitle": "English Grammar Fundamentals"},
                {"type": "warmup", "title": "What do you know?", "content": "How do we describe habits and routines?"},
                {"type": "explanation", "title": "Formation", "content": "Subject + Verb (base form) + Object. For third person singular, add -s or -es.", "key_points": ["I/You/We/They + verb", "He/She/It + verb+s"]},
                {"type": "explanation", "title": "Usage", "content": "Used for habits, facts, routines, and general truths.", "key_points": ["Habitual actions", "General facts", "Schedules"]},
                {"type": "example", "title": "Example 1", "content": "I go to school every day. She works in a hospital."},
                {"type": "example", "title": "Example 2", "content": "They play football on weekends. The sun rises in the east."},
                {"type": "practice", "title": "Try it!", "content": "Write a sentence about your daily routine.", "question": "What is something you do every day?"},
                {"type": "summary", "title": "Summary", "content": "Present simple describes regular actions and facts.", "key_takeaways": ["For habits and routines", "Remember the -s/-es rule for third person"]}
            ]
        }),
        topic_type='manual'
    )
    
    # Add game questions for Topic 1
    game1_questions = [
        ("What is the base form for 'he goes'?", "go", 10),
        ("Write: I ___ English every day.", "speak", 10),
        ("Does she like tennis?", "Yes, she does.", 10),
        ("Complete: They ___ at home.", "live", 10),
        ("Is 'eating' used in present simple?", "No, it is not.", 10),
        ("Write: My mother ___ breakfast at 7am.", "makes", 10),
    ]
    for i, (q, a, p) in enumerate(game1_questions, 1):
        GameQuestion.create(topic1['id'], set_no=1, tile_no=i, question=q, answer=a, points=p)
    
    # Add more game questions for set 2
    for i, (q, a, p) in enumerate(game1_questions[:6], 1):
        GameQuestion.create(topic1['id'], set_no=2, tile_no=i, question=q, answer=a, points=p)
    
    # Add practice questions for Topic 1
    practice_topics = [
        ("multiple_choice", "What does 'present simple' describe?", "regular actions"),
        ("fill_blank", "I ___ coffee every morning.", "drink"),
        ("fill_blank", "She ___ in London.", "lives"),
        ("multiple_choice", "Which is correct: 'He go' or 'He goes'?", "He goes"),
        ("matching", "Match 'I work' with its meaning:", "habit"),
    ]
    for q_type, question, answer in practice_topics:
        PracticeQuestion.create(topic1['id'], q_type, question, answer)
    
    # Topic 2: Asking for Directions
    topic2 = Topic.create(
        name="Asking for Directions",
        description="Learn how to ask for and give directions in English",
        slides_json=json.dumps({
            "slides": [
                {"type": "title", "title": "Asking for Directions", "subtitle": "Practical English Communication"},
                {"type": "warmup", "title": "Scenario", "content": "You are lost in a new city. What do you ask?"},
                {"type": "explanation", "title": "Useful Phrases", "content": "Excuse me, where is...? Can you tell me the way to...? How do I get to...?", "key_points": ["Be polite with 'Excuse me'", "Use 'Where is' or 'How do I get to'"]},
                {"type": "explanation", "title": "Understanding Directions", "content": "Learn directional vocabulary: left, right, straight, north, south, near, far", "key_points": ["Compass directions", "Spatial prepositions"]},
                {"type": "example", "title": "Asking", "content": "Excuse me, how do I get to the railway station?"},
                {"type": "example", "title": "Answering", "content": "Go straight ahead and turn left at the traffic light."},
                {"type": "practice", "title": "Your turn", "content": "Practice asking for the nearest café.", "question": "Where is the nearest café?"},
                {"type": "summary", "title": "Summary", "content": "Key phrases for asking and understanding directions.", "key_takeaways": ["Use polite expressions", "Know direction vocabulary"]}
            ]
        }),
        topic_type='manual'
    )
    
    # Add game questions for Topic 2
    game2_questions = [
        ("How do you politely ask for directions?", "Excuse me...", 10),
        ("What does 'turn left' mean?", "Go to the left side", 10),
        ("Complete: 'Can you tell me the ___ to the bank?'", "way", 10),
        ("Is 'How do I get there?' a correct question?", "Yes", 10),
        ("What does 'straight ahead' mean?", "Continue in the same direction", 10),
        ("Complete: The hospital is ___. I can see it.", "near", 10),
    ]
    for i, (q, a, p) in enumerate(game2_questions, 1):
        GameQuestion.create(topic2['id'], set_no=1, tile_no=i, question=q, answer=a, points=p)
    
    # Topic 3: Parts of Speech
    topic3 = Topic.create(
        name="Parts of Speech",
        description="Understanding nouns, verbs, adjectives, and more",
        slides_json=json.dumps({
            "slides": [
                {"type": "title", "title": "Parts of Speech", "subtitle": "Building Blocks of Language"},
                {"type": "warmup", "title": "Warm-up", "content": "Can you identify different word types in a sentence?"},
                {"type": "explanation", "title": "Nouns & Verbs", "content": "Nouns: person, place, thing. Verbs: action or state words.", "key_points": ["Nouns are things or concepts", "Verbs describe what we do"]},
                {"type": "explanation", "title": "Adjectives & Adverbs", "content": "Adjectives describe nouns. Adverbs describe verbs, adjectives, or other adverbs.", "key_points": ["Adjectives: beautiful, big, happy", "Adverbs: quickly, slowly, happily"]},
                {"type": "example", "title": "Example 1", "content": "The quick brown fox jumps. (adj, noun, verb)"},
                {"type": "example", "title": "Example 2", "content": "She speaks English fluently. (verb, noun, adverb)"},
                {"type": "practice", "title": "Identify", "content": "Find the noun, verb, and adjective.", "question": "In 'The big dog runs fast', what is the verb?"},
                {"type": "summary", "title": "Summary", "content": "All words belong to a part of speech category.", "key_takeaways": ["Understand each part's role", "Practice identifying them"]}
            ]
        }),
        topic_type='manual'
    )
    
    # Add game questions for Topic 3
    game3_questions = [
        ("What is a noun?", "A person, place, or thing", 10),
        ("Is 'run' a verb?", "Yes", 10),
        ("What is an adjective?", "A word that describes a noun", 10),
        ("Complete: 'She sings ___.' (adverb)", "beautifully", 10),
        ("What part of speech is 'happy'?", "Adjective", 10),
        ("Is 'quickly' a verb?", "No, it is an adverb", 10),
    ]
    for i, (q, a, p) in enumerate(game3_questions, 1):
        GameQuestion.create(topic3['id'], set_no=1, tile_no=i, question=q, answer=a, points=p)
    
    print("✓ Sample data seeded successfully!")

# ==============================================================================
# FILE: requirements.txt
# ==============================================================================
# Flask 2.3.2
# Werkzeug 2.3.6
# openai 0.27.8 (optional, for AI slide generation)
# gunicorn 21.2.0 (for production)

# ==============================================================================
# FILE: Procfile
# ==============================================================================
# web: gunicorn app:app

# ==============================================================================
# FILE: .env.example
# ==============================================================================
# FLASK_ENV=production
# SECRET_KEY=your-secret-key-here-change-in-production
# ADMIN_EMAIL=admin@teacherplatform.com
# ADMIN_PASSWORD=Admin@12345
# OPENAI_API_KEY=sk-your-openai-key-optional