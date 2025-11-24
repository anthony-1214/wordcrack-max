import pandas as pd
import pymysql

# 1. 讀取 CSV
df = pd.read_csv("words.csv")  # 你上傳的檔案

# 2. Railway MySQL 連線資訊
conn = pymysql.connect(
    host="turntable.proxy.rlwy.net",
    user="root",
    password="NqgYVbDURUzcpNmeElgwHgjGptPsNfhq",  # 你自己的密碼
    database="railway",
    port=24042,
    charset="utf8mb4"
)

cursor = conn.cursor()

# 3. 匯入每一筆資料
count = 0
for _, row in df.iterrows():
    sql = """
        INSERT INTO words (level, word, part_of_speech, chinese)
        VALUES (%s, %s, %s, %s)
    """
    cursor.execute(sql, (
        str(row["級別"]),
        row["單字"],
        row["屬性"],
        row["中文"]
    ))
    count += 1

conn.commit()
cursor.close()
conn.close()

print(f"✅ 匯入完成！共新增 {count} 筆單字資料")