"""
embed_words.py
讀取 words.csv → 呼叫 OpenAI Embeddings → 寫入 MySQL 資料表 word_embeddings

前置：
1. pip install openai pymysql python-dotenv pandas
2. 檔案結構（例）：
   backend/
     ├─ app.py
     ├─ embed_words.py   ← 放這個
     └─ words.csv        ← 你的 6000 字 CSV

3. .env 需要：
   OPENAI_API_KEY=你的金鑰
   MYSQL_HOST=localhost
   MYSQL_USER=root
   MYSQL_PASSWORD=（你的密碼）
   MYSQL_DB=wordcrack
"""

import os
import json
import time
import traceback

import pandas as pd
import pymysql
from dotenv import load_dotenv
from openai import OpenAI

# -----------------------------
# 讀取 .env
# -----------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "wordcrack")

if not OPENAI_API_KEY:
    raise RuntimeError("❌ 沒有找到 OPENAI_API_KEY，請在 .env 裡設定")

client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# 連線 MySQL
# -----------------------------
try:
    db = pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,  # 批次 commit
    )
    print(f"✅ 已連線 MySQL：{MYSQL_HOST} / DB={MYSQL_DB}")
except Exception:
    print("❌ 無法連線 MySQL：")
    traceback.print_exc()
    raise SystemExit(1)

# -----------------------------
# 建立 word_embeddings 資料表
# -----------------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS word_embeddings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  word_id INT NOT NULL,
  word VARCHAR(255) NOT NULL,
  embedding JSON NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_word_id (word_id),
  CONSTRAINT fk_word_embeddings_word
    FOREIGN KEY (word_id) REFERENCES words(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with db.cursor() as cursor:
    cursor.execute(CREATE_TABLE_SQL)
db.commit()
print("✅ 已確認建立資料表：word_embeddings")

# -----------------------------
# 讀取 words.csv
# -----------------------------
CSV_PATH = "words.csv"

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"❌ 找不到 {CSV_PATH}，請確認檔案路徑")

df = pd.read_csv(CSV_PATH)

# 你的欄位名稱：級別, 單字, 屬性, 中文
# 做個保險：如果未來你改成英文欄位也能用
col_level = "級別" if "級別" in df.columns else "level"
col_word = "單字" if "單字" in df.columns else "word"
col_pos = "屬性" if "屬性" in df.columns else "part_of_speech"
col_cn = "中文" if "中文" in df.columns else "chinese"

print(f"📄 CSV 總列數：{len(df)}")
print("📌 欄位對應：", col_level, col_word, col_pos, col_cn)

# -----------------------------
# 準備要做 embedding 的單字清單
# -----------------------------
to_embed = []

with db.cursor() as cursor:
    for _, row in df.iterrows():
        word = str(row[col_word]).strip()
        if not word:
            continue

        # 找對應 words 表的 id
        cursor.execute(
            "SELECT id FROM words WHERE word = %s LIMIT 1",
            (word,),
        )
        r = cursor.fetchone()
        if not r:
            # 如果 DB 裡沒有這個 word，就跳過（你也可以選擇印出來）
            # print(f"⚠️ DB 中找不到單字：{word}")
            continue

        word_id = r["id"]

        # 檢查是否已經有 embedding，避免重複
        cursor.execute(
            "SELECT id FROM word_embeddings WHERE word_id = %s LIMIT 1",
            (word_id,),
        )
        exists = cursor.fetchone()
        if exists:
            # print(f"⏭ 已有 embedding，略過：{word}")
            continue

        to_embed.append(
            {
                "word_id": word_id,
                "word": word,
            }
        )

print(f"🧮 準備產生 embeddings 的單字數量：{len(to_embed)}")

if not to_embed:
    print("✅ 看起來所有單字都已經有 embeddings 了，結束。")
    db.close()
    raise SystemExit(0)

# -----------------------------
# 呼叫 OpenAI Embeddings 批次寫入
# -----------------------------
BATCH_SIZE = 100
MODEL_NAME = "text-embedding-3-small"

total = len(to_embed)
processed = 0

try:
    with db.cursor() as cursor:
        for start in range(0, total, BATCH_SIZE):
            batch = to_embed[start : start + BATCH_SIZE]
            texts = [item["word"] for item in batch]

            print(f"🚀 呼叫 embeddings：{start+1} ~ {start+len(batch)} / {total}")

            # 呼叫 OpenAI Embeddings
            resp = client.embeddings.create(
                model=MODEL_NAME,
                input=texts,
            )

            # resp.data[i].embedding 是一個 float list
            for item, emb_obj in zip(batch, resp.data):
                embedding = emb_obj.embedding  # list[float]
                cursor.execute(
                    """
                    INSERT INTO word_embeddings (word_id, word, embedding)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      embedding = VALUES(embedding)
                    """,
                    (
                        item["word_id"],
                        item["word"],
                        json.dumps(embedding),
                    ),
                )

            db.commit()
            processed += len(batch)
            print(f"✅ 已寫入 {processed} / {total} 筆")

            # 避免太快（可調整或註解掉）
            time.sleep(0.2)

except Exception:
    print("❌ 產生 embeddings 時發生錯誤，準備回滾交易")
    db.rollback()
    traceback.print_exc()
finally:
    db.close()
    print("🔚 結束，資料庫連線已關閉")
