import sqlite3

conn = sqlite3.connect('data/processing_state.db')
cur = conn.cursor()

rows = cur.execute(
    """
    SELECT customer_id, COUNT(*)
    FROM processed_files
    WHERE email_sent = 1
    GROUP BY customer_id
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC, customer_id ASC
    """
).fetchall()

print(f"Duplicate customer_id among sent: {len(rows)}")
for customer_id, cnt in rows[:50]:
    print(f"  - {customer_id}: {cnt}")

recipient_rows = cur.execute(
    """
    SELECT target_recipient, COUNT(*)
    FROM processed_files
    WHERE email_sent = 1
    GROUP BY target_recipient
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC
    """
).fetchall()

print(f"\nDuplicate target_recipient among sent: {len(recipient_rows)}")
for recipient, cnt in recipient_rows[:20]:
    print(f"  - {recipient}: {cnt}")

conn.close()
