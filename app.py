import os
import math
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for, jsonify, g
from dotenv import load_dotenv
import db

load_dotenv()

app = Flask(__name__)

def normalize_genre(genre_name):
    if not genre_name:
        return ""
    g = genre_name.strip().lower()
    if g in ["reality-tv", "reality tv", "reality_tv"]:
        return "Reality TV"
    if g in ["sci-fi", "scifi", "science fiction"]:
        return "Sci-Fi"
    if g in ["talk-show", "talk show"]:
        return "Talk Show"
    if g in ["game-show", "game show"]:
        return "Game Show"
    if g in ["tv-movie", "tv movie"]:
        return "TV Movie"
    return genre_name.strip().replace('-', ' ').title()


@app.template_global()
def modify_query(page_num):
    args = request.args.copy()
    if 'page' in args:
        args.pop('page')
    
    query_string = urllib.parse.urlencode(args, doseq=True)
    if query_string:
        return f"/?{query_string}&page={page_num}"
    return f"/?page={page_num}"

@app.template_filter('comma')
def comma_filter(value):
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

def get_db():
    if 'db' not in g:
        g.db, g.is_sqlite = db.get_connection()
    return g.db, g.is_sqlite

@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

def get_db_data(query, params=None):
    """
    Helper to execute a query using the request-scoped connection.
    """
    conn, is_sqlite = get_db()
    try:
        cursor = db.execute_query(conn, is_sqlite, query, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return rows, columns
    except Exception as e:
        print(f"Database query error: {e}")
        return [], []

@app.route("/")
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    offset = (page - 1) * per_page
    
    # Collect active filters from query params
    filter_platform = request.args.getlist('platform')
    filter_genre = request.args.getlist('genre')
    filter_language = request.args.getlist('language')
    filter_content_type = request.args.getlist('content_type')
    filter_content_format = request.args.getlist('content_format')
    filter_paid_free = request.args.getlist('paid_free')
    filter_gender = request.args.get('gender', '')
    reach_min = request.args.get('reach_min', '', type=str)
    reach_max = request.args.get('reach_max', '', type=str)
    
    sports_mode = request.args.get('sports_mode', '')
    
    # Build WHERE clauses dynamically
    where_clauses = ["s.current_rank IS NOT NULL"]
    
    if sports_mode == 'only':
        where_clauses.append("(s.content_type = 'Sports' OR s.id IN (SELECT show_id FROM show_genres WHERE genre IN ('Sport', 'Sports')))")
    elif sports_mode == 'exclude':
        where_clauses.append("(s.content_type IS NULL OR s.content_type != 'Sports') AND s.id NOT IN (SELECT show_id FROM show_genres WHERE genre IN ('Sport', 'Sports'))")
        
    params = []
    
    if filter_platform:
        placeholders = ', '.join(['%s'] * len(filter_platform))
        where_clauses.append(f"s.platform IN ({placeholders})")
        params.extend(filter_platform)
    
    if filter_content_type:
        placeholders = ', '.join(['%s'] * len(filter_content_type))
        where_clauses.append(f"s.content_type IN ({placeholders})")
        params.extend(filter_content_type)
    
    if filter_content_format:
        placeholders = ', '.join(['%s'] * len(filter_content_format))
        where_clauses.append(f"s.content_format IN ({placeholders})")
        params.extend(filter_content_format)
    
    if filter_paid_free:
        placeholders = ', '.join(['%s'] * len(filter_paid_free))
        where_clauses.append(f"s.paid_free IN ({placeholders})")
        params.extend(filter_paid_free)
    
    if reach_min:
        where_clauses.append("s.reach >= %s")
        params.append(float(reach_min))
    
    if reach_max:
        where_clauses.append("s.reach <= %s")
        params.append(float(reach_max))
    
    # Genre filter: need to check show_genres table with database value mapping
    if filter_genre:
        db_genres_rows, _ = get_db_data("SELECT DISTINCT genre FROM show_genres")
        raw_matches = []
        for row in db_genres_rows:
            db_gen = row[0]
            if db_gen and normalize_genre(db_gen) in filter_genre:
                raw_matches.append(db_gen)
        
        if raw_matches:
            placeholders = ', '.join(['%s'] * len(raw_matches))
            where_clauses.append(f"s.id IN (SELECT show_id FROM show_genres WHERE genre IN ({placeholders}))")
            params.extend(raw_matches)
        else:
            where_clauses.append("1=0")

    
    # Language filter: use LIKE on the languages TEXT column
    if filter_language:
        lang_conditions = []
        for lang in filter_language:
            lang_conditions.append("s.languages LIKE %s")
            params.append(f"%{lang}%")
        where_clauses.append(f"({' OR '.join(lang_conditions)})")
    
    # Gender filter: filter by platform gender demographics
    if filter_gender == 'male':
        # Show content from platforms where male audience > 50%
        where_clauses.append("s.platform IN (SELECT platform FROM platform_gender WHERE male_pct > 0.5)")
    elif filter_gender == 'female':
        # Show content from platforms where female audience > 50%
        where_clauses.append("s.platform IN (SELECT platform FROM platform_gender WHERE female_pct > 0.5)")
    
    where_sql = " AND ".join(where_clauses)
    
    # Count total matching items
    count_query = f"SELECT COUNT(*) FROM shows s WHERE {where_sql}"
    count_rows, _ = get_db_data(count_query, tuple(params) if params else None)
    total_items = count_rows[0][0] if count_rows else 0
    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 1
    
    # Clamp page
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page
    
    # Fetch paginated shows
    shows_query = f"""
        SELECT s.id, s.title, s.type, s.release_year, s.end_year, s.global_rating, s.global_vote_count, 
               s.runtime_seconds, s.certificate, s.plot, s.poster_url, s.current_rank, s.creators, s.stars,
               s.platform, s.content_format, s.paid_free, s.content_type, s.languages, s.reach, s.week, s.market
        FROM shows s
        WHERE {where_sql}
        ORDER BY s.global_rating DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    all_params = list(params) + [per_page, offset]
    shows_rows, shows_cols = get_db_data(shows_query, tuple(all_params))
    
    shows = []
    for idx, row in enumerate(shows_rows):
        show = dict(zip(shows_cols, row))
        if show['global_rating'] is not None:
            show['global_rating'] = float(show['global_rating'])
        if show['reach'] is not None:
            show['reach'] = round(float(show['reach']), 2)
        show['display_rank'] = offset + idx + 1
        shows.append(show)
        
    # Fetch genres mapping for displayed shows
    genre_rows, genre_cols = get_db_data("SELECT show_id, genre FROM show_genres")
    genres_by_show = {}
    for r in genre_rows:
        show_id, genre = r[0], r[1]
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        if show_id not in genres_by_show:
            genres_by_show[show_id] = set()
        genres_by_show[show_id].add(norm_genre)
        
    for show in shows:
        show['genres'] = sorted(list(genres_by_show.get(show['id'], [])))
    
    # Stats for filtered results
    stats_query = f"""
        SELECT COUNT(*), 
               COALESCE(AVG(s.reach), 0),
               COALESCE(MAX(s.reach), 0),
               COALESCE(AVG(CASE WHEN s.global_rating IS NOT NULL THEN s.global_rating END), 0)
        FROM shows s WHERE {where_sql}
    """
    stats_rows, _ = get_db_data(stats_query, tuple(params) if params else None)
    
    stats = {
        'total_shows': total_items,
        'avg_reach': f"{float(stats_rows[0][1]):.2f}" if stats_rows else "0",
        'max_reach': f"{float(stats_rows[0][2]):.2f}" if stats_rows else "0",
        'avg_rating': f"{float(stats_rows[0][3]):.1f}" if stats_rows else "0",
    }
    
    # Get all distinct values for filter dropdowns
    platforms_data, _ = get_db_data("SELECT DISTINCT platform FROM shows WHERE platform IS NOT NULL AND current_rank IS NOT NULL ORDER BY platform")
    genres_data, _ = get_db_data("SELECT DISTINCT genre FROM show_genres ORDER BY genre")
    content_types_data, _ = get_db_data("SELECT DISTINCT content_type FROM shows WHERE content_type IS NOT NULL AND current_rank IS NOT NULL ORDER BY content_type")
    content_formats_data, _ = get_db_data("SELECT DISTINCT content_format FROM shows WHERE content_format IS NOT NULL AND current_rank IS NOT NULL ORDER BY content_format")
    paid_free_data, _ = get_db_data("SELECT DISTINCT paid_free FROM shows WHERE paid_free IS NOT NULL AND current_rank IS NOT NULL ORDER BY paid_free")
    
    # Extract unique languages from comma-separated strings
    all_langs_rows, _ = get_db_data("SELECT DISTINCT languages FROM shows WHERE languages IS NOT NULL AND current_rank IS NOT NULL")
    all_languages = set()
    for r in all_langs_rows:
        if r[0]:
            for lang in r[0].split(','):
                lang = lang.strip()
                if lang:
                    all_languages.add(lang)
    all_languages = sorted(all_languages)
    
    # Reach range for slider
    reach_range_rows, _ = get_db_data("SELECT MIN(reach), MAX(reach) FROM shows WHERE reach IS NOT NULL AND current_rank IS NOT NULL")
    reach_range = {
        'min': round(float(reach_range_rows[0][0]), 1) if reach_range_rows and reach_range_rows[0][0] else 0,
        'max': round(float(reach_range_rows[0][1]), 1) if reach_range_rows and reach_range_rows[0][1] else 100
    }
    
    # Platform gender data
    platform_gender_rows, pg_cols = get_db_data("SELECT platform, total_reach, male_pct, female_pct FROM platform_gender ORDER BY total_reach DESC")
    platform_gender = []
    for r in platform_gender_rows:
        pg = dict(zip(pg_cols, r))
        pg['total_reach'] = round(float(pg['total_reach']), 2) if pg['total_reach'] else 0
        pg['male_pct'] = round(float(pg['male_pct']) * 100, 1) if pg['male_pct'] else 0
        pg['female_pct'] = round(float(pg['female_pct']) * 100, 1) if pg['female_pct'] else 0
        platform_gender.append(pg)
    
    filter_options = {
        'platforms': [r[0] for r in platforms_data],
        'genres': sorted(list(set(normalize_genre(r[0]) for r in genres_data if r[0] and normalize_genre(r[0]) not in ['Sport', 'Sports']))),
        'content_types': [r[0] for r in content_types_data],
        'content_formats': [r[0] for r in content_formats_data],
        'paid_free': [r[0] for r in paid_free_data],
        'languages': all_languages,
    }
    
    active_filters = {
        'platform': filter_platform,
        'genre': filter_genre,
        'language': filter_language,
        'content_type': filter_content_type,
        'content_format': filter_content_format,
        'paid_free': filter_paid_free,
        'gender': filter_gender,
        'reach_min': reach_min,
        'reach_max': reach_max,
        'sports_mode': sports_mode,
    }
    
    pagination = {
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return render_template("index.html", 
        shows=shows, 
        stats=stats, 
        pagination=pagination,
        filter_options=filter_options,
        active_filters=active_filters,
        reach_range=reach_range,
        platform_gender=platform_gender
    )

@app.route("/show/<show_id>")
def show_detail(show_id):
    # Fetch show main details
    show_rows, show_cols = get_db_data("""
        SELECT id, title, type, release_year, end_year, global_rating, global_vote_count, 
               runtime_seconds, certificate, plot, poster_url, current_rank, creators, stars,
               platform, content_format, paid_free, content_type, languages, reach, week, market
        FROM shows 
        WHERE id = %s
    """, (show_id,))
    
    if not show_rows:
        return "Show not found", 404
        
    show = dict(zip(show_cols, show_rows[0]))
    if show['global_rating'] is not None:
        show['global_rating'] = float(show['global_rating'])
    if show['reach'] is not None:
        show['reach'] = round(float(show['reach']), 2)
        
    # Fetch genres
    genre_rows, _ = get_db_data("SELECT genre FROM show_genres WHERE show_id = %s", (show_id,))
    show['genres'] = sorted(list(set(normalize_genre(r[0]) for r in genre_rows if r[0])))
    
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
        if rev['submission_date']:
            rev['submission_date'] = str(rev['submission_date'])
        reviews.append(rev)
        
    return render_template("show.html", show=show, country_ratings=country_ratings, reviews=reviews)

@app.route("/api/filters")
def api_filters():
    """Return all filter options as JSON for dynamic filtering."""
    platforms_data, _ = get_db_data("SELECT DISTINCT platform FROM shows WHERE platform IS NOT NULL ORDER BY platform")
    genres_data, _ = get_db_data("SELECT DISTINCT genre FROM show_genres ORDER BY genre")
    content_types_data, _ = get_db_data("SELECT DISTINCT content_type FROM shows WHERE content_type IS NOT NULL ORDER BY content_type")
    content_formats_data, _ = get_db_data("SELECT DISTINCT content_format FROM shows WHERE content_format IS NOT NULL ORDER BY content_format")
    
    return jsonify({
        'platforms': [r[0] for r in platforms_data],
        'genres': sorted(list(set(normalize_genre(r[0]) for r in genres_data if r[0] and normalize_genre(r[0]) not in ['Sport', 'Sports']))),
        'content_types': [r[0] for r in content_types_data],
        'content_formats': [r[0] for r in content_formats_data],
    })


@app.route("/analytics")
def analytics():
    # 1. Top 10 content by rank with reach and rating
    top_shows_rows, top_shows_cols = get_db_data("""
        SELECT title, reach, global_rating 
        FROM shows 
        WHERE current_rank IS NOT NULL 
          AND (content_type IS NULL OR LOWER(content_type) != 'sports')
        ORDER BY current_rank ASC 
        LIMIT 10
    """)
    top_shows = []
    for row in top_shows_rows:
        show = dict(zip(top_shows_cols, row))
        show['reach'] = float(show['reach']) if show['reach'] is not None else 0.0
        show['global_rating'] = float(show['global_rating']) if show['global_rating'] is not None else 0.0
        top_shows.append(show)

    # 2. Platform distribution
    platform_rows, platform_cols = get_db_data("""
        SELECT platform, COUNT(*) as count 
        FROM shows 
        WHERE platform IS NOT NULL AND current_rank IS NOT NULL 
        GROUP BY platform 
        ORDER BY count DESC
    """)
    platforms = []
    for row in platform_rows:
        platforms.append({
            'platform': row[0],
            'count': int(row[1])
        })

    # 2b. Format distribution by reach (views)
    format_rows, _ = get_db_data("""
        SELECT content_format, SUM(reach) as total_reach 
        FROM shows 
        WHERE content_format IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
        GROUP BY content_format 
        ORDER BY total_reach DESC
    """)
    formats_by_reach = []
    for row in format_rows:
        formats_by_reach.append({
            'format': row[0],
            'reach': round(float(row[1]), 2)
        })

    # 3. Genre reach percentage
    genre_rows, _ = get_db_data("""
        SELECT s.id, s.reach, g.genre 
        FROM shows s 
        JOIN show_genres g ON s.id = g.show_id 
        WHERE s.reach IS NOT NULL AND s.current_rank IS NOT NULL
    """)
    
    show_genres_map = {}
    for show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        if show_id not in show_genres_map:
            show_genres_map[show_id] = (float(reach) if reach is not None else 0.0, set())
        show_genres_map[show_id][1].add(norm_genre)
        
    genre_reach_map = {}
    for show_id, (reach, genres) in show_genres_map.items():
        for genre in genres:
            genre_reach_map[genre] = genre_reach_map.get(genre, 0.0) + reach
            
    total_genre_reach = sum(genre_reach_map.values())
    genre_percentages = []
    if total_genre_reach > 0:
        for genre, reach in genre_reach_map.items():
            pct = (reach / total_genre_reach) * 100
            genre_percentages.append({
                'genre': genre,
                'reach': round(reach, 2),
                'percentage': round(pct, 2)
            })
        genre_percentages = sorted(genre_percentages, key=lambda x: x['percentage'], reverse=True)

    # 4. Language reach percentage
    lang_rows, _ = get_db_data("""
        SELECT id, reach, languages 
        FROM shows 
        WHERE languages IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL
    """)
    
    show_langs_map = {}
    for show_id, reach, languages_str in lang_rows:
        if not languages_str:
            continue
        parts = languages_str.split(',')
        unique_langs = set()
        for p in parts:
            lang = p.strip().title()
            if lang:
                unique_langs.add(lang)
        
        show_langs_map[show_id] = (float(reach) if reach is not None else 0.0, unique_langs)
        
    lang_reach_map = {}
    for show_id, (reach, langs) in show_langs_map.items():
        for lang in langs:
            lang_reach_map[lang] = lang_reach_map.get(lang, 0.0) + reach
            
    total_lang_reach = sum(lang_reach_map.values())
    lang_percentages = []
    if total_lang_reach > 0:
        for lang, reach in lang_reach_map.items():
            pct = (reach / total_lang_reach) * 100
            lang_percentages.append({
                'language': lang,
                'reach': round(reach, 2),
                'percentage': round(pct, 2)
            })
        lang_percentages = sorted(lang_percentages, key=lambda x: x['percentage'], reverse=True)

    return render_template(
        "analytics.html", 
        top_shows=top_shows, 
        platforms=platforms, 
        formats_by_reach=formats_by_reach,
        genre_percentages=genre_percentages, 
        lang_percentages=lang_percentages
    )


import subprocess
import sys

@app.route("/update")
def update():
    # Trigger the scraper in a completely independent background process
    subprocess.Popen([sys.executable, "scraper.py"])
    return redirect(url_for('index', syncing='true'))

@app.route("/sync_status")
def sync_status():
    running = os.path.exists("scraper.lock")
    return {"status": "syncing" if running else "idle"}

if __name__ == "__main__":
    # Ensure tables exist
    try:
        db.init_db()
    except Exception as e:
        print(f"Failed to initialize database: {e}")

    # Clean up any stale lock file on startup
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