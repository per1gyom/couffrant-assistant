import sqlite3

conn = sqlite3.connect("assistant.db")
cursor = conn.cursor()

cursor.execute("""
SELECT display_title, needs_reply, suggested_reply
FROM mail_memory
ORDER BY id DESC
LIMIT 20
""")

rows = cursor.fetchall()

for row in rows:
    print("\n---")
    print("Titre:", row[0])
    print("Needs reply:", row[1])
    print("Réponse:", row[2])

conn.close()