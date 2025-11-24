import pandas as pd
import pymysql
import math

# 1. Load CSV
df = pd.read_csv("words.csv")

# 2. Replace NaN with None (MySQL NULL)
df = df.where(pd.notnull(df), None)

# 3. Connect to Railway MySQL
conn = pymysql.connect(
    host="turntable.proxy.rlwy.net",
    user="root",
    password="NqgYVbDURUzcpNmeElgwHgjGptPsNfhq",
    database="railway",
    port=24042,
    charset="utf8mb4"
)

cursor = conn.cursor()

# 4. Batch insert (every 500 rows)
batch_size = 500
total = len(df)

sql = """
    INSERT INTO words (level, word, part_of_speech, chinese)
    VALUES (%s, %s, %s, %s)
"""

for i in range(0, total, batch_size):
    batch = df.iloc[i:i+batch_size]

    values = []
    for _, r in batch.iterrows():
        values.append((
            None if r["級別"] is None else str(r["級別"]),
            r["單字"],
            r["屬性"],
            r["中文"]
        ))

    cursor.executemany(sql, values)
    conn.commit()
    print(f"✅ 已匯入 {min(i+batch_size, total)} / {total} 筆")

cursor.close()
conn.close()

print("🎉 匯入完成！")