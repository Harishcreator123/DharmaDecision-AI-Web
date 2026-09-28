from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
import json

import faiss
import torch
from transformers import AutoTokenizer, AutoModel


# --------------------------------------------------
# PROJECT PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

DATA_FILE = ROOT / "data" / "vidura_niti.json"
FRONTEND_DIR = ROOT / "frontend"


# --------------------------------------------------
# LOAD VIDURA NITI DATA
# --------------------------------------------------

with open(DATA_FILE, "r", encoding="utf-8") as file:
    records = json.load(file)

print(f"Loaded {len(records)} Vidura Niti records.")


# --------------------------------------------------
# LOAD MINI-LM MODEL
# --------------------------------------------------

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

print("Loading MiniLM model...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)

model.eval()

print("MiniLM model loaded successfully.")


# --------------------------------------------------
# CREATE TEXT DOCUMENTS
# --------------------------------------------------

documents = [
    (
        f"Principle: {record['principle']}. "
        f"{record['text']}"
    )
    for record in records
]


# --------------------------------------------------
# EMBEDDING FUNCTION
# --------------------------------------------------

def create_embeddings(texts):

    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        return_tensors="pt"
    )

    with torch.no_grad():

        output = model(**encoded)

    token_embeddings = output.last_hidden_state

    attention_mask = encoded["attention_mask"]

    mask = attention_mask.unsqueeze(-1).expand(
        token_embeddings.size()
    ).float()

    summed = torch.sum(
        token_embeddings * mask,
        dim=1
    )

    counts = torch.clamp(
        mask.sum(dim=1),
        min=1e-9
    )

    embeddings = summed / counts

    embeddings = torch.nn.functional.normalize(
        embeddings,
        p=2,
        dim=1
    )

    return embeddings.cpu().numpy().astype("float32")


# --------------------------------------------------
# CREATE FAISS INDEX
# --------------------------------------------------

print("Creating embeddings...")

embeddings = create_embeddings(documents)

index = faiss.IndexFlatIP(
    embeddings.shape[1]
)

index.add(embeddings)

print(
    f"FAISS index created with {len(records)} documents."
)


# --------------------------------------------------
# RETRIEVE EVIDENCE
# --------------------------------------------------

def retrieve_evidence(query, k=3):

    query_embedding = create_embeddings([query])

    scores, indices = index.search(
        query_embedding,
        min(k, len(records))
    )

    results = []

    for rank, idx in enumerate(
        indices[0],
        start=1
    ):

        record = records[int(idx)]

        results.append({
            "rank": rank,
            "id": record["id"],
            "principle": record["principle"],
            "text": record["text"],
            "source": record["source"],
            "parva": record["parva"],
            "section": record["section"],
            "similarity": round(
                float(scores[0][rank - 1]),
                4
            )
        })

    return results


# --------------------------------------------------
# DISPLAY CONFIDENCE
# --------------------------------------------------

def display_confidence(evidence):

    if not evidence:
        return 0.0

    similarity = evidence[0]["similarity"]

    similarity = max(
        -1.0,
        min(1.0, similarity)
    )

    normalized = (
        (similarity + 1.0) / 2.0
    )

    confidence = 85.0 + (
        normalized * 15.0
    )

    return round(
        max(85.0, min(100.0, confidence)),
        2
    )


# --------------------------------------------------
# RECOMMENDATION
# --------------------------------------------------

def generate_recommendation(dilemma, evidence):

    if not evidence:
        return "No sufficiently relevant Vidura Niti evidence was retrieved."

    top = evidence[0]

    principle = (
        top.get("principle")
        or "Relevant Vidura Niti principle"
    )

    principle_text = (
        top.get("text")
        or ""
    )

    return (
        f"The retrieved principle is {principle}. "
        f"{principle_text} "
        f"Apply this principle to the situation while considering "
        f"fairness, responsibility, and the consequences of the decision."
    )


# --------------------------------------------------
# FLASK
# --------------------------------------------------

app = Flask(
    __name__,
    static_folder=str(
        FRONTEND_DIR / "static"
    )
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
        "evidence_count": len(records)
    })


@app.route(
    "/api/analyze",
    methods=["POST"]
)
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


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )