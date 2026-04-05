import sqlite3

conn = sqlite3.connect("assistant.db")
c = conn.cursor()

try:
    c.execute("ALTER TABLE mail_memory ADD COLUMN reply_status TEXT DEFAULT 'drafted'")
    print("OK colonne ajoutée")
except:
    print("Déjà existante")

conn.commit()
conn.close()