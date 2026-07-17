import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM shows")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM shows WHERE creators IS NOT NULL AND creators != ''")
has_creators = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM shows WHERE stars IS NOT NULL AND stars != ''")
has_stars = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM shows WHERE certificate IS NOT NULL AND certificate != ''")
has_cert = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM shows WHERE global_rating IS NOT NULL")
has_rating = cur.fetchone()[0]

print(f"Total shows: {total}")
print(f"Has creators: {has_creators} ({100*has_creators//total}%)")
print(f"Has stars:    {has_stars} ({100*has_stars//total}%)")
print(f"Has cert:     {has_cert} ({100*has_cert//total}%)")
print(f"Has rating:   {has_rating} ({100*has_rating//total}%)")

print("\nSample shows with missing data:")
cur.execute("""
    SELECT id, title, creators, stars, certificate, global_rating
    FROM shows
    WHERE (creators IS NULL OR creators = '') OR (stars IS NULL OR stars = '')
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]} | {r[1][:40]:<40} | creators={repr(r[2])} | stars={repr(r[3])} | cert={repr(r[4])} | rating={r[5]}")

conn.close()
