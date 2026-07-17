import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()

# Check platform_gender table
print("=== platform_gender table ===")
cur.execute("SELECT platform, total_reach, male_pct, female_pct FROM platform_gender ORDER BY platform")
rows = cur.fetchall()
for r in rows:
    print(f"  {repr(r[0])} | reach={r[1]} | male={r[2]} | female={r[3]}")

conn.close()
