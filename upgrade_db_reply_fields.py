import sqlite3

DB_PATH = "assistant.db"

columns_to_add = [
    ("needs_reply", "INTEGER DEFAULT 0"),
    ("reply_urgency", "TEXT"),
    ("reply_reason", "TEXT"),
    ("suggested_reply_subject", "TEXT"),
    ("suggested_reply", "TEXT"),
    ("reply_confidence", "REAL"),
    ("reply_needs_review", "INTEGER DEFAULT 1"),
    ("last_reply_generated_at", "TEXT"),
    ("status", "TEXT DEFAULT 'new'"),
    ("assigned_to", "TEXT"),
    ("follow_up_needed", "INTEGER DEFAULT 0")
]

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

for column_name, column_type in columns_to_add:
    try:
        cursor.execute(f"ALTER TABLE mail_memory ADD COLUMN {column_name} {column_type}")
        print(f"Colonne ajoutée : {column_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"Colonne déjà existante : {column_name}")
        else:
            print(f"Erreur sur {column_name} : {e}")

conn.commit()
conn.close()

print("Mise à jour terminée.")