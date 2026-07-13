import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
cur = conn.cursor()

# Use FTS separately to find matching part IDs, then join
keywords = ['stocks_api', 'search_sales_correlation', 'deliveryService', 'openCount']

for kw in keywords:
    try:
        cur.execute("""
        SELECT session_id, substr(body, 1, 400)
        FROM history_fts
        WHERE body MATCH ?
        AND time_created >= 1783305600000
        LIMIT 5
        """, (kw,))
        rows = cur.fetchall()
        if rows:
            print(f"\n=== '{kw}' in FTS ===")
            for sid, body in rows:
                print(f"  [{sid}]: {body[:250]}")
    except Exception as e:
        print(f"  Error for '{kw}': {e}")

# Check user messages with specific patterns in recent sessions
# Focus on sessions ses_0ad3e3ea0ffe, ses_0b73baeccffe, ses_0bca01dd6ffe
for sid in ['ses_0ad3e3ea0ffeEhqZmf9jEd5w4U', 'ses_0b73baeccffeO2CcGUOSCHpF1y', 'ses_0bca01dd6ffe6R4CmW2TsbFHOL']:
    cur.execute("""
    SELECT substr(json_extract(p.data, '$.text'), 1, 400) as txt
    FROM message m
    JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
    AND json_extract(m.data, '$.role') = 'user'
    AND json_extract(p.data, '$.type') = 'text'
    AND length(json_extract(p.data, '$.text')) > 15
    ORDER BY m.time_created
    """, (sid,))
    rows = cur.fetchall()
    if rows:
        print(f"\n=== User messages in {sid} ===")
        for (txt,) in rows:
            print(f"  {txt[:250]}")

conn.close()
