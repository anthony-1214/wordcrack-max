"""
build_similar_words.py
根據 word_embeddings 建立 6000 字的相似字資料表 similar_words
- 支援 Railway MySQL
- 含 ETA 預估
- 每 50 字計算一次，避免暴衝占記憶體
"""

import os
import json
import time
import traceback
from urllib.parse import urlparse

import numpy as np
import pymysql
from dotenv import load_dotenv


# ============================================================
# 讀取 .env → MYSQL_URL + OPENAI_API_KEY（不需要 OpenAI）
# ============================================================
load_dotenv()

MYSQL_URL = os.getenv("MYSQL_URL", "")
if not MYSQL_URL:
    raise RuntimeError("❌ 缺少 MYSQL_URL，請在 .env 設定")

url = urlparse(MYSQL_URL)
MYSQL_HOST = url.hostname
MYSQL_PORT = url.port
MYSQL_USER = url.username
MYSQL_PASSWORD = url.password
MYSQL_DB = url.path[1:]

print("🔗 使用 Railway MySQL：")
print(f"   Host = {MYSQL_HOST}")
print(f"   Port = {MYSQL_PORT}")
print(f"   User = {MYSQL_USER}")
print(f"   DB   = {MYSQL_DB}\n")


# ============================================================
# DB Connect
# ============================================================
def get_db():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


try:
    db = get_db()
    print("✅ 成功連線 Railway MySQL\n")
except Exception:
    print("❌ MySQL 連線失敗")
    traceback.print_exc()
    raise SystemExit(1)


# ============================================================
# 建立 similar_words 資料表
# ============================================================
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS similar_words (
  id INT AUTO_INCREMENT PRIMARY KEY,
  word_id INT NOT NULL,
  similar_word VARCHAR(255) NOT NULL,
  score FLOAT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_word (word_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with db.cursor() as cursor:
    cursor.execute(CREATE_TABLE)

print("🧱 已確認資料表存在：similar_words\n")

# ============================================================
# 讀取所有 embedding
# ============================================================
print("📥 正在讀取 word_embeddings ...")

with db.cursor() as cursor:
    cursor.execute("""
        SELECT w.id, w.word, w.chinese, e.embedding
        FROM words w
        JOIN word_embeddings e ON w.id = e.word_id
        ORDER BY w.id
    """)
    rows = cursor.fetchall()

if not rows:
    raise RuntimeError("❌ word_embeddings 沒有資料，請先跑 embed_words.py")

print(f"📦 共讀取 {len(rows)} 筆 embedding\n")

# 轉成 numpy
WORDS = []
EMBS = []

for r in rows:
    WORDS.append({
        "id": r["id"],
        "word": r["word"],
        "chinese": r["chinese"],
    })
    EMBS.append(np.array(json.loads(r["embedding"]), dtype=np.float32))

EMBS = np.vstack(EMBS)   # shape (6009, 1536)

print("📌 Embedding 轉換為 numpy 完成\n")


# ============================================================
# 計算相似度（cosine similarity）
# ============================================================
def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ============================================================
# 開始逐字產生相似字
# ============================================================
TOTAL = len(WORDS)
BATCH = 50   # 每 50 字 commit 一次

print("🚀 開始建立相似字資料（similar_words） ...\n")

start_time = time.time()
processed = 0

with db.cursor() as cursor:
    # 清空舊資料
    cursor.execute("DELETE FROM similar_words")

    for idx, base in enumerate(WORDS):
        base_vec = EMBS[idx]

        scores = []

        # 計算與所有字相似度
        for j in range(TOTAL):
            if j == idx:
                continue
            score = cosine(base_vec, EMBS[j])
            scores.append((WORDS[j]["word"], score))

        # 排序取前 5
        scores.sort(key=lambda x: x[1], reverse=True)
        top5 = scores[:5]

        # 寫入 DB
        for w, sc in top5:
            cursor.execute(
                """
                INSERT INTO similar_words (word_id, similar_word, score)
                VALUES (%s, %s, %s)
                """,
                (base["id"], w, sc)
            )

        processed += 1

        # ===== 進度與 ETA =====
        elapsed = time.time() - start_time
        speed = processed / elapsed
        remain = TOTAL - processed
        eta = remain / speed if speed > 0 else 9999

        print(f"✅ {processed}/{TOTAL}  ({processed/TOTAL*100:.2f}%) | ETA：約 {eta/60:.1f} 分鐘")

print("\n🎉 全部完成！已成功建立 6000 筆相似字資料！")
db.close()