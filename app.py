import os
import json
import traceback
import random

from flask import Flask, jsonify, request
from flask_cors import CORS
import pymysql
import numpy as np
from openai import OpenAI

# =====================================================
# 讀取 .env（本機開發用；Render 上用環境變數）
# =====================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "wordcrack")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)
CORS(app)


# =====================================================
# ⭐ 每次 API 呼叫建立自己的 DB 連線（適合 Render）
# =====================================================
def get_db():
    return pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@app.route("/api/health")
def health():
    try:
        db = get_db()
        db.close()
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False})


# =====================================================
# ⭐ 取得全部 6000 單字
# =====================================================
@app.route("/api/words", methods=["GET"])
def get_words():
    try:
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, level, word, part_of_speech, chinese
                FROM words
                ORDER BY word ASC;
                """
            )
            data = cursor.fetchall()
        db.close()
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# ⭐ 搜尋（英文 / 中文）
# =====================================================
@app.route("/api/search", methods=["GET"])
def search_words():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    try:
        db = get_db()
        like = f"%{q}%"

        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, level, word, part_of_speech, chinese
                FROM words
                WHERE word LIKE %s
                   OR chinese LIKE %s
                   OR part_of_speech LIKE %s
                ORDER BY word ASC
                LIMIT 200;
                """,
                (like, like, like),
            )

            data = cursor.fetchall()

        db.close()
        return jsonify(data)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# ⭐ 依字母開頭篩選
# =====================================================
@app.route("/api/words/by_letter/<letter>", methods=["GET"])
def by_letter(letter):
    try:
        db = get_db()
        letter = letter.lower()

        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, level, word, part_of_speech, chinese
                FROM words
                WHERE LOWER(word) LIKE %s
                ORDER BY word ASC;
                """,
                (letter + "%",),
            )

            data = cursor.fetchall()

        db.close()
        return jsonify(data)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# ⭐ 依 Level 篩選
# =====================================================
@app.route("/api/words/by_level/<int:level>", methods=["GET"])
def by_level(level):
    try:
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, level, word, part_of_speech, chinese
                FROM words
                WHERE level = %s
                ORDER BY word ASC;
                """,
                (level,),
            )
            data = cursor.fetchall()
        db.close()
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# ⭐ AI 相似字（GPT）
# =====================================================
@app.route("/api/words/similar", methods=["POST"])
def get_similar_words():
    try:
        keyword = request.json.get("word", "").strip()
        if not keyword:
            return jsonify({"error": "missing word"}), 400

        prompt = f"""
        請列出 5 個與「{keyword}」語意相近的英文單字，
        回傳格式為純 JSON，例如：
        ["skill","talent","ability"]
        """

        ai_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        raw = ai_res.choices[0].message.content.strip()

        try:
            words = json.loads(raw)
        except Exception:
            words = []

        db = get_db()
        results = []

        with db.cursor() as cursor:
            for w in words:
                cursor.execute(
                    """
                    SELECT word, chinese, part_of_speech, level
                    FROM words
                    WHERE word = %s LIMIT 1
                    """,
                    (w,),
                )
                row = cursor.fetchone()

                results.append(
                    row
                    or {
                        "word": w,
                        "chinese": "(資料庫無此字)",
                        "part_of_speech": "",
                        "level": "",
                    }
                )

        db.close()
        return jsonify(results)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# ⭐ Embedding 相似字（資料庫）
# =====================================================
@app.route("/api/words/similar_db", methods=["POST"])
def similar_from_db():
    try:
        word = request.json.get("word", "").strip()
        if not word:
            return jsonify({"error": "missing word"}), 400

        db = get_db()

        # 取得目標單字 embedding
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT embedding FROM word_embeddings
                WHERE word = %s LIMIT 1
                """,
                (word,),
            )
            base = cursor.fetchone()

        if not base:
            db.close()
            return jsonify({"error": "no embedding"}), 404

        query_vec = np.array(json.loads(base["embedding"]))

        # 取得全部 embedding
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT w.word, w.chinese, e.embedding
                FROM words w
                JOIN word_embeddings e ON w.word = e.word
                """
            )
            rows = cursor.fetchall()

        db.close()

        # 計算 cosine similarity
        results = []
        for r in rows:
            vec = np.array(json.loads(r["embedding"]))
            sim = float(
                np.dot(query_vec, vec)
                / (np.linalg.norm(query_vec) * np.linalg.norm(vec))
            )

            results.append({"word": r["word"], "chinese": r["chinese"], "score": sim})

        # 排除自己 + 取前五名
        final = [
            x for x in sorted(results, key=lambda x: x["score"], reverse=True) if x["word"] != word
        ][:5]

        return jsonify(final)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# ⭐ AI 例句（多樣化 + JSON 修復 + fallback）
# =====================================================
@app.route("/api/words/sentence", methods=["POST"])
def get_sentence():
    try:
        word = request.json.get("word", "").strip()
        if not word:
            return jsonify({"error": "missing word"}), 400

        prompt = f"""
        請為英文單字「{word}」生成一個自然、生活化且至少 10 個字以上的英文例句。
        條件如下：
        - 不得使用 "I saw the word" 類句型
        - 不得提到「這個單字」
        - 語氣自然、像真人會講的
        - 回傳純 JSON：
        {{
            "sentence": "英文例句",
            "translation": "中文翻譯"
        }}
        """

        ai_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        raw = ai_res.choices[0].message.content.strip()

        # 嘗試解析 JSON
        try:
            result = json.loads(raw)
            if isinstance(result, dict) and "sentence" in result:
                return jsonify(result)
        except Exception:
            pass

        # fallback：10 個自然句子（隨機選一個）
        fallback_pool = [
            (
                f"I used the word '{word}' while writing my English journal yesterday.",
                f"我昨天寫英文日記時用了 {word}。",
            ),
            (
                f"My teacher told us to practice using '{word}' in daily conversations.",
                f"老師鼓勵我們在日常對話中多使用 {word}。",
            ),
            (
                f"I finally understood how to use '{word}' after reading several examples.",
                f"看了幾個例句後，我終於知道 {word} 怎麼用了。",
            ),
            (
                f"My friend mentioned '{word}' during our discussion, and it caught my attention.",
                f"朋友在討論時用到 {word}，讓我很有印象。",
            ),
            (
                f"I practiced '{word}' by making sentences during my bus ride to school.",
                f"我在搭車去學校時用 {word} 造句練習。",
            ),
            (
                f"I heard '{word}' in a podcast and looked it up afterward.",
                f"我在 podcast 裡聽到 {word}，所以去查了它的意思。",
            ),
            (
                f"The article I read last night used '{word}' several times.",
                f"我昨天看的文章裡多次用到 {word}。",
            ),
            (
                f"I tried to memorize '{word}' by connecting it to real-life situations.",
                f"我把 {word} 和生活情境連結來記它。",
            ),
            (
                f"I recognized '{word}' on a sign when I was traveling last week.",
                f"上週旅行時我在路標上看到 {word}，覺得很驚喜。",
            ),
            (
                f"I reviewed '{word}' again while using my vocabulary app this morning.",
                f"我今天早上用單字 app 時又複習到 {word}。",
            ),
        ]

        sen, zh = random.choice(fallback_pool)

        return jsonify({"sentence": sen, "translation": zh})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================
# 🚀 啟動伺服器（本機用；Render 會用 gunicorn app:app）
# =====================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    print(f"\n🚀 後端啟動成功！ Port = {port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)
