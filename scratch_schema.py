import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='shows' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("shows columns:", cols)

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='show_weekly_rankings' ORDER BY ordinal_position")
cols2 = [r[0] for r in cur.fetchall()]
print("weekly_rankings columns:", cols2)
conn.close()
