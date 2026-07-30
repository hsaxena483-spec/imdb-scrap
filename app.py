import os
import math
import json
import urllib.parse
import requests
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify, g, make_response
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import db
import scraper

# Load environment variables relative to app.py directory
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "supersecret_jwt_signing_key")
token_serializer = URLSafeTimedSerializer(JWT_SECRET)

def requires_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization token is missing"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            # Token is valid for 30 days
            user_id = token_serializer.loads(token, max_age=30 * 24 * 3600)
        except SignatureExpired:
            return jsonify({"error": "Token has expired"}), 401
        except BadSignature:
            return jsonify({"error": "Invalid token"}), 401
            
        conn, is_sqlite = get_db()
        user = db.get_user(conn, is_sqlite, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not user.get("is_active"):
            return jsonify({"error": "Account is inactive"}), 403
            
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def requires_admin_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Admin authorization token is missing"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            # Admin token is valid for 7 days
            admin_email = token_serializer.loads(token, salt="admin-auth", max_age=7 * 24 * 3600)
            if admin_email != "admin@cott.com":
                return jsonify({"error": "Unauthorized admin access"}), 403
        except SignatureExpired:
            return jsonify({"error": "Admin token has expired"}), 401
        except BadSignature:
            return jsonify({"error": "Invalid admin token"}), 401
            
        g.current_admin = admin_email
        return f(*args, **kwargs)
    return decorated

@app.route("/api/auth/google", methods=["POST"])
def google_auth():
    data = request.get_json()
    if not data or "credential" not in data:
        return jsonify({"error": "Credential token is missing"}), 400
        
    id_token = data["credential"]
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "your_client_id")
    
    try:
        # Call Google tokeninfo API to verify the ID token
        token_info_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
        response = requests.get(token_info_url)
        if response.status_code != 200:
            return jsonify({"error": "Invalid Google credential"}), 400
            
        user_info = response.json()
        
        # Verify audience matches client ID if CLIENT_ID is configured
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_ID != "your_client_id":
            aud = user_info.get("aud")
            if aud != GOOGLE_CLIENT_ID:
                return jsonify({"error": "Audience mismatch"}), 400
                
        user_id = user_info.get("sub")
        email = user_info.get("email")
        name = user_info.get("name")
        picture = user_info.get("picture")
        
        if not email:
            return jsonify({"error": "Email not found in Google profile"}), 400
            
        # Get connection
        conn, is_sqlite = get_db()
        
        # Check if user already exists
        existing_user = db.get_user(conn, is_sqlite, user_id)
        
        user_data = {
            "id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "phone_number": existing_user.get("phone_number") if existing_user else None,
            "user_role": existing_user.get("user_role") if existing_user else "normal user",
            "is_active": existing_user.get("is_active") if existing_user else True,
            "account_type": existing_user.get("account_type") if existing_user else "free",
            "plan_status": existing_user.get("plan_status") if existing_user else "none"
        }
        
        db.upsert_user(conn, is_sqlite, user_data)
        
        # Generate session token (valid for 30 days)
        session_token = token_serializer.dumps(user_id)
        
        return jsonify({
            "token": session_token,
            "user": user_data
        }), 200
        
    except Exception as e:
        print(f"Error in google_auth: {e}")
        return jsonify({"error": "Authentication failed", "details": str(e)}), 500

@app.route("/api/auth/me", methods=["GET"])
@requires_auth
def get_me():
    return jsonify(g.current_user), 200

@app.route("/api/auth/profile", methods=["PUT"])
@requires_auth
def update_profile():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    name = data.get("name", "").strip()
    phone_number = data.get("phone_number", "").strip()
    
    if not name:
        return jsonify({"error": "Name is required"}), 400
        
    try:
        conn, is_sqlite = get_db()
        
        profile_data = {
            "name": name,
            "phone_number": phone_number if phone_number else None
        }
        
        db.update_user_profile(conn, is_sqlite, g.current_user["id"], profile_data)
        
        # Fetch the updated user details
        updated_user = db.get_user(conn, is_sqlite, g.current_user["id"])
        
        return jsonify(updated_user), 200
    except Exception as e:
        print(f"Error in update_profile: {e}")
        return jsonify({"error": "Failed to update profile", "details": str(e)}), 500

@app.route("/api/auth/bypass", methods=["POST"])
def auth_bypass():
    conn, is_sqlite = get_db()
    user_data = {
        "id": "mock_dev_user_12345",
        "email": "developer@cott.analytics",
        "name": "Dev User",
        "picture": "https://lh3.googleusercontent.com/a/default-user=s96-c",
        "phone_number": "1234567890",
        "user_role": "super admin",
        "is_active": True,
        "account_type": "paid",
        "plan_status": "active"
    }
    
    db.upsert_user(conn, is_sqlite, user_data)
    session_token = token_serializer.dumps(user_data["id"])
    
    return jsonify({
        "token": session_token,
        "user": user_data
    }), 200

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No credentials provided"}), 400
        
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = "SELECT password, user_role FROM users WHERE email = %s"
        if is_sqlite:
            query = query.replace("%s", "?")
        cursor.execute(query, (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            db_password_hash, db_role = row[0], row[1]
            from werkzeug.security import check_password_hash
            if db_password_hash and check_password_hash(db_password_hash, password) and db_role == "admin":
                token = token_serializer.dumps(email, salt="admin-auth")
                return jsonify({
                    "token": token,
                    "email": email,
                    "role": "admin"
                }), 200
        
        return jsonify({"error": "Invalid admin email or password"}), 401
    except Exception as e:
        print(f"Error in admin_login: {e}")
        return jsonify({"error": "Failed to complete login transaction", "details": str(e)}), 500

@app.route("/api/admin/stats", methods=["GET"])
@requires_admin_auth
def admin_get_stats():
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # 1. Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # 2. Total shows
        cursor.execute("SELECT COUNT(*) FROM shows")
        total_shows = cursor.fetchone()[0]
        
        # 3. Platform distribution
        cursor.execute("""
            SELECT platform, COUNT(*) 
            FROM shows 
            WHERE platform IS NOT NULL 
            GROUP BY platform 
            ORDER BY COUNT(*) DESC
        """)
        platform_rows = cursor.fetchall()
        platform_stats = [{"platform": r[0], "count": r[1]} for r in platform_rows]
        
        # 4. Weekly scraping volume (historical database growth)
        cursor.execute("""
            SELECT week, COUNT(*) 
            FROM shows 
            WHERE week IS NOT NULL 
            GROUP BY week
        """)
        week_rows = cursor.fetchall()
        
        # Sort weeks chronologically in Python to keep it database-agnostic
        def parse_week_sort_key(item):
            week_code = item[0]
            if not week_code:
                return (0, 0)
            import re
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(week_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
            
        week_rows.sort(key=parse_week_sort_key)
        weekly_stats = [{"week": r[0], "count": r[1]} for r in week_rows]
        
        conn.close()
        
        return jsonify({
            "total_users": total_users,
            "total_shows": total_shows,
            "platform_stats": platform_stats,
            "weekly_stats": weekly_stats
        }), 200
    except Exception as e:
        print(f"Error in admin_get_stats: {e}")
        return jsonify({"error": "Failed to fetch stats", "details": str(e)}), 500

@app.route("/api/admin/users", methods=["GET"])
@requires_admin_auth
def admin_get_users():
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = """
        SELECT id, email, name, picture, phone_number, user_role, is_active, account_type, plan_status, created_at 
        FROM users 
        ORDER BY created_at DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        users = []
        for r in rows:
            users.append({
                "id": r[0],
                "email": r[1],
                "name": r[2],
                "picture": r[3],
                "phone_number": r[4],
                "user_role": r[5],
                "is_active": r[6],
                "account_type": r[7],
                "plan_status": r[8],
                "created_at": r[9].isoformat() if r[9] and hasattr(r[9], 'isoformat') else str(r[9])
            })
        return jsonify(users), 200
    except Exception as e:
        print(f"Error in admin_get_users: {e}")
        return jsonify({"error": "Failed to fetch users", "details": str(e)}), 500

@app.route("/api/admin/upload-excel", methods=["POST"])
@requires_admin_auth
def admin_upload_excel():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
        
    if not file.filename.endswith('.xlsx'):
        return jsonify({"error": "Only Excel files (.xlsx) are allowed"}), 400
        
    # Save the file to data_input/uploads/
    upload_dir = os.path.join(basedir, "data_input", "uploads")
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        
    import uuid
    unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(upload_dir, unique_filename)
    file.save(filepath)
    
    # Insert pending job into scraping_jobs
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = "INSERT INTO scraping_jobs (status, current_show) VALUES ('pending', 'Initializing Excel upload')"
        if is_sqlite:
            cursor.execute(query)
            job_id = cursor.lastrowid
        else:
            query += " RETURNING id"
            cursor.execute(query)
            job_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inserting scraping job: {e}")
        return jsonify({"error": "Failed to initialize scraping task in database", "details": str(e)}), 500
        
    # Spawn background thread to run scraping
    try:
        thread = threading.Thread(target=scraper.process_excel_file, args=(filepath, job_id))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "pending",
            "message": "Scraping task started in the background"
        }), 200
    except Exception as e:
        print(f"Error spawning scraping thread: {e}")
        return jsonify({"error": "Failed to start scraping background thread", "details": str(e)}), 500

@app.route("/api/admin/scraping-job/<int:job_id>", methods=["GET"])
@requires_admin_auth
def admin_get_job_status(job_id):
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = """
        SELECT id, status, total_shows, processed_shows, current_show, error_message, created_at, updated_at 
        FROM scraping_jobs 
        WHERE id = %s
        """
        if is_sqlite:
            query = query.replace("%s", "?")
            
        cursor.execute(query, (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"error": "Job not found"}), 404
            
        return jsonify({
            "id": row[0],
            "status": row[1],
            "total_shows": row[2],
            "processed_shows": row[3],
            "current_show": row[4],
            "error_message": row[5],
            "created_at": row[6].isoformat() if row[6] and hasattr(row[6], 'isoformat') else str(row[6]),
            "updated_at": row[7].isoformat() if row[7] and hasattr(row[7], 'isoformat') else str(row[7])
        }), 200
    except Exception as e:
        print(f"Error fetching job status: {e}")
        return jsonify({"error": "Failed to fetch job status", "details": str(e)}), 500


@app.before_request
def handle_options_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        return response

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

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
    search_q = request.args.get('q', '').strip()
    
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
    
    # Search by title
    if search_q:
        where_clauses.append("s.title ILIKE %s")
        params_prefix = [f"%{search_q}%"]
    else:
        params_prefix = []
    if sports_mode == 'only':
        where_clauses.append("(s.content_type = 'Sports' OR s.id IN (SELECT show_id FROM show_genres WHERE genre IN ('Sport', 'Sports')))")
    elif sports_mode == 'exclude':
        where_clauses.append("(s.content_type IS NULL OR s.content_type != 'Sports') AND s.id NOT IN (SELECT show_id FROM show_genres WHERE genre IN ('Sport', 'Sports'))")
        
    params = params_prefix
    
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
        ORDER BY SUBSTR(s.week, 8, 4) DESC, SUBSTR(s.week, 4, 2) DESC, s.global_rating DESC NULLS LAST
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
        'q': search_q,
    }
    
    # Smart page list: always show first, last, current±2, with None = ellipsis
    def build_page_list(cur, total, window=2):
        pages = set()
        pages.add(1)
        pages.add(total)
        for p in range(max(2, cur - window), min(total, cur + window + 1)):
            pages.add(p)
        sorted_pages = sorted(pages)
        result = []
        prev = None
        for p in sorted_pages:
            if prev is not None and p - prev > 1:
                result.append(None)   # ellipsis marker
            result.append(p)
            prev = p
        return result

    pagination = {
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1,
        'page_list': build_page_list(page, total_pages) if total_pages > 1 else []
    }
    
    return render_template("index.html", 
        shows=shows, 
        stats=stats, 
        pagination=pagination,
        filter_options=filter_options,
        active_filters=active_filters,
        reach_range=reach_range,
        platform_gender=platform_gender,
        search_q=search_q
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
        
    # Fetch weekly ranking history sorted chronologically
    history_rows, _ = get_db_data("""
        SELECT week, current_rank, reach 
        FROM show_weekly_rankings 
        WHERE show_id = %s 
        ORDER BY week ASC
    """, (show_id,))
    
    def sort_history_key(row):
        w_code = row[0]
        import re
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
        
    sorted_history = sorted(history_rows, key=sort_history_key)
    
    weekly_history = []
    for r in sorted_history:
        weekly_history.append({
            'week': r[0],
            'rank': int(r[1]) if r[1] is not None else None,
            'reach': round(float(r[2]), 2) if r[2] is not None else 0.0
        })
        
    return render_template("show.html", show=show, country_ratings=country_ratings, reviews=reviews, weekly_history=weekly_history)


@app.route("/api/shows")
def api_shows_json():
    # Helper to parse list parameters which could be comma-separated or separate request arguments
    def get_list_param(param_name):
        vals = request.args.getlist(param_name)
        if len(vals) == 1 and ',' in vals[0]:
            return [v.strip() for v in vals[0].split(',') if v.strip()]
        return vals

    page = request.args.get('page', 1, type=int)
    per_page = 12
    offset = (page - 1) * per_page
    search_q = request.args.get('q', '').strip()
    
    # Collect active filters from query params
    filter_platform = get_list_param('platform')
    filter_genre = get_list_param('genre')
    filter_language = get_list_param('language')
    filter_content_type = get_list_param('content_type')
    filter_content_format = get_list_param('content_format')
    filter_paid_free = get_list_param('paid_free')
    filter_gender = request.args.get('gender', '')
    reach_min = request.args.get('reach_min', '', type=str)
    reach_max = request.args.get('reach_max', '', type=str)
    sports_mode = request.args.get('sports_mode', '')
    
    # Build WHERE clauses dynamically
    where_clauses = ["s.current_rank IS NOT NULL"]
    
    # Search by title
    if search_q:
        where_clauses.append("s.title ILIKE %s")
        params_prefix = [f"%{search_q}%"]
    else:
        params_prefix = []
        
    if sports_mode == 'only':
        where_clauses.append("(s.content_type = 'Sports' OR s.id IN (SELECT show_id FROM show_genres WHERE genre IN ('Sport', 'Sports')))")
    elif sports_mode == 'exclude':
        where_clauses.append("(s.content_type IS NULL OR s.content_type != 'Sports') AND s.id NOT IN (SELECT show_id FROM show_genres WHERE genre IN ('Sport', 'Sports'))")
        
    params = params_prefix
    
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
    
    # Genre filter
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
    
    # Language filter
    if filter_language:
        lang_conditions = []
        for lang in filter_language:
            lang_conditions.append("s.languages LIKE %s")
            params.append(f"%{lang}%")
        where_clauses.append(f"({' OR '.join(lang_conditions)})")
    
    # Gender filter
    if filter_gender == 'male':
        where_clauses.append("s.platform IN (SELECT platform FROM platform_gender WHERE male_pct > 0.5)")
    elif filter_gender == 'female':
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
        ORDER BY SUBSTR(s.week, 8, 4) DESC, SUBSTR(s.week, 4, 2) DESC, s.global_rating DESC NULLS LAST
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
    genre_rows, _ = get_db_data("SELECT show_id, genre FROM show_genres")
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
    
    # Extract unique languages
    all_langs_rows, _ = get_db_data("SELECT DISTINCT languages FROM shows WHERE languages IS NOT NULL AND current_rank IS NOT NULL")
    all_languages = set()
    for r in all_langs_rows:
        if r[0]:
            for lang in r[0].split(','):
                lang = lang.strip()
                if lang:
                    all_languages.add(lang)
    all_languages = sorted(all_languages)
    
    # Reach range
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
    
    pagination = {
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return jsonify({
        'shows': shows,
        'stats': stats,
        'pagination': pagination,
        'filter_options': filter_options,
        'reach_range': reach_range,
        'platform_gender': platform_gender
    })


@app.route("/api/show/<show_id>/json")
def api_show_detail_json(show_id):
    # Fetch show main details
    show_rows, show_cols = get_db_data("""
        SELECT id, title, type, release_year, end_year, global_rating, global_vote_count, 
               runtime_seconds, certificate, plot, poster_url, current_rank, creators, stars,
               platform, content_format, paid_free, content_type, languages, reach, week, market
        FROM shows 
        WHERE id = %s
    """, (show_id,))
    
    if not show_rows:
        return jsonify({'error': 'Show not found'}), 404
        
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
        
    # Fetch weekly ranking history
    history_rows, _ = get_db_data("""
        SELECT week, current_rank, reach 
        FROM show_weekly_rankings 
        WHERE show_id = %s 
        ORDER BY week ASC
    """, (show_id,))
    
    def sort_history_key(row):
        w_code = row[0]
        import re
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
        
    sorted_history = sorted(history_rows, key=sort_history_key)
    
    weekly_history = []
    for r in sorted_history:
        weekly_history.append({
            'week': r[0],
            'rank': int(r[1]) if r[1] is not None else None,
            'reach': round(float(r[2]), 2) if r[2] is not None else 0.0
        })
        
    return jsonify({
        'show': show,
        'country_ratings': country_ratings,
        'reviews': reviews,
        'weekly_history': weekly_history
    })


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

@app.route("/api/search")
def api_search():
    """Live search endpoint for autocomplete dropdown."""
    q = request.args.get('q', '').strip()
    
    if not q:
        query = """
            SELECT id, title, poster_url, platform, global_rating, release_year
            FROM shows
            WHERE current_rank IS NOT NULL
            ORDER BY current_rank ASC
            LIMIT 50
        """
        rows, cols = get_db_data(query)
    else:
        query = """
            SELECT id, title, poster_url, platform, global_rating, release_year
            FROM shows
            WHERE title ILIKE %s
            ORDER BY current_rank ASC NULLS LAST, global_rating DESC NULLS LAST
            LIMIT 15
        """
        rows, cols = get_db_data(query, (f"%{q}%",))
    
    results = []
    for r in rows:
        show = dict(zip(cols, r))
        if show['global_rating'] is not None:
            show['global_rating'] = float(show['global_rating'])
        results.append(show)
        
    return jsonify({'results': results})



@app.route("/analytics")
def analytics():
    # Check if we have weekly rankings table populated
    has_rankings_row, _ = get_db_data("SELECT 1 FROM show_weekly_rankings LIMIT 1")
    use_rankings_table = bool(has_rankings_row)

    available_weeks = []
    selected_week = None

    if use_rankings_table:
        weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
        def sort_weeks_key(w_code):
            import re
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key, reverse=True)
        
        selected_week = request.args.get("week")
        if not selected_week and available_weeks:
            selected_week = available_weeks[0]

    # Fallback default if not set or empty
    if not selected_week:
        selected_week = "WK-26,2026"

    # Query 1: Top 10 content
    if use_rankings_table:
        top_shows_rows, top_shows_cols = get_db_data("""
            SELECT s.title, w.reach, s.global_rating 
            FROM shows s 
            JOIN show_weekly_rankings w ON s.id = w.show_id 
            WHERE w.week = %s 
              AND w.current_rank IS NOT NULL 
              AND (w.content_type IS NULL OR LOWER(w.content_type) != 'sports')
            ORDER BY w.current_rank ASC 
            LIMIT 10
        """, (selected_week,))
    else:
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
    top_shows = sorted(top_shows, key=lambda x: x['reach'], reverse=True)

    # Query 2: Platform distribution
    if use_rankings_table:
        platform_rows, platform_cols = get_db_data("""
            SELECT w.platform, COUNT(*) as count 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.platform IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.platform 
            ORDER BY count DESC
        """, (selected_week,))
    else:
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

    # Query 2b: Format distribution by reach
    if use_rankings_table:
        format_rows, _ = get_db_data("""
            SELECT w.content_format, SUM(w.reach) as total_reach 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.content_format IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.content_format 
            ORDER BY total_reach DESC
        """, (selected_week,))
    else:
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

    # Query 3: Genre reach
    if use_rankings_table:
        genre_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, g.genre 
            FROM show_weekly_rankings w 
            JOIN show_genres g ON w.show_id = g.show_id 
            WHERE w.week = %s AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
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

    # Query 4: Language reach
    if use_rankings_table:
        lang_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, s.languages 
            FROM show_weekly_rankings w 
            JOIN shows s ON w.show_id = s.id 
            WHERE w.week = %s AND s.languages IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
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

    # Load metadata from metadata.json
    metadata = {
        "time_period": "WK-26, 2026 ( 27 Jun 2026 - 3 Jul 2026 )",
        "market": "ALL INDIA"
    }
    if os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                # If nested week dictionary
                if selected_week in loaded_meta:
                    metadata = loaded_meta[selected_week]
                # Fallback for old single-week metadata format
                elif "time_period" in loaded_meta:
                    metadata = loaded_meta
        except Exception as e:
            print(f"Warning: Could not read metadata.json: {e}")

    return render_template(
        "analytics.html", 
        top_shows=top_shows, 
        platforms=platforms, 
        formats_by_reach=formats_by_reach,
        genre_percentages=genre_percentages, 
        lang_percentages=lang_percentages,
        metadata=metadata,
        available_weeks=available_weeks,
        selected_week=selected_week
    )


@app.route("/api/analytics")
def api_analytics_json():
    # Check if we have weekly rankings table populated
    has_rankings_row, _ = get_db_data("SELECT 1 FROM show_weekly_rankings LIMIT 1")
    use_rankings_table = bool(has_rankings_row)

    available_weeks = []
    selected_week = None

    if use_rankings_table:
        weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
        def sort_weeks_key(w_code):
            import re
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key, reverse=True)
        
        selected_week = request.args.get("week")
        if not selected_week and available_weeks:
            selected_week = available_weeks[0]

    # Fallback default if not set or empty
    if not selected_week:
        selected_week = "WK-26,2026"

    # Query 1: Top 10 content
    if use_rankings_table:
        top_shows_rows, top_shows_cols = get_db_data("""
            SELECT s.title, w.reach, s.global_rating 
            FROM shows s 
            JOIN show_weekly_rankings w ON s.id = w.show_id 
            WHERE w.week = %s 
              AND w.current_rank IS NOT NULL 
              AND (w.content_type IS NULL OR LOWER(w.content_type) != 'sports')
            ORDER BY w.current_rank ASC 
            LIMIT 10
        """, (selected_week,))
    else:
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
    top_shows = sorted(top_shows, key=lambda x: x['reach'], reverse=True)

    # Query 2: Platform distribution
    if use_rankings_table:
        platform_rows, platform_cols = get_db_data("""
            SELECT w.platform, COUNT(*) as count 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.platform IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.platform 
            ORDER BY count DESC
        """, (selected_week,))
    else:
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

    # Query 2b: Format distribution by reach
    if use_rankings_table:
        format_rows, _ = get_db_data("""
            SELECT w.content_format, SUM(w.reach) as total_reach 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.content_format IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.content_format 
            ORDER BY total_reach DESC
        """, (selected_week,))
    else:
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

    # Query 3: Genre reach
    if use_rankings_table:
        genre_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, g.genre 
            FROM show_weekly_rankings w 
            JOIN show_genres g ON w.show_id = g.show_id 
            WHERE w.week = %s AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
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

    # Query 4: Language reach
    if use_rankings_table:
        lang_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, s.languages 
            FROM show_weekly_rankings w 
            JOIN shows s ON w.show_id = s.id 
            WHERE w.week = %s AND s.languages IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
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

    # Load metadata from metadata.json
    metadata = {
        "time_period": "WK-26, 2026 ( 27 Jun 2026 - 3 Jul 2026 )",
        "market": "ALL INDIA"
    }
    if os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                # If nested week dictionary
                if selected_week in loaded_meta:
                    metadata = loaded_meta[selected_week]
                # Fallback for old single-week metadata format
                elif "time_period" in loaded_meta:
                    metadata = loaded_meta
        except Exception as e:
            print(f"Warning: Could not read metadata.json: {e}")

    return jsonify({
        'top_shows': top_shows,
        'platforms': platforms,
        'formats_by_reach': formats_by_reach,
        'genre_percentages': genre_percentages,
        'lang_percentages': lang_percentages,
        'metadata': metadata,
        'available_weeks': available_weeks,
        'selected_week': selected_week
    })


@app.route("/api/platform_analytics")
def api_platform_analytics():
    # 1. Total content count platform-wise
    plat_rows, _ = get_db_data("""
        SELECT platform, COUNT(*) as count 
        FROM shows 
        WHERE platform IS NOT NULL 
        GROUP BY platform 
        ORDER BY count DESC
    """)
    platforms = []
    for r in plat_rows:
        platforms.append({
            'platform': r[0],
            'count': int(r[1])
        })
        
    # 2. Paid vs Free count platform-wise
    paid_free_rows, _ = get_db_data("""
        SELECT platform, paid_free, COUNT(*) as count 
        FROM shows 
        WHERE platform IS NOT NULL AND paid_free IS NOT NULL 
        GROUP BY platform, paid_free
    """)
    
    paid_free_data = {}
    for r in paid_free_rows:
        plat = r[0]
        pf_type = r[1]
        count = int(r[2])
        if plat not in paid_free_data:
            paid_free_data[plat] = {'Paid': 0, 'Free': 0}
        
        if pf_type in ['Paid', 'Free']:
            paid_free_data[plat][pf_type] = count
        elif pf_type.lower() == 'paid':
            paid_free_data[plat]['Paid'] = count
        elif pf_type.lower() == 'free':
            paid_free_data[plat]['Free'] = count
            
    paid_free_list = []
    for plat, counts in paid_free_data.items():
        paid_free_list.append({
            'platform': plat,
            'Paid': counts['Paid'],
            'Free': counts['Free']
        })
        
    response = jsonify({
        'platforms': platforms,
        'paid_free': paid_free_list
    })
    response.headers['Cache-Control'] = 'public, max-age=300'  # cache 5 minutes
    return response


@app.route("/api/all_shows")
def api_all_shows():
    shows_rows, _ = get_db_data("SELECT id, title FROM shows ORDER BY title")
    shows = [{'id': r[0], 'title': r[1]} for r in shows_rows]
    return jsonify({'shows': shows})



@app.route("/api/trending_metadata")
def api_trending_metadata():
    weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
    def sort_weeks_key(w_code):
        import re
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
    available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key)
    
    latest_metadata = {
        "time_period": "Historical Trends",
        "market": "ALL INDIA"
    }
    if available_weeks and os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                latest_week = available_weeks[-1]
                if latest_week in loaded_meta:
                    latest_metadata = loaded_meta[latest_week]
                elif "time_period" in loaded_meta:
                    latest_metadata = loaded_meta
        except Exception:
            pass
            
    return jsonify({
        'weeks': available_weeks,
        'metadata': latest_metadata
    })


@app.route("/trending")
def trending():
    # Fetch all shows in the system to populate single show selection dropdown
    shows_rows, _ = get_db_data("SELECT id, title FROM shows ORDER BY title")
    shows = [{'id': r[0], 'title': r[1]} for r in shows_rows]
    
    # Load all available weeks
    weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
    def sort_weeks_key(w_code):
        import re
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
    available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key)
    
    # Find the latest week's metadata for display
    latest_metadata = {
        "time_period": "Historical Trends",
        "market": "ALL INDIA"
    }
    if available_weeks and os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                latest_week = available_weeks[-1]
                if latest_week in loaded_meta:
                    latest_metadata = loaded_meta[latest_week]
                elif "time_period" in loaded_meta:
                    latest_metadata = loaded_meta
        except Exception:
            pass
            
    return render_template("trending.html", shows=shows, weeks=available_weeks, metadata=latest_metadata)

@app.route("/api/show_trends")
def api_show_trends():
    show_id = request.args.get("show_id")
    if not show_id:
        return jsonify({'error': 'show_id is required'}), 400
        
    rows, _ = get_db_data("""
        SELECT week, current_rank, reach 
        FROM show_weekly_rankings 
        WHERE show_id = %s
    """, (show_id,))
    
    def sort_weeks_key(row):
        w_code = row[0]
        import re
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
        
    sorted_rows = sorted(rows, key=sort_weeks_key)
    
    weeks = [r[0] for r in sorted_rows]
    ranks = [int(r[1]) if r[1] is not None else None for r in sorted_rows]
    reach = [round(float(r[2]), 2) if r[2] is not None else 0.0 for r in sorted_rows]
    
    # Also fetch show title
    title_rows, _ = get_db_data("SELECT title FROM shows WHERE id = %s", (show_id,))
    title = title_rows[0][0] if title_rows else "Unknown Show"
    
    return jsonify({
        'title': title,
        'weeks': weeks,
        'ranks': ranks,
        'reach': reach
    })

@app.route("/api/content_trends")
def api_content_trends():
    # 1. Platform reach trends week-over-week
    plat_rows, _ = get_db_data("""
        SELECT week, platform, SUM(reach) as total_reach 
        FROM show_weekly_rankings 
        WHERE platform IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
        GROUP BY week, platform
    """)
    
    # 2. Format reach trends week-over-week
    format_rows, _ = get_db_data("""
        SELECT week, content_format, SUM(reach) as total_reach 
        FROM show_weekly_rankings 
        WHERE content_format IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
        GROUP BY week, content_format
    """)
    
    # Sort weeks helper
    def sort_weeks(w_list):
        def sort_weeks_key(w_code):
            import re
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        return sorted(list(set(w_list)), key=sort_weeks_key)
        
    # Process platforms
    plat_weeks = sort_weeks([r[0] for r in plat_rows])
    platforms = list(set([r[1] for r in plat_rows]))
    
    # Structure platforms: {platform: [val_w1, val_w2, ...]}
    plat_trends = {p: [0.0] * len(plat_weeks) for p in platforms}
    for week, platform, reach in plat_rows:
        if week in plat_weeks:
            w_idx = plat_weeks.index(week)
            plat_trends[platform][w_idx] = round(float(reach), 2)
            
    # Process formats
    form_weeks = sort_weeks([r[0] for r in format_rows])
    formats = list(set([r[1] for r in format_rows]))
    
    # Structure formats: {format: [val_w1, val_w2, ...]}
    form_trends = {f: [0.0] * len(form_weeks) for f in formats}
    for week, content_format, reach in format_rows:
        if week in form_weeks:
            w_idx = form_weeks.index(week)
            form_trends[content_format][w_idx] = round(float(reach), 2)
            
    return jsonify({
        'platforms': {
            'weeks': plat_weeks,
            'labels': platforms,
            'trends': plat_trends
        },
        'formats': {
            'weeks': form_weeks,
            'labels': formats,
            'trends': form_trends
        }
    })

@app.route("/api/genre_trends")
def api_genre_trends():
    # 1. Genre reach trends
    genre_rows, _ = get_db_data("""
        SELECT w.week, w.show_id, w.reach, g.genre 
        FROM show_weekly_rankings w 
        JOIN show_genres g ON w.show_id = g.show_id 
        WHERE w.reach IS NOT NULL AND w.current_rank IS NOT NULL
    """)
    
    # 2. Language reach trends
    lang_rows, _ = get_db_data("""
        SELECT w.week, w.show_id, w.reach, s.languages 
        FROM show_weekly_rankings w 
        JOIN shows s ON w.show_id = s.id 
        WHERE w.reach IS NOT NULL AND w.current_rank IS NOT NULL AND s.languages IS NOT NULL
    """)
    
    # Sort weeks helper
    def sort_weeks(w_list):
        def sort_weeks_key(w_code):
            import re
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        return sorted(list(set(w_list)), key=sort_weeks_key)
        
    # Process Genres: We group genres per week by show reach mapping
    # A single show reach is added to all its genres
    weeks_set = set()
    weekly_genre_totals = {} # {week: {genre: total_reach}}
    
    for week, show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        weeks_set.add(week)
        if week not in weekly_genre_totals:
            weekly_genre_totals[week] = {}
        
    show_genres_by_week = {}
    for week, show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        weeks_set.add(week)
        if week not in show_genres_by_week:
            show_genres_by_week[week] = {}
        if show_id not in show_genres_by_week[week]:
            show_genres_by_week[week][show_id] = (float(reach), set())
        show_genres_by_week[week][show_id][1].add(norm_genre)
        
    genre_weeks = sort_weeks(list(weeks_set))
    all_genres = set()
    
    weekly_genre_shares = {w: {} for w in genre_weeks}
    for week in genre_weeks:
        if week in show_genres_by_week:
            for show_id, (reach, genres) in show_genres_by_week[week].items():
                for genre in genres:
                    all_genres.add(genre)
                    weekly_genre_shares[week][genre] = weekly_genre_shares[week].get(genre, 0.0) + reach
                    
    genres_list = sorted(list(all_genres))
    genre_trends = {g: [0.0] * len(genre_weeks) for g in genres_list}
    for w_idx, week in enumerate(genre_weeks):
        total_week_reach = sum(weekly_genre_shares[week].values())
        if total_week_reach > 0:
            for genre in genres_list:
                share_pct = (weekly_genre_shares[week].get(genre, 0.0) / total_week_reach) * 100
                genre_trends[genre][w_idx] = round(share_pct, 2)

    # Process Languages:
    show_langs_by_week = {}
    lang_weeks_set = set()
    for week, show_id, reach, languages_str in lang_rows:
        if not languages_str:
            continue
        lang_weeks_set.add(week)
        parts = languages_str.split(',')
        unique_langs = set()
        for p in parts:
            lang = p.strip().title()
            if lang:
                unique_langs.add(lang)
        if week not in show_langs_by_week:
            show_langs_by_week[week] = {}
        show_langs_by_week[week][show_id] = (float(reach), unique_langs)
        
    lang_weeks = sort_weeks(list(lang_weeks_set))
    all_langs = set()
    
    weekly_lang_shares = {w: {} for w in lang_weeks}
    for week in lang_weeks:
        if week in show_langs_by_week:
            for show_id, (reach, langs) in show_langs_by_week[week].items():
                for lang in langs:
                    all_langs.add(lang)
                    weekly_lang_shares[week][lang] = weekly_lang_shares[week].get(lang, 0.0) + reach
                    
    langs_list = sorted(list(all_langs))
    lang_trends = {l: [0.0] * len(lang_weeks) for l in langs_list}
    for w_idx, week in enumerate(lang_weeks):
        total_week_reach = sum(weekly_lang_shares[week].values())
        if total_week_reach > 0:
            for lang in langs_list:
                share_pct = (weekly_lang_shares[week].get(lang, 0.0) / total_week_reach) * 100
                lang_trends[lang][w_idx] = round(share_pct, 2)
                
    return jsonify({
        'genres': {
            'weeks': genre_weeks,
            'labels': genres_list,
            'trends': genre_trends
        },
        'languages': {
            'weeks': lang_weeks,
            'labels': langs_list,
            'trends': lang_trends
        }
    })


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

# Ensure tables exist on startup (runs under Gunicorn/Render WSGI workers)
try:
    db.init_db()
except Exception as e:
    print(f"Failed to initialize database on startup: {e}")

# Clean up any stale lock file on startup
if os.path.exists("scraper.lock"):
    try:
        os.remove("scraper.lock")
    except Exception:
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )