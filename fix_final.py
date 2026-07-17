import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()

# Fix Reality-Tv -> Reality (delete dupes first, then update remaining)
cur.execute("""
    DELETE FROM show_genres
    WHERE genre = 'Reality-Tv'
    AND show_id IN (SELECT show_id FROM show_genres WHERE genre = 'Reality')
""")
print(f"Deleted {cur.rowcount} duplicate Reality-Tv rows")
cur.execute("UPDATE show_genres SET genre='Reality' WHERE genre='Reality-Tv'")
print(f"Updated {cur.rowcount} remaining Reality-Tv -> Reality")

# Fix Family Drama -> Drama (same pattern)
cur.execute("""
    DELETE FROM show_genres
    WHERE genre = 'Family Drama'
    AND show_id IN (SELECT show_id FROM show_genres WHERE genre = 'Drama')
""")
print(f"Deleted {cur.rowcount} duplicate Family Drama rows")
cur.execute("UPDATE show_genres SET genre='Drama' WHERE genre='Family Drama'")
print(f"Updated {cur.rowcount} remaining Family Drama -> Drama")

# Remove language names wrongly stored as genres
lang_genres = ['English', 'Hindi', 'Tamil', 'Telugu', 'Bengali', 'Kannada', 'Malayalam', 'Marathi', 'Punjabi', 'Bhojpuri']
for lang in lang_genres:
    cur.execute('DELETE FROM show_genres WHERE genre=%s', (lang,))
    if cur.rowcount:
        print(f'Removed {cur.rowcount} language-as-genre rows: {lang}')

conn.commit()

# Final audit
cur.execute('SELECT DISTINCT genre FROM show_genres ORDER BY genre')
print('\n=== FINAL CLEAN GENRES ===')
for r in cur.fetchall():
    print(' ', r[0])

cur.execute('SELECT DISTINCT platform FROM shows ORDER BY platform')
print('\n=== FINAL CLEAN PLATFORMS ===')
for r in cur.fetchall():
    print(' ', r[0])

cur.execute('SELECT DISTINCT content_type FROM shows ORDER BY content_type')
print('\n=== FINAL CONTENT TYPES ===')
for r in cur.fetchall():
    print(' ', r[0])

conn.close()
print('\nAll clean!')
