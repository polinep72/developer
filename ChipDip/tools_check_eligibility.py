import psycopg2
from decouple import config

conn = psycopg2.connect(
    host=config('DB_HOST'),
    database=config('DB_NAME'),
    user=config('DB_USER'),
    password=config('DB_PASSWORD')
)
cur = conn.cursor()

# Всего товаров
cur.execute("SELECT COUNT(*) FROM products;")
print('Total products:', cur.fetchone()[0])

# Активные с COALESCE
cur.execute("SELECT COUNT(*) FROM products WHERE COALESCE(is_active, TRUE) = TRUE;")
print('Active (coalesced) products:', cur.fetchone()[0])

# Последняя проверка по stock_history
cur.execute("""
SELECT COUNT(*)
FROM products p
LEFT JOIN LATERAL (
  SELECT sh.check_timestamp AS last_check
  FROM stock_history sh
  WHERE sh.product_id = p.id
  ORDER BY sh.check_timestamp DESC
  LIMIT 1
) lc ON TRUE
WHERE COALESCE(p.is_active, TRUE) = TRUE
  AND (
    lc.last_check IS NULL OR lc.last_check <= NOW() - INTERVAL '12 hours'
  );
""")
print('Eligible by 12h rule:', cur.fetchone()[0])

# Показать 5 примеров
cur.execute("""
SELECT p.id, p.name, lc.last_check
FROM products p
LEFT JOIN LATERAL (
  SELECT sh.check_timestamp AS last_check
  FROM stock_history sh
  WHERE sh.product_id = p.id
  ORDER BY sh.check_timestamp DESC
  LIMIT 1
) lc ON TRUE
WHERE COALESCE(p.is_active, TRUE) = TRUE
ORDER BY lc.last_check ASC NULLS FIRST, p.id ASC
LIMIT 5;
""")
rows = cur.fetchall()
print('Sample (first 5):')
for r in rows:
    print(r)

conn.close()
