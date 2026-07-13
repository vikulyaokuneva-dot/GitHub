import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
cur = conn.cursor()

# Get user messages from recent sessions to find rules/decisions
cur.execute("""
SELECT s.id, s.title, s.time_created, 
       json_extract(m.data, '$.role') as role,
       substr(json_extract(p.data, '$.text'), 1, 500) as text_preview
FROM session s
JOIN message m ON m.session_id = s.id
JOIN part p ON p.message_id = m.id
WHERE s.time_created >= 1783305600000
  AND json_extract(m.data, '$.role') = 'user'
  AND json_extract(p.data, '$.type') = 'text'
ORDER BY s.time_created DESC, m.time_created
LIMIT 30
""")

print("=== RECENT USER MESSAGES ===")
for row in cur.fetchall():
    sid, title, ts, role, text = row
    if text and len(text.strip()) > 5:
        print(f"\n[{sid}] {title}")
        print(f"  {text[:300]}")

conn.close()
