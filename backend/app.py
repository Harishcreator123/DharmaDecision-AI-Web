
from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import json
import math
import re
import os
import sqlite3


# ============================================================
# 1. PATHS AND KNOWLEDGE BASE
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "vidura_niti.json"
FRONTEND_DIR = ROOT / "frontend"
DB_PATH = Path(
    os.environ.get("FEEDBACK_DB_PATH", str(ROOT / "feedback.sqlite3"))
)

with open(DATA_FILE, "r", encoding="utf-8") as f:
    records = json.load(f)

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR / "static")
)


# ============================================================
# 2. TEXT PROCESSING
# ============================================================

STOP_WORDS = set("""
a an the and or but if then is am are was were be been being
to of in on at for from with by as it this that these those
i me my we our you your he she they them do does did what
how why when where who should would could can will about want
need like please
""".split())


def tokenize(text):
    """Convert text to lowercase words and remove common stop words."""
    return [
        word
        for word in re.findall(
            r"[^\W_]+", str(text).lower(), flags=re.UNICODE
        )
        if word not in STOP_WORDS and len(word) > 1
    ]


def record_text(record):
    """Build searchable text from all relevant knowledge-base fields."""
    fields = (
        "principle",
        "text",
        "source",
        "parva",
        "section",
        "context",
        "themes",
        "episode",
        "dilemma_examples",
        "source_type",
    )

    parts = []

    for field in fields:
        value = record.get(field, "")

        if isinstance(value, list):
            value = " ".join(str(item) for item in value)

        parts.append(str(value))

    return " ".join(parts)


# Prepare searchable records once when the backend starts.
docs = [record_text(record) for record in records]
doc_tokens = [tokenize(document) for document in docs]
doc_token_sets = [set(tokens) for tokens in doc_tokens]


# ============================================================
# 3. SAFETY CLASSIFICATION
# ============================================================

VIOLENT_ACTIONS = set("""
kill murder stab shoot strangle choke poison attack hurt beat
harm assassinate
""".split())

TARGETS = set("""
friend person someone him her them people classmate teacher
professor partner wife husband boyfriend girlfriend family
colleague boss
""".split())

DIRECT_PHRASES = (
    "want to kill",
    "going to kill",
    "i will kill",
    "i'll kill",
    "kill my friend",
    "kill someone",
    "kill him",
    "kill her",
    "kill them",
    "want to hurt",
    "going to hurt",
    "i will hurt",
    "i want to murder",
    "planning to kill",
    "how do i kill",
    "how to kill",
    "help me kill",
    "i might kill",
    "i am going to attack",
    "best way to kill",
    "ways to poison",
    "how to hurt someone",
    "help me attack",
)

CONTEXT_HINTS = (
    "in the mahabharata",
    "in the story",
    "fictional",
    "for my novel",
    "for a story",
    "historical account",
    "literature analysis",
    "translate the phrase",
    "meaning of the phrase",
    "in a video game",
    "historical question",
)

HISTORY_HINTS = (
    "what happened",
    "who killed",
    "why did",
    "historical",
    "character",
    "battle of",
    "describe the war",
)


def classify_safety(text):
    """Apply a basic rule-based safety check."""
    low = re.sub(r"\s+", " ", text.lower()).strip()
    words = set(tokenize(low))

    contextual = any(hint in low for hint in CONTEXT_HINTS)
    historical = contextual or any(
        hint in low for hint in HISTORY_HINTS
    )

    has_action = bool(words & VIOLENT_ACTIONS)
    direct = any(phrase in low for phrase in DIRECT_PHRASES)

    first_person = bool(
        re.search(
            r"\b(i|i'm|i am|i'll|i will|im|my)\b",
            low
        )
    )

    target = bool(words & TARGETS)

    if not contextual and (
        direct or (first_person and has_action and target)
    ):
        return "high_risk"

    if not contextual and any(
        phrase in low
        for phrase in (
            "how to kill",
            "how do i kill",
            "best way to kill",
            "how to hurt someone",
            "ways to poison",
        )
    ):
        return "high_risk"

    if has_action and historical:
        return "historical_or_fictional"

    return "normal"


# ============================================================
# 4. QUERY CONCEPT EXPANSION
# ============================================================

CONCEPT_MAP = {
    # Trust, loyalty, and relationships
    "friend": [
        "trust", "character", "loyalty", "fairness"
    ],
    "loyalty": [
        "friend", "trust", "justice", "fairness",
        "responsibility", "relationships"
    ],
    "betray": [
        "trust", "honesty", "character", "loyalty"
    ],
    "betrayed": [
        "trust", "honesty", "character", "loyalty"
    ],
    "cheat": [
        "trust", "honesty", "truthful", "character", "fairness"
    ],
    "cheated": [
        "trust", "honesty", "truthful", "character", "fairness"
    ],
    "lie": ["truthful", "honesty", "trust"],
    "lied": ["truthful", "honesty", "trust"],
    "unfair": [
        "fairness", "justice", "responsibility"
    ],
    "unfairly": [
        "fairness", "justice", "responsibility"
    ],
    "injustice": [
        "justice", "fairness", "responsibility"
    ],
    "wrongdoing": [
        "justice", "fairness", "responsibility"
    ],

    # Conflict and negotiation
    "conflict": [
        "negotiation", "peace", "compromise", "consequences"
    ],
    "fight": [
        "conflict", "peace", "negotiation", "consequences"
    ],
    "war": [
        "conflict", "peace", "diplomacy", "consequences"
    ],
    "negotiate": [
        "negotiation", "peace", "compromise", "diplomacy"
    ],
    "compromise": [
        "negotiation", "fairness", "justice", "peace"
    ],
    "opponent": [
        "negotiation", "diplomacy", "conflict", "understanding"
    ],
    "revenge": [
        "anger", "self-control", "consequences", "restraint"
    ],
    "escalation": [
        "conflict", "consequences", "restraint"
    ],

    # Leadership and decisions
    "leader": [
        "leadership", "responsibility", "justice", "counsel"
    ],
    "leadership": [
        "responsibility", "justice", "counsel", "self-control"
    ],
    "decision": [
        "ethical decision", "consequences", "responsibility"
    ],
    "advice": [
        "counsel", "wisdom", "truthful", "decision"
    ],
    "pride": [
        "self-control", "humility", "conflict", "consequences"
    ],
    "power": [
        "responsibility", "leadership", "justice"
    ],
    "duty": [
        "responsibility", "justice", "relationships"
    ],
    "responsibility": [
        "duty", "justice", "fairness", "consequences"
    ],

    # Emotional control and reflection
    "angry": [
        "anger", "self-control", "reflection"
    ],
    "anger": [
        "self-control", "reflection", "consequences"
    ],
    "forgive": [
        "anger", "self-control", "reflection", "trust"
    ],
    "forgiveness": [
        "anger", "self-control", "reflection", "trust"
    ],
    "confront": [
        "honesty", "truthful advice", "consequences"
    ],
    "regret": [
        "reflection", "consequences", "reconsideration"
    ],
    "reconsider": [
        "reflection", "consequences", "decision"
    ],
}


def expand_query(query):
    """
    Preserve original query terms and add related concepts.
    Original terms receive more weight during retrieval.
    """
    original_words = set(tokenize(query))
    expanded_words = set(original_words)

    query_lower = query.lower()

    for keyword, related_terms in CONCEPT_MAP.items():
        if re.search(
            r"\b" + re.escape(keyword) + r"\b",
            query_lower
        ):
            expanded_words.update(tokenize(" ".join(related_terms)))

    return original_words, expanded_words


# ============================================================
# 5. EVIDENCE RETRIEVAL
# ============================================================

def retrieve_evidence(query, k=3):
    """
    Rank records using:
    - overlap with the user's original words
    - overlap with expanded concepts
    - direct principle-name matches
    - matches in dilemma examples and themes

    The returned score is a retrieval relevance score, not
    a probability or validated confidence percentage.
    """
    original_words, expanded_words = expand_query(query)

    if not original_words:
        return []

    scored = []

    for index, record in enumerate(records):
        principle_words = set(
            tokenize(record.get("principle", ""))
        )

        text_words = set(
            tokenize(record.get("text", ""))
        )

        themes = record.get("themes", "")
        examples = record.get("dilemma_examples", "")

        if isinstance(themes, list):
            themes = " ".join(str(x) for x in themes)

        if isinstance(examples, list):
            examples = " ".join(str(x) for x in examples)

        theme_words = set(tokenize(themes))
        example_words = set(tokenize(examples))

        document_words = doc_token_sets[index]

        original_matches = original_words & document_words
        expanded_matches = expanded_words & document_words
        principle_matches = original_words & principle_words
        theme_matches = expanded_words & theme_words
        example_matches = original_words & example_words

        # Original query matches matter more than added concepts.
        original_ratio = (
            len(original_matches) / len(original_words)
        )

        expanded_only = expanded_words - original_words
        expanded_ratio = (
            len(expanded_matches & expanded_only)
            / len(expanded_only)
            if expanded_only else 0.0
        )

        principle_bonus = (
            0.15 if principle_matches else 0.0
        )

        theme_bonus = (
            0.12 if theme_matches else 0.0
        )

        example_bonus = (
            0.18 if example_matches else 0.0
        )

        score = (
            0.60 * original_ratio
            + 0.20 * expanded_ratio
            + principle_bonus
            + theme_bonus
            + example_bonus
        )

        score = min(score, 1.0)

        matched_terms = (
            original_matches
            | expanded_matches
            | principle_matches
            | theme_matches
            | example_matches
        )

        if score > 0:
            scored.append(
                (score, record, matched_terms)
            )

    # Sort by score, then prefer direct principle matches.
    scored.sort(
        key=lambda item: (
            item[0],
            len(
                original_words
                & set(tokenize(item[1].get("principle", "")))
            ),
        ),
        reverse=True,
    )

    results = []

    for score, record, matched_terms in scored[:k]:
        results.append({
            "id": record.get("id", ""),
            "principle": record.get("principle", ""),
            "text": record.get("text", ""),
            "source": record.get("source", ""),
            "parva": record.get("parva", ""),
            "section": record.get("section", ""),
            "similarity": round(float(score), 4),
            "evidence_type": record.get(
                "source_type", "Paraphrase"
            ),
            "matched_terms": sorted(matched_terms),
        })

    return results


# ============================================================
# 6. RECOMMENDATION
# ============================================================

def make_recommendation(evidence):
    if not evidence or evidence[0]["similarity"] < 0.12:
        return (
            "I could not find sufficiently relevant evidence "
            "in the current knowledge base to support a "
            "responsible recommendation. Please provide more "
            "context or try rephrasing your dilemma."
        )

    top = evidence[0]

    return (
        f"The closest retrieved principle is "
        f"“{top.get('principle', 'Relevant principle')}.” "
        f"{top.get('text', '')} "
        "This is a possible ethical perspective, not a "
        "definitive answer. Consider the circumstances, "
        "people affected, fairness, responsibility, and "
        "likely consequences."
    )


# ============================================================
# 7. FEEDBACK DATABASE AND METRICS
# ============================================================

def init_db():
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    query_category TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    metric_key TEXT PRIMARY KEY,
                    metric_value INTEGER NOT NULL
                )
            """)

    except Exception as error:
        print(f"Feedback database unavailable: {error}")


def metric(key):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO metrics(metric_key, metric_value)
                VALUES (?, 1)
                ON CONFLICT(metric_key)
                DO UPDATE SET metric_value = metric_value + 1
            """, (key,))

    except Exception as error:
        print(f"Metric update unavailable: {error}")


init_db()


# ============================================================
# 8. FRONTEND ROUTE
# ============================================================

@app.route("/")
def home():
    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


# ============================================================
# 9. HEALTH CHECK API
# ============================================================

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "DharmaDecision-AI",
        "retrieval_method": "weighted keyword and concept matching",
        "evidence_count": len(records),
        "confidence_score": "disabled until validated",
    })


# ============================================================
# 10. ETHICAL DILEMMA ANALYSIS API
# ============================================================

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    query = str(data.get("dilemma", "")).strip()

    if not query:
        return jsonify({
            "error": "Please enter an ethical dilemma."
        }), 400

    if len(query) > 3000:
        return jsonify({
            "error": "Please keep your question under 3000 characters."
        }), 400

    safety = classify_safety(query)
    metric("requests_total")

    if safety == "high_risk":
        metric("requests_high_risk")

        return jsonify({
            "dilemma": query,
            "intent": "potential immediate harm",
            "safety_status": "high_risk",
            "recommendation": (
                "Your message suggests someone may be at risk "
                "of being harmed. I can't help justify or plan "
                "violence. Please move away from your friend "
                "and from any weapons or objects you could use "
                "to hurt them. Contact someone you trust who "
                "can stay with you. If you think you might act "
                "soon or anyone is in immediate danger, contact "
                "local emergency services now. Are you with "
                "your friend right now, and do you feel you "
                "might act on this?"
            ),
            "confidence": None,
            "confidence_label": "Not applicable",
            "evidence": [],
            "message": (
                "Safety response shown; ordinary evidence "
                "retrieval was skipped."
            ),
        })

    evidence = retrieve_evidence(query, 3)
    score = evidence[0]["similarity"] if evidence else 0.0

    # This is a heuristic threshold, not a validated accuracy measure.
    relevant = score >= 0.12

    if not relevant:
        metric("low_relevance_requests")

    return jsonify({
        "dilemma": query,
        "intent": (
            "historical_or_fictional"
            if safety == "historical_or_fictional"
            else "ethical_or_general_query"
        ),
        "safety_status": "normal",
        "recommendation": make_recommendation(evidence),
        "confidence": None,
        "confidence_label": "Not yet statistically validated",
        "relevance": round(float(score), 4),
        "relevance_status": (
            "Potentially relevant"
            if relevant
            else "Insufficient evidence"
        ),
        "evidence": evidence if relevant else [],
        "message": (
            None
            if relevant
            else "No sufficiently relevant evidence was found. "
                 "No confidence percentage is provided."
        ),
    })


# ============================================================
# 11. FEEDBACK API
# ============================================================

@app.route("/api/feedback", methods=["POST"])
def feedback():
    data = request.get_json(silent=True) or {}

    rating = str(data.get("rating", "")).strip().lower()

    if rating not in {
        "helpful", "not_helpful", "irrelevant", "unsafe"
    }:
        return jsonify({
            "error": "Invalid feedback rating."
        }), 400

    category = str(data.get("category", "general"))[:80]
    ids = data.get("evidence_ids", [])

    ids = (
        [str(item)[:100] for item in ids[:10]]
        if isinstance(ids, list)
        else []
    )

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO feedback(
                    created_at,
                    query_category,
                    rating,
                    evidence_ids
                )
                VALUES (?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                category,
                rating,
                json.dumps(ids),
            ))

    except Exception:
        return jsonify({
            "status": "not_saved",
            "message": (
                "Feedback storage is unavailable in this deployment."
            ),
        }), 503

    return jsonify({
        "status": "recorded",
        "message": (
            "Thank you. Feedback was recorded for future evaluation."
        ),
    })


# ============================================================
# 12. START FLASK
# ============================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
