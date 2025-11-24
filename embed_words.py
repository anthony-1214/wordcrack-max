"""
embed_words.py — FINAL VERSION
✔ tqdm 進度條
✔ ETA 預估
✔ API 自動重試
✔ Railway MySQL URL 支援
"""

import os
import json
import time
from urllib.parse import urlparse

import pandas as pd
import pymysql
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

# ==============================
# 讀取環境變數
# ==============================
load_dotenv()

MYSQL_URL = os.getenv("MYSQL_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not MYSQL_URL:
    raise RuntimeError("❌ 缺少 MYSQL_URL，請在 .env 設定")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ 缺少 OPENAI_API_KEY，請在 .env 設定")

print("🔍 解析 MySQL_URL =", MYSQL_URL)

url = urlparse(MYSQL_URL)
MYSQL_HOST = url.hostname
MYSQL_PORT = url.port
MYSQL_USER = url.username
MYSQL_PASSWORD = url.password
MYSQL_DB = url.path[1:]

print(f"🧭 Host={MYSQL_HOST}, Port={MYSQL_PORT}, User={MYSQL_USER}, DB={MYSQL_DB}")

client = OpenAI(api_key=OPENAI_API_KEY)

# ==============================
# MySQL 連線
# ==============================
def db_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )

db = db_conn()
print("✅ 成功連線 Railway MySQL")

# ==============================
# 建立 word_embeddings 資料表
# ==============================
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS word_embeddings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    word_id INT NOT NULL,
    word VARCHAR(255) NOT NULL,
    embedding JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_word_id (word_id),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with db.cursor() as cursor:
    cursor.execute(TABLE_SQL)
db.commit()
print("✅ 已確認 word_embeddings 資料表存在")

# ==============================
# 讀 CSV
# ==============================
df = pd.read_csv("words.csv")
print(f"📄 CSV 讀取成功：共 {len(df)} 筆")

col_word = "單字" if "單字" in df.columns else "word"

# ==============================
# 取得 DB 目前有多少資料
# ==============================
with db.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) AS c FROM words")
    words_count = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM word_embeddings")
    embed_count = cursor.fetchone()["c"]

print(f"📊 words 表 = {words_count} 筆")
print(f"📊 word_embeddings 表 = {embed_count} 筆\n")

# ==============================
# 找需要產生 embedding 的單字 (含 tqdm)
# ==============================
to_embed = []

with db.cursor() as cursor:
    for _, row in tqdm(df.iterrows(), total=len(df), desc="🔍 檢查需要 embedding 的單字"):
        word = str(row[col_word]).strip()
        if not word:
            continue

        cursor.execute("SELECT id FROM words WHERE word=%s", (word,))
        w = cursor.fetchone()
        if not w:
            continue

        word_id = w["id"]

        cursor.execute("SELECT id FROM word_embeddings WHERE word_id=%s", (word_id,))
        if cursor.fetchone():
            continue

        to_embed.append({"word": word, "word_id": word_id})

print(f"\n🧮 總共需要 embedding 的單字：{len(to_embed)}")

if len(to_embed) == 0:
    print("👍 所有 embedding 都已存在，不需跑！")
    db.close()
    exit(0)

# ==============================
# 開始產生 embeddings（含 ETA）
# ==============================
MODEL = "text-embedding-3-small"
BATCH = 50
total = len(to_embed)
processed = 0
start = time.time()

def eta(start, done, total):
    if done == 0:
        return "計算中..."
    speed = done / (time.time() - start)
    left = (total - done) / speed
    return f"{left:.1f} 秒"

with db.cursor() as cursor:
    for i in range(0, total, BATCH):
        batch = to_embed[i:i+BATCH]
        words_list = [x["word"] for x in batch]

        print(f"\n🚀 Embedding {i+1} ~ {i+len(batch)} / {total}")
        print("⏳ ETA:", eta(start, processed, total))

        # ====== 呼叫 API（最多重試 3 次） ======
        for retry in range(3):
            try:
                resp = client.embeddings.create(
                    model=MODEL,
                    input=words_list
                )
                break
            except Exception as e:
                print(f"⚠️ API 錯誤，重試 {retry+1}/3：", e)
                time.sleep(2)
        else:
            raise RuntimeError("❌ API 重試 3 次仍失敗，請檢查網路或 API Key")

        # ====== 寫入 DB ======
        for item, emb in zip(batch, resp.data):
            cursor.execute(
                """
                INSERT INTO word_embeddings (word_id, word, embedding)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE embedding=VALUES(embedding)
                """,
                (item["word_id"], item["word"], json.dumps(emb.embedding)),
            )

        db.commit()

        processed += len(batch)
        percent = processed / total * 100
        print(f"✅ 進度：{processed}/{total} ({percent:.2f}%)")

db.close()
print("\n🎉 全部 embeddings 生成完畢！")