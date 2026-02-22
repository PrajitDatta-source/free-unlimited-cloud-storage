import sqlite3

conn = sqlite3.connect("vault.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    telegram_file_id TEXT,
    file_name TEXT,
    text_content TEXT,
    sent_ist TEXT NOT NULL,
    custom_ist TEXT,
    edited_ist TEXT,
    tags TEXT
)
""")

conn.commit()
conn.close()

print("Database initialized successfully.")