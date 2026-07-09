import os
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
import db

load_dotenv()

app = Flask(__name__)

@app.template_filter('comma')
def comma_filter(value):
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

def get_db_data(query, params=None):
    """
    Helper to execute a query and return fetched rows, columns, and connection info.
    """
    conn, is_sqlite = db.get_connection()
    try:
        cursor = db.execute_query(conn, is_sqlite, query, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return rows, columns
    except Exception as e:
        print(f"Database query error: {e}")
        return [], []
    finally:
        conn.close()

@app.route("/")
def index():
    import math
    page = request.args.get('page', 1, type=int)
    per_page = 12
    offset = (page - 1) * per_page
    
    # Fetch paginated shows ordered by rank
    shows_rows, shows_cols = get_db_data("""
        SELECT id, title, type, release_year, end_year, global_rating, global_vote_count, 
               runtime_seconds, certificate, plot, poster_url, current_rank, creators, stars 
        FROM shows 
        WHERE current_rank IS NOT NULL
        ORDER BY current_rank ASC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    
    shows = []
    for row in shows_rows:
        show = dict(zip(shows_cols, row))
        # Ensure ratings and ranks are formatted nicely
        if show['global_rating'] is not None:
            show['global_rating'] = float(show['global_rating'])
        shows.append(show)
        
    # Fetch genres mapping
    genre_rows, genre_cols = get_db_data("SELECT show_id, genre FROM show_genres")
    genres_by_show = {}
    for r in genre_rows:
        show_id, genre = r[0], r[1]
        if show_id not in genres_by_show:
            genres_by_show[show_id] = []
        genres_by_show[show_id].append(genre)
        
    # Attach genres to shows
    for show in shows:
        show['genres'] = genres_by_show.get(show['id'], [])
        
    # Fetch total count of trending shows
    count_rows, _ = get_db_data("SELECT COUNT(*) FROM shows WHERE current_rank IS NOT NULL")
    total_trending_shows = count_rows[0][0] if count_rows else 0
    total_pages = math.ceil(total_trending_shows / per_page)
    
    # Get overall stats over all shows in the database
    all_shows_rows, _ = get_db_data("SELECT global_rating, global_vote_count FROM shows WHERE current_rank IS NOT NULL")
    total_shows = len(all_shows_rows)
    avg_rating = 0.0
    total_votes = 0
    
    rated_votes = [r[0] for r in all_shows_rows if r[0] is not None]
    if rated_votes:
        avg_rating = sum(float(r) for r in rated_votes) / len(rated_votes)
    total_votes = sum(int(r[1]) for r in all_shows_rows if r[1] is not None)
    
    stats = {
        'total_shows': total_trending_shows,
        'avg_rating': f"{avg_rating:.2f}",
        'total_votes': f"{total_votes:,}"
    }
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    pagination = {
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return render_template("index.html", shows=shows, stats=stats, pagination=pagination)

@app.route("/show/<show_id>")
def show_detail(show_id):
    # Fetch show main details
    show_rows, show_cols = get_db_data("""
        SELECT id, title, type, release_year, end_year, global_rating, global_vote_count, 
               runtime_seconds, certificate, plot, poster_url, current_rank, creators, stars 
        FROM shows 
        WHERE id = %s
    """, (show_id,))
    
    if not show_rows:
        return "Show not found", 404
        
    show = dict(zip(show_cols, show_rows[0]))
    if show['global_rating'] is not None:
        show['global_rating'] = float(show['global_rating'])
        
    # Fetch genres
    genre_rows, _ = get_db_data("SELECT genre FROM show_genres WHERE show_id = %s", (show_id,))
    show['genres'] = [r[0] for r in genre_rows]
    
    # Fetch country ratings
    country_rows, country_cols = get_db_data("""
        SELECT country_code, country_name, rating, vote_count 
        FROM show_country_ratings 
        WHERE show_id = %s 
        ORDER BY vote_count DESC
    """, (show_id,))
    
    country_ratings = []
    for r in country_rows:
        cr = dict(zip(country_cols, r))
        if cr['rating'] is not None:
            cr['rating'] = float(cr['rating'])
        country_ratings.append(cr)
        
    # Fetch reviews
    reviews_rows, reviews_cols = get_db_data("""
        SELECT id, author_username, author_id, rating, summary, content, 
               submission_date, up_votes, down_votes, is_spoiler 
        FROM show_reviews 
        WHERE show_id = %s 
        ORDER BY submission_date DESC
    """, (show_id,))
    
    reviews = []
    for r in reviews_rows:
        rev = dict(zip(reviews_cols, r))
        # Parse dates to strings for template rendering
        if rev['submission_date']:
            rev['submission_date'] = str(rev['submission_date'])
        reviews.append(rev)
        
    return render_template("show.html", show=show, country_ratings=country_ratings, reviews=reviews)

import subprocess
import sys

@app.route("/update")
def update():
    # Trigger the scraper in a completely independent background process
    # This prevents thread conflicts and debug auto-reloads from killing it
    subprocess.Popen([sys.executable, "scraper.py"])
    return redirect(url_for('index', syncing='true'))

@app.route("/sync_status")
def sync_status():
    # If the scraper.lock file exists, the scraper is currently running
    import os
    running = os.path.exists("scraper.lock")
    return {"status": "syncing" if running else "idle"}

if __name__ == "__main__":
    # Clean up any stale lock file on startup
    import os
    if os.path.exists("scraper.lock"):
        try:
            os.remove("scraper.lock")
        except Exception:
            pass

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )