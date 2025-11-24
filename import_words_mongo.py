import pandas as pd
from pymongo import MongoClient

# 1. MongoDB Atlas 連線
MONGO_URL = "mongodb+srv://root:root1234@wordcrack.p6dqwbl.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URL)

db = client["wordcrack"]
words_col = db["words"]

print("📦 已連線 MongoDB，準備匯入資料...")

# 2. 讀取 CSV
df = pd.read_csv("words.csv")

# 3. 將 DataFrame 轉成 MongoDB 能接受的 dict
records = df.to_dict(orient="records")

# 4. 批次匯入（最快）
result = words_col.insert_many(records)

print(f"✅ 匯入完成！共新增 {len(result.inserted_ids)} 筆單字資料")