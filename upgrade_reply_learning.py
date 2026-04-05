import sqlite3

conn = sqlite3.connect("assistant.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS reply_learning_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_subject TEXT,
    mail_from TEXT,
    mail_body_preview TEXT,
    category TEXT,
    ai_reply TEXT,
    final_reply TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("Table reply_learning_memory prête.")