import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    dbname=os.getenv("DB_NAME"),
)
cur = conn.cursor()

term = "пс2у"
pattern = f"%{term}%"

cur.execute("select id, name from names_pp where lower(name) like lower(%s)", (pattern,))
names = cur.fetchall()
print("names_pp matches:", names)

cur.execute(
    """
    select id, element_type_id, legacy_name_id, name
    from elements
    where element_type_id = (select id from element_types where code='pp')
      and lower(name) like lower(%s)
    """,
    (pattern,),
)
els = cur.fetchall()
print("elements(pp) matches:", els)

if names:
    ids = tuple([r[0] for r in names])
    cur.execute(
        f"""
        select count(*) from invoices
        where element_type_id=(select id from element_types where code='pp')
          and name_id in {ids}
        """
    )
    print("invoices(pp) rows with name_id in names_pp ids:", cur.fetchone()[0])

    cur.execute(
        f"""
        select id, invoice_id, name_id, chip_id, body_id, pp_id, arrival_date_id, quan, item_id
        from invoices
        where element_type_id=(select id from element_types where code='pp')
          and name_id in {ids}
        limit 10
        """
    )
    print("sample invoices rows:", cur.fetchall()[:3])

# Also check join path used by bot
cur.execute(
    """
    select count(*)
    from invoices i
    join elements e on e.element_type_id=i.element_type_id and e.legacy_name_id=i.name_id
    where i.element_type_id=(select id from element_types where code='pp')
    """
)
print("invoices(pp) join to elements via legacy_name_id works rows:", cur.fetchone()[0])

cur.close()
conn.close()

