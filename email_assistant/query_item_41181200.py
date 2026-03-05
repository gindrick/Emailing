import sqlite3

conn = sqlite3.connect('data/processing_state.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

row = cur.execute(
    "SELECT item_id, file_name, email_sent, moved_to_sent, status, last_error, email_sent_at, moved_at, updated_at "
    "FROM processed_files WHERE file_name LIKE ? OR customer_id = ?",
    ('41181200 %', '41181200')
).fetchone()

if row is None:
    print('NOT FOUND')
else:
    for key in row.keys():
        print(f"{key}: {row[key]}")

conn.close()
