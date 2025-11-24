import os
import pandas as pd
import pymysql
from dotenv import load_dotenv
from urllib.parse import urlparse
from tqdm import tqdm  # ← 加這行！

load_dotenv()

MYSQL_URL = os.getenv("MYSQL_URL")
url = urlparse(MYSQL_URL)
MYSQL_HOST = url.hostname
MYSQL_PORT = url.port
MYSQL_USER = url.username
MYSQL_PASSWORD = url.password
MYSQL_DB = url.path[1:]

db = pymysql.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DB,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)

df = pd.read_csv("words.csv")
col_word = "單字" if "單字" in df.columns else "word"

missing = []
found = 0

with db.cursor() as cursor:
    # ⭐ 用 tqdm 包住 df.iterrows():
    for _, row in tqdm(df.iterrows(), total=len(df), desc="🔍 逐筆檢查 words 資料庫"):
        word = str(row[col_word]).strip()
        if not word:
            continue

        cursor.execute("SELECT id FROM words WHERE word=%s LIMIT 1", (word,))
        r = cursor.fetchone()

        if r:
            found += 1
        else:
            missing.append(word)

print("\n=== 結果 ===")
print("📊 CSV 總筆數 =", len(df))
print("📊 DB 有找到 =", found)
print("❌ DB 找不到的字 =", len(missing))
print("⚠️ 前 30 個 missing =", missing[:30])