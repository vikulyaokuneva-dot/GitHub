import sqlite3
conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for t in tables:
    cur.execute(f"PRAGMA table_info({t})")
    cols = [r[1] for r in cur.fetchall()]
    print(f"\n--- {t} columns: {cols}")

# List sessions from last 7 days
cur.execute("SELECT * FROM session ORDER BY rowid DESC LIMIT 15")
rows = cur.fetchall()
print("\n=== RECENT SESSIONS ===")
for row in rows:
    print(row)

conn.close()
