import os
import json
import traceback
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from openai import OpenAI

# =====================================================
# 載入 .env
# =====================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# =====================================================
# MongoDB 連線
# =====================================================
MONGO_URL = os.getenv("MONGO_URL")
if not MONGO_URL:
    raise RuntimeError("❌ 請在 .env 設定 MONGO_URL")

mongo_client = MongoClient(MONGO_URL)
db = mongo_client["wordcrack"]
words_col = db["words"]  # 你的 6009 單字 + embedding

# =====================================================
# OpenAI
# =====================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Flask
app = Flask(__name__)
CORS(app)


# =====================================================
# Health Check（MongoDB）
# =====================================================
@app.route("/api/health")
def health():
    try:
        mongo_client.admin.command("ping")
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False})


# =====================================================
# Helper：把 Mongo 格式轉成前端格式
# =====================================================
def doc_to_dict(doc):
    return {
        "id": str(doc.get("_id")),
        "word": doc.get("單字") or doc.get("word"),
        "chinese": doc.get("中文") or "",
        "part_of_speech": doc.get("屬性") or "",
        "level": doc.get("級別") or "",
    }


# =====================================================
# ⭐ 取得全部單字
# =====================================================
@app.route("/api/words")
def get_words():
    cursor = words_col.find({}, {"embedding": 0}).sort("單字", 1)
    return jsonify([doc_to_dict(x) for x in cursor])


# =====================================================
# ⭐ 搜尋單字
# =====================================================
@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    regex = {"$regex": q, "$options": "i"}

    cursor = words_col.find(
        {"$or": [{"單字": regex}, {"中文": regex}, {"屬性": regex}]},
        {"embedding": 0}
    ).sort("單字", 1)

    return jsonify([doc_to_dict(x) for x in cursor])


# =====================================================
# ⭐ Vector Search（重點）
# =====================================================
@app.route("/api/words/similar_db", methods=["POST"])
def similar_db():
    payload = request.get_json(force=True)
    word = payload.get("word", "").strip()
    top_k = payload.get("top_k", 5)

    if not word:
        return jsonify([])

    # 1. 找到該字本身的 embedding
    base = words_col.find_one({"單字": word})
    if not base or "embedding" not in base:
        return jsonify([])

    query_vec = base["embedding"]

    # 2. MongoDB Atlas Vector Search Pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "embedding_index",
                "path": "embedding",
                "queryVector": query_vec,
                "numCandidates": 200,
                "limit": top_k + 1
            }
        },
        {
            "$project": {
                "單字": 1,
                "中文": 1,
                "屬性": 1,
                "級別": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]

    docs = list(words_col.aggregate(pipeline))

    # 去掉自己
    results = []
    for d in docs:
        if d.get("單字") == word:
            continue

        results.append({
            "word": d.get("單字"),
            "chinese": d.get("中文", ""),
            "part_of_speech": d.get("屬性", ""),
            "level": d.get("級別", ""),
            "score": d.get("score")
        })

        if len(results) >= top_k:
            break

    return jsonify(results)


# =====================================================
# ⭐ 例句（OpenAI）
# =====================================================
@app.route("/api/words/sentence", methods=["POST"])
def sentence():
    data = request.get_json(force=True)
    word = data.get("word", "").strip()

    if not OPENAI_API_KEY or not word:
        return jsonify({
            "sentence": f"I saw the word '{word}' today.",
            "translation": f"我今天看到了「{word}」。"
        })

    prompt = f"""
    為單字「{word}」寫一個自然、生活化的英文例句（至少 10 字）。
    回傳 JSON 格式：
    {{
        "sentence": "...",
        "translation": "..."
    }}
    """

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = res.choices[0].message.content.strip()

    try:
        return jsonify(json.loads(raw))
    except:
        return jsonify({
            "sentence": f"I used the word '{word}' today.",
            "translation": f"我今天用了「{word}」。"
        })


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(port=5001, debug=True)