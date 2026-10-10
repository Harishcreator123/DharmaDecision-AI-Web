from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
from collections import Counter
import json, math, re, os, sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "vidura_niti.json"
FRONTEND_DIR = ROOT / "frontend"
DB_PATH = Path(os.environ.get("FEEDBACK_DB_PATH", str(ROOT / "feedback.sqlite3")))

with open(DATA_FILE, "r", encoding="utf-8") as f:
    records = json.load(f)

app = Flask(__name__, static_folder=str(FRONTEND_DIR / "static"))

STOP_WORDS = set("""a an the and or but if then is am are was were be been being to of in on at for from with by as it this that these those i me my we our you your he she they them do does did what how why when where who should would could can will about want need like please""".split())

def tokenize(text):
    return [w for w in re.findall(r"[^\W_]+", str(text).lower(), flags=re.UNICODE)
            if w not in STOP_WORDS and len(w) > 1]

def record_text(r):
    return " ".join(str(r.get(k, "")) for k in
                    ("principle", "text", "source", "parva", "section", "context", "themes"))

docs = [record_text(r) for r in records]
doc_tokens = [tokenize(d) for d in docs]
doc_freq = Counter()
for ts in doc_tokens:
    doc_freq.update(set(ts))
N = max(len(docs), 1)

def vectorize(tokens):
    if not tokens:
        return {}
    counts, length, vec = Counter(tokens), max(len(tokens), 1), {}
    for word, count in counts.items():
        df = doc_freq.get(word, 0)
        if df:
            vec[word] = (count / length) * (math.log(1 + N / (1 + df)) + 1)
    norm = math.sqrt(sum(v*v for v in vec.values()))
    return {k: v/norm for k, v in vec.items()} if norm else {}

doc_vectors = [vectorize(ts) for ts in doc_tokens]

def cosine_sparse(a, b):
    return sum(v * b.get(k, 0.0) for k, v in a.items()) if a and b else 0.0

VIOLENT_ACTIONS = set("kill murder stab shoot strangle choke poison attack hurt beat harm assassinate".split())
TARGETS = set("friend person someone him her them people classmate teacher professor partner wife husband boyfriend girlfriend family colleague boss".split())
DIRECT_PHRASES = (
    "want to kill", "going to kill", "i will kill", "i'll kill", "kill my friend",
    "kill someone", "kill him", "kill her", "kill them", "want to hurt",
    "going to hurt", "i will hurt", "i want to murder", "planning to kill",
    "how do i kill", "how to kill", "help me kill", "i might kill",
    "i am going to attack", "best way to kill", "ways to poison",
    "how to hurt someone", "help me attack"
)
CONTEXT_HINTS = (
    "in the mahabharata", "in the story", "fictional", "for my novel",
    "for a story", "historical account", "literature analysis", "translate the phrase",
    "meaning of the phrase", "in a video game", "historical question"
)
HISTORY_HINTS = ("what happened", "who killed", "why did", "historical", "character", "battle of", "describe the war")

def classify_safety(text):
    low = re.sub(r"\s+", " ", text.lower()).strip()
    words = set(tokenize(low))
    contextual = any(h in low for h in CONTEXT_HINTS)
    historical = contextual or any(h in low for h in HISTORY_HINTS)
    has_action = bool(words & VIOLENT_ACTIONS)
    direct = any(p in low for p in DIRECT_PHRASES)
    first_person = bool(re.search(r"\b(i|i'm|i am|i'll|i will|im|my)\b", low))
    target = bool(words & TARGETS)
    if not contextual and (direct or (first_person and has_action and target)):
        return "high_risk"
    if not contextual and any(p in low for p in ("how to kill", "how do i kill", "best way to kill", "how to hurt someone", "ways to poison")):
        return "high_risk"
    if has_action and historical:
        return "historical_or_fictional"
    return "normal"


def retrieve_evidence(query, k=3):
    query_lower = query.lower()
    query_words = set(tokenize(query_lower))

    # Map real-world wording to concepts in the knowledge base.
    concept_map = {
        "friend": ["trust", "trustworthy", "character"],
        "cheat": ["trust", "honesty", "truthful", "character"],
        "cheated": ["trust", "honesty", "truthful", "character"],
        "betray": ["trust", "honesty", "character"],
        "forgive": ["anger", "self-control", "reflection"],
        "forgiveness": ["anger", "self-control", "reflection"],
        "confront": ["honesty", "truthful advice", "consequences"],
        "lie": ["truthful", "honesty", "trust"],
        "lied": ["truthful", "honesty", "trust"],
        "angry": ["anger", "self-control", "reflection"],
        "revenge": ["anger", "self-control", "consequences"],
        "unfair": ["fairness", "justice"],
        "decision": ["ethical decision", "consequences"],
    }

    expanded_words = set(query_words)

    for keyword, related in concept_map.items():
        if keyword in query_lower:
            expanded_words.update(tokenize(" ".join(related)))

    scored = []

    for record in records:
        text = (
            str(record.get("principle", "")) + " " +
            str(record.get("text", ""))
        ).lower()

        doc_words = set(tokenize(text))

        # Score actual overlapping terms, not just TF-IDF.
        overlap = expanded_words.intersection(doc_words)

        score = (
            len(overlap) / len(expanded_words)
            if expanded_words else 0.0
        )

        # Add a small bonus for a direct principle-name match.
        principle_words = set(
            tokenize(record.get("principle", ""))
        )

        if expanded_words.intersection(principle_words):
            score += 0.10

        if score > 0:
            scored.append((score, record, overlap))

    scored.sort(key=lambda item: item[0], reverse=True)

    results = []

    for score, record, overlap in scored[:k]:
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
            "matched_terms": sorted(overlap)
        })

    return results


def make_recommendation(evidence):
    if not evidence or evidence[0]["similarity"] < 0.08:
        return "I could not find sufficiently relevant evidence in the current knowledge base to support a responsible recommendation. Please provide more context."
    top = evidence[0]
    return (f"The closest retrieved principle is “{top.get('principle', 'Relevant principle')}.” "
            f"{top.get('text', '')} This is a possible ethical perspective, not a definitive answer. "
            "Consider the circumstances, people affected, fairness, responsibility, and likely consequences.")

def init_db():
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                query_category TEXT NOT NULL, rating TEXT NOT NULL, evidence_ids TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS metrics (
                metric_key TEXT PRIMARY KEY, metric_value INTEGER NOT NULL)""")
    except Exception as e:
        print(f"Feedback database unavailable: {e}")

def metric(key):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""INSERT INTO metrics(metric_key, metric_value) VALUES (?, 1)
                ON CONFLICT(metric_key) DO UPDATE SET metric_value=metric_value+1""", (key,))
    except Exception as e:
        print(f"Metric update unavailable: {e}")

init_db()

@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status":"ok", "service":"DharmaDecision-AI",
                    "retrieval_method":"lightweight TF-IDF", "evidence_count":len(records),
                    "confidence_score":"disabled until validated"})

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    query = str(data.get("dilemma", "")).strip()
    if not query:
        return jsonify({"error":"Please enter an ethical dilemma."}), 400
    if len(query) > 3000:
        return jsonify({"error":"Please keep your question under 3000 characters."}), 400

    safety = classify_safety(query)
    metric("requests_total")
    if safety == "high_risk":
        metric("requests_high_risk")
        return jsonify({
            "dilemma": query, "intent":"potential immediate harm", "safety_status":"high_risk",
            "recommendation":(
                "Your message suggests someone may be at risk of being harmed. I can't help justify "
                "or plan violence. Please move away from your friend and from any weapons or objects "
                "you could use to hurt them. Contact someone you trust who can stay with you. If you "
                "think you might act soon or anyone is in immediate danger, contact local emergency "
                "services now. Are you with your friend right now, and do you feel you might act on this?"
            ),
            "confidence":None, "confidence_label":"Not applicable", "evidence":[],
            "message":"Safety response shown; ordinary evidence retrieval was skipped."
        })

    evidence = retrieve_evidence(query, 3)
    score = evidence[0]["similarity"] if evidence else 0.0
    relevant = score >= 0.08
    if not relevant:
        metric("low_relevance_requests")
    return jsonify({
        "dilemma":query,
        "intent":"historical_or_fictional" if safety == "historical_or_fictional" else "ethical_or_general_query",
        "safety_status":"normal",
        "recommendation":make_recommendation(evidence),
        "confidence":None,
        "confidence_label":"Not yet statistically validated",
        "relevance":round(float(score), 4),
        "relevance_status":"Potentially relevant" if relevant else "Insufficient evidence",
        "evidence":evidence if relevant else [],
        "message":None if relevant else "No sufficiently relevant evidence was found. No confidence percentage is provided."
    })

@app.route("/api/feedback", methods=["POST"])
def feedback():
    data = request.get_json(silent=True) or {}
    rating = str(data.get("rating", "")).strip().lower()
    if rating not in {"helpful", "not_helpful", "irrelevant", "unsafe"}:
        return jsonify({"error":"Invalid feedback rating."}), 400
    category = str(data.get("category", "general"))[:80]
    ids = data.get("evidence_ids", [])
    ids = [str(x)[:100] for x in ids[:10]] if isinstance(ids, list) else []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO feedback(created_at, query_category, rating, evidence_ids) VALUES (?, ?, ?, ?)",
                         (datetime.now(timezone.utc).isoformat(), category, rating, json.dumps(ids)))
    except Exception:
        return jsonify({"status":"not_saved", "message":"Feedback storage is unavailable in this deployment."}), 503
    return jsonify({"status":"recorded", "message":"Thank you. Feedback was recorded for future evaluation."})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
