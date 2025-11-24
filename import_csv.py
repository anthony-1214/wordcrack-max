import csv
import pymysql

# 連線到 MySQL
db = pymysql.connect(
    host="localhost",
    user="root",
    password="root1234",   # 若你有密碼 → 填入
    database="wordcrack",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True
)

print("📚 開始匯入 CSV → MySQL...")

try:
    with db.cursor() as cursor:
        with open("words.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                sql = """
                    INSERT INTO words (level, word, part_of_speech, chinese)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    row["級別"],
                    row["單字"],
                    row["屬性"],
                    row["中文"]
                ))

    print("✅ 匯入成功！")

except Exception as e:
    print("❌ 匯入失敗：", e)
