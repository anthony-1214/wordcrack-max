from pymongo import MongoClient

MONGO_URL = "mongodb+srv://root:root1234@wordcrack.p6dqwbl.mongodb.net/?retryWrites=true&w=majority"

client = MongoClient(MONGO_URL)

try:
    client.admin.command("ping")
    print("🎉 MongoDB 連線成功！")
except Exception as e:
    print("❌ 連線失敗：", e)