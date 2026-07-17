import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()

# Fix Game-Show -> Game Show
cur.execute("DELETE FROM show_genres WHERE genre='Game-Show' AND show_id IN (SELECT show_id FROM show_genres WHERE genre='Game Show')")
print('Deleted dupes:', cur.rowcount)
cur.execute("UPDATE show_genres SET genre='Game Show' WHERE genre='Game-Show'")
print('Updated remaining:', cur.rowcount)
conn.commit()

cur.execute('SELECT DISTINCT genre FROM show_genres ORDER BY genre')
print('Final genres:', [r[0] for r in cur.fetchall()])
conn.close()
