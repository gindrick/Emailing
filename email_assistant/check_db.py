import sqlite3

conn = sqlite3.connect('data/processing_state.db')
c = conn.cursor()

# First, check what tables exist
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f"Tables in DB: {tables}")

if not tables:
    print("No tables found!")
    conn.close()
    exit(1)

table_name = tables[0][0]
print(f"Using table: {table_name}\n")

# Get all columns
c.execute(f"PRAGMA table_info({table_name})")
columns = c.fetchall()
print(f"Columns: {[col[1] for col in columns]}\n")

# Count total
c.execute(f"SELECT COUNT(*) FROM {table_name}")
total = c.fetchone()[0]

# Kolik emailů odesláno
c.execute(f"SELECT COUNT(*) FROM {table_name} WHERE email_sent = 1")
email_sent_count = c.fetchone()[0]

# Kolik přesunuto do sent
c.execute(f"SELECT COUNT(*) FROM {table_name} WHERE moved_to_sent = 1")
moved_to_sent_count = c.fetchone()[0]

# Statistika
print('=' * 60)
print('DB Summary (processing_state.db):')
print('=' * 60)
print(f'  - Total records: {total}')
print(f'  - Email sent (email_sent=1): {email_sent_count}')
print(f'  - Moved to sent (moved_to_sent=1): {moved_to_sent_count}')
print('=' * 60)

# Show statuses if status column exists
status_col = [col for col in columns if 'status' in col[1].lower()]
if status_col:
    c.execute(f"SELECT status, COUNT(*) FROM {table_name} GROUP BY status ORDER BY status")
    print('\nStatus breakdown:')
    for status, count in c.fetchall():
        print(f'  - {status}: {count}')

conn.close()
