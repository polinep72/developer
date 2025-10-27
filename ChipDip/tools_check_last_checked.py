import os
import psycopg2
from decouple import config

reset = os.environ.get('RESET_LASTCHECKED', '0') == '1'

conn = psycopg2.connect(
    host=config('DB_HOST'),
    database=config('DB_NAME'),
    user=config('DB_USER'),
    password=config('DB_PASSWORD')
)
cur = conn.cursor()

cur.execute("""
SELECT COUNT(*) FROM products 
WHERE is_active=TRUE AND (last_checked_at IS NULL OR last_checked_at <= NOW() - INTERVAL '12 hours');
""")
print('Eligible to parse (<= now-12h or NULL):', cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM products WHERE is_active=TRUE;")
print('Active products:', cur.fetchone()[0])

cur.execute("SELECT MIN(last_checked_at), MAX(last_checked_at) FROM products;")
print('last_checked_at min/max:', cur.fetchone())

cur.execute("""
SELECT id, name, last_checked_at 
FROM products 
WHERE is_active=TRUE 
ORDER BY last_checked_at ASC NULLS FIRST, id ASC 
LIMIT 5;
""")
rows = cur.fetchall()
print('Sample (first 5 by last_checked_at):')
for r in rows:
    print(r)

if reset:
    cur.execute("UPDATE products SET last_checked_at = NULL WHERE is_active=TRUE;")
    conn.commit()
    print('last_checked_at сброшен в NULL для активных товаров')

conn.close()
