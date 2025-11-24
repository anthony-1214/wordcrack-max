import time
import pandas as pd
from pymongo import MongoClient
from openai import OpenAI

# 1. MongoDB 連線
MONGO_URL = "mongodb+srv://root:root1234@wordcrack.p6dqwbl.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URL)

db = client["wordcrack"]
words_col = db["words"]

# 2. OpenAI 初始化
client_ai = OpenAI(api_key="REMOVEDVE-8cCB5bYANg6KOY4tP6quuZbtXBBbN4Rtas129vhkICasaHFcOtMqpfYVCRKAlyvzT3BlbkFJRmdtyI9rQXtHbLzNYup8eznENAJ-sOTG3rTchqsZNL-AbUlXoUbB9FymA-GrZzOidusLS1kHkA")

# 3. 找出還沒有 embedding 的單字
words = list(words_col.find({"embedding": {"$exists": False}}))

print(f"📦 共有 {len(words)} 個單字需要產生 embedding")

for i, word in enumerate(words):
    text = word["單字"]

    try:
        # --- 產生向量 ---
        resp = client_ai.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        emb = resp.data[0].embedding

        # --- 寫回 MongoDB ---
        words_col.update_one(
            {"_id": word["_id"]},
            {"$set": {"embedding": emb}}
        )

        if i % 50 == 0:
            print(f"🔥 已完成 {i}/{len(words)}")

        time.sleep(0.1)  # 降低 API 壓力

    except Exception as e:
        print("❌ 錯誤：", e)
        continue

print("🎉 完成所有 embedding 寫入！")