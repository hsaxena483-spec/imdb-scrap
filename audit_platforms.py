import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()

print("=== PLATFORMS in show_weekly_rankings ===")
cur.execute("SELECT DISTINCT platform, COUNT(*) FROM show_weekly_rankings GROUP BY platform ORDER BY platform")
for r in cur.fetchall():
    print(f"  {repr(r[0])} ({r[1]} rows)")

print("\n=== PLATFORMS in shows ===")
cur.execute("SELECT DISTINCT platform, COUNT(*) FROM shows GROUP BY platform ORDER BY platform")
for r in cur.fetchall():
    print(f"  {repr(r[0])} ({r[1]} rows)")

conn.close()
