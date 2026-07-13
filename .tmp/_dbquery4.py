import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
cur = conn.cursor()

# Search for key user statements in recent sessions
keywords = ['всегда', 'никогда', 'нужно', 'правило', 'не смешивай', 'decision', 'decided']

for kw in keywords:
    cur.execute("""
    SELECT h.session_id, s.title, h.body
    FROM history_fts h
    JOIN session s ON s.id = h.session_id
    WHERE h.body MATCH ? AND h.kind = 'text'
    AND s.time_created >= 1783305600000
    LIMIT 5
    """, (kw,))
    rows = cur.fetchall()
    if rows:
        print(f"\n=== '{kw}' matches ===")
        for sid, title, body in rows:
            print(f"  [{sid}] {title}: {body[:200]}")

# Also search for specific durable knowledge patterns
for kw in ['stocks_api_deprecated', 'search_sales_correlation', 'rendering', 'PDF rendering', 'open_count', 'impressions', 'deliveryService', 'rebillLogisticCost']:
    cur.execute("""
    SELECT h.session_id, s.title, substr(h.body, 1, 300) as body_preview
    FROM history_fts h
    JOIN session s ON s.id = h.session_id
    WHERE h.body MATCH ? AND h.kind IN ('text', 'tool')
    AND s.time_created >= 1783305600000
    LIMIT 3
    """, (kw,))
    rows = cur.fetchall()
    if rows:
        print(f"\n=== '{kw}' in trajectory ===")
        for sid, title, body in rows:
            print(f"  [{sid}] {title}: {body[:200]}")

conn.close()
