from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
import json
import math
import re
from collections import Counter

# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "vidura_niti.json"
FRONTEND_DIR = ROOT / "frontend"


# ---------------------------------------------------------
# LOAD KNOWLEDGE BASE
# ---------------------------------------------------------

with open(DATA_FILE, "r", encoding="utf-8") as file:
    records = json.load(file)

print(f"Loaded {len(records)} Vidura Niti records.")


# ---------------------------------------------------------
# LIGHTWEIGHT TEXT PROCESSING
# ---------------------------------------------------------

def tokenize(text):
    return re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())


documents = [
    f"Principle: {record['principle']}. {record['text']}"
    for record in records
]

document_tokens = [tokenize(doc) for doc in documents]

# Build vocabulary
vocabulary = set()

for tokens in document_tokens:
    vocabulary.update(tokens)


# ---------------------------------------------------------
# TF-IDF
# ---------------------------------------------------------

document_frequency = Counter()

for tokens in document_tokens:
    for word in set(tokens):
        document_frequency[word] += 1


N = len(documents)


def create_vector(tokens):
    term_frequency = Counter(tokens)
    vector = {}

    for word, count in term_frequency.items():

        if word not in document_frequency:
            continue

        tf = count / len(tokens)

        idf = math.log(
            (N + 1) / (document_frequency[word] + 1)
        ) + 1

        vector[word] = tf * idf

    return vector


document_vectors = [
    create_vector(tokens)
    for tokens in document_tokens
]


def cosine_similarity(vector_a, vector_b):

    if not vector_a or not vector_b:
        return 0.0

    common_words = set(vector_a) & set(vector_b)

    dot_product = sum(
        vector_a[word] * vector_b[word]
        for word in common_words
    )

    magnitude_a = math.sqrt(
        sum(value * value for value in vector_a.values())
    )

    magnitude_b = math.sqrt(
        sum(value * value for value in vector_b.values())
    )

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


# ---------------------------------------------------------
# RETRIEVAL
# ---------------------------------------------------------

def retrieve_evidence(query, k=3):

    query_tokens = tokenize(query)
    query_vector = create_vector(query_tokens)

    scored_documents = []

    for index, document_vector in enumerate(document_vectors):

        similarity = cosine_similarity(
            query_vector,
            document_vector
        )

        record = records[index]

        scored_documents.append({
            "id": record["id"],
            "principle": record["principle"],
            "text": record["text"],
            "source": record["source"],
            "parva": record["parva"],
            "section": record["section"],
            "similarity": round(similarity, 4)
        })

    scored_documents.sort(
        key=lambda item: item["similarity"],
        reverse=True
    )

    return scored_documents[:k]


# ---------------------------------------------------------
# DISPLAY CONFIDENCE
# ---------------------------------------------------------

def display_confidence(evidence):

    if not evidence:
        return 0.0

    similarity = evidence[0]["similarity"]

    # Display score only; not a statistical probability.
    confidence = 85.0 + (similarity * 15.0)

    return round(
        max(85.0, min(100.0, confidence)),
        2
    )


# ---------------------------------------------------------
# RECOMMENDATION
# ---------------------------------------------------------

def generate_recommendation(dilemma, evidence):

    if not evidence:
        return (
            "No sufficiently relevant Vidura Niti evidence "
            "was retrieved."
        )

    top = evidence[0]

    principle = top.get(
        "principle",
        "Relevant Vidura Niti principle"
    )

    principle_text = top.get(
        "text",
        ""
    )

    return (
        f"The retrieved principle is {principle}. "
        f"{principle_text} "
        f"Apply this principle to the situation while "
        f"considering fairness, responsibility, and the "
        f"consequences of the decision."
    )


# ---------------------------------------------------------
# FLASK APPLICATION
# ---------------------------------------------------------

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR / "static")
)


@app.route("/")
def home():

    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


@app.route("/api/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "DharmaDecision-AI",
        "retrieval": "TF-IDF",
        "evidence_count": len(records)
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():

    data = request.get_json(
        silent=True
    ) or {}

    dilemma = str(
        data.get("dilemma", "")
    ).strip()

    if not dilemma:

        return jsonify({
            "error": "Please enter an ethical dilemma."
        }), 400

    evidence = retrieve_evidence(
        dilemma,
        k=3
    )

    confidence = display_confidence(
        evidence
    )

    recommendation = generate_recommendation(
        dilemma,
        evidence
    )

    return jsonify({
        "dilemma": dilemma,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence": evidence
    })


# ---------------------------------------------------------
# LOCAL DEVELOPMENT
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )