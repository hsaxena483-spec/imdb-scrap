import os
import uuid
import threading
from flask import Blueprint, request, jsonify, g
from decorators import requires_admin_auth
from db import get_db
from config import basedir
import scraper

admin_bp = Blueprint('admin', __name__)

@admin_bp.route("/api/admin/stats", methods=["GET"])
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

@admin_bp.route("/api/admin/users", methods=["GET"])
@requires_admin_auth
def admin_get_users():
    if g.current_admin != "superadmin@cott.com":
        return jsonify({"error": "Forbidden: Only super admin can access users directory"}), 403
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = """
        SELECT id, email, name, picture, phone_number, user_role, is_active, account_type, plan_status, allowed_weeks, created_at 
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
                "allowed_weeks": r[9],
                "created_at": r[10].isoformat() if r[10] and hasattr(r[10], 'isoformat') else str(r[10])
            })
        return jsonify(users), 200
    except Exception as e:
        print(f"Error in admin_get_users: {e}")
        return jsonify({"error": "Failed to fetch users", "details": str(e)}), 500

@admin_bp.route("/api/admin/users/<user_id>/access", methods=["PUT"])
@requires_admin_auth
def admin_update_user_access(user_id):
    if g.current_admin != "superadmin@cott.com":
        return jsonify({"error": "Forbidden: Only super admin can modify user access"}), 403
    data = request.get_json() or {}
    allowed_weeks = data.get("allowed_weeks")
    if allowed_weeks is not None:
        try:
            allowed_weeks = int(allowed_weeks)
            if allowed_weeks <= 0:
                allowed_weeks = None
        except (ValueError, TypeError):
            return jsonify({"error": "allowed_weeks must be a positive integer or null"}), 400

    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = "UPDATE users SET allowed_weeks = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        if is_sqlite:
            query = query.replace("%s", "?")
        cursor.execute(query, (allowed_weeks, user_id))
        conn.commit()
        conn.close()
        return jsonify({
            "success": True,
            "user_id": user_id,
            "allowed_weeks": allowed_weeks,
            "message": f"Updated week access: {'All Weeks (Default)' if allowed_weeks is None else f'Latest {allowed_weeks} Weeks'}"
        }), 200
    except Exception as e:
        print(f"Error updating user access: {e}")
        return jsonify({"error": "Failed to update user access", "details": str(e)}), 500

@admin_bp.route("/api/admin/upload-excel", methods=["POST"])
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

def _serialize_job(row):
    import datetime
    
    created_at_val = row[6]
    updated_at_val = row[7]
    created_at_ts = None
    updated_at_ts = None
    
    if created_at_val:
        if isinstance(created_at_val, datetime.datetime):
            created_at_ts = created_at_val.timestamp()
        elif isinstance(created_at_val, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    created_at_ts = datetime.datetime.strptime(created_at_val, fmt).timestamp()
                    break
                except ValueError:
                    continue
                    
    if updated_at_val:
        if isinstance(updated_at_val, datetime.datetime):
            updated_at_ts = updated_at_val.timestamp()
        elif isinstance(updated_at_val, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    updated_at_ts = datetime.datetime.strptime(updated_at_val, fmt).timestamp()
                    break
                except ValueError:
                    continue
                    
    return {
        "id": row[0],
        "status": row[1],
        "total_shows": row[2],
        "processed_shows": row[3],
        "current_show": row[4],
        "error_message": row[5],
        "created_at": row[6].isoformat() if row[6] and hasattr(row[6], 'isoformat') else str(row[6]),
        "updated_at": row[7].isoformat() if row[7] and hasattr(row[7], 'isoformat') else str(row[7]),
        "created_at_ts": created_at_ts,
        "updated_at_ts": updated_at_ts
    }

@admin_bp.route("/api/admin/scraping-job/latest", methods=["GET"])
@requires_admin_auth
def admin_get_latest_job():
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        query = """
        SELECT id, status, total_shows, processed_shows, current_show, error_message, created_at, updated_at 
        FROM scraping_jobs 
        ORDER BY id DESC LIMIT 1
        """
        cursor.execute(query)
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"message": "No jobs found"}), 404
            
        return jsonify(_serialize_job(row)), 200
    except Exception as e:
        print(f"Error fetching latest job: {e}")
        return jsonify({"error": "Failed to fetch latest job", "details": str(e)}), 500

@admin_bp.route("/api/admin/scraping-job/<int:job_id>", methods=["GET"])
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
            
        return jsonify(_serialize_job(row)), 200
    except Exception as e:
        print(f"Error fetching job status: {e}")
        return jsonify({"error": "Failed to fetch job status", "details": str(e)}), 500

@admin_bp.route("/api/admin/scraping-job/<int:job_id>/pause", methods=["POST"])
@requires_admin_auth
def admin_pause_job(job_id):
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # Check current status
        query_check = "SELECT status FROM scraping_jobs WHERE id = %s"
        if is_sqlite:
            query_check = query_check.replace("%s", "?")
        cursor.execute(query_check, (job_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Job not found"}), 404
            
        status = row[0]
        if status != "running":
            conn.close()
            return jsonify({"error": f"Cannot pause job in status '{status}'"}), 400
            
        query_update = "UPDATE scraping_jobs SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        if is_sqlite:
            query_update = query_update.replace("%s", "?")
        cursor.execute(query_update, (job_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Job paused successfully", "status": "paused"}), 200
    except Exception as e:
        print(f"Error pausing job: {e}")
        return jsonify({"error": "Failed to pause job", "details": str(e)}), 500

@admin_bp.route("/api/admin/scraping-job/<int:job_id>/resume", methods=["POST"])
@requires_admin_auth
def admin_resume_job(job_id):
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # Check current status
        query_check = "SELECT status FROM scraping_jobs WHERE id = %s"
        if is_sqlite:
            query_check = query_check.replace("%s", "?")
        cursor.execute(query_check, (job_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Job not found"}), 404
            
        status = row[0]
        if status != "paused":
            conn.close()
            return jsonify({"error": f"Cannot resume job in status '{status}'"}), 400
            
        query_update = "UPDATE scraping_jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        if is_sqlite:
            query_update = query_update.replace("%s", "?")
        cursor.execute(query_update, (job_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Job resumed successfully", "status": "running"}), 200
    except Exception as e:
        print(f"Error resuming job: {e}")
        return jsonify({"error": "Failed to resume job", "details": str(e)}), 500

@admin_bp.route("/api/admin/scraping-job/<int:job_id>/cancel", methods=["POST"])
@requires_admin_auth
def admin_cancel_job(job_id):
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # Check current status
        query_check = "SELECT status FROM scraping_jobs WHERE id = %s"
        if is_sqlite:
            query_check = query_check.replace("%s", "?")
        cursor.execute(query_check, (job_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Job not found"}), 404
            
        status = row[0]
        if status not in ["pending", "running", "paused"]:
            conn.close()
            return jsonify({"error": f"Cannot cancel job in status '{status}'"}), 400
            
        query_update = "UPDATE scraping_jobs SET status = 'cancelled', current_show = 'Cancelled by user', updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        if is_sqlite:
            query_update = query_update.replace("%s", "?")
        cursor.execute(query_update, (job_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Job cancelled successfully", "status": "cancelled"}), 200
    except Exception as e:
        print(f"Error cancelling job: {e}")
        return jsonify({"error": "Failed to cancel job", "details": str(e)}), 500

@admin_bp.route("/api/admin/test-selenium", methods=["GET"])
@requires_admin_auth
def admin_test_selenium():
    try:
        print("Testing Selenium initialization on server...")
        driver = scraper.init_driver()
        print("Selenium initialized successfully. Fetching a test page...")
        driver.get("https://www.google.com")
        title = driver.title
        driver.quit()
        return jsonify({"status": "success", "page_title": title}), 200
    except Exception as e:
        print(f"Selenium test failed: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 500

@admin_bp.route("/api/admin/shows", methods=["GET"])
@requires_admin_auth
def admin_get_shows():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        search_q = request.args.get('q', '').strip()
        
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # Count total items
        if search_q:
            count_query = "SELECT COUNT(*) FROM shows WHERE title ILIKE %s"
            if is_sqlite:
                count_query = count_query.replace("ILIKE", "LIKE").replace("%s", "?")
            cursor.execute(count_query, (f"%{search_q}%",))
        else:
            count_query = "SELECT COUNT(*) FROM shows"
            cursor.execute(count_query)
        total_items = cursor.fetchone()[0]
        
        # Fetch shows
        if search_q:
            query = """
            SELECT id, title, type, release_year, current_rank, platform, play_url 
            FROM shows 
            WHERE title ILIKE %s 
            ORDER BY CASE WHEN current_rank IS NULL THEN 1 ELSE 0 END, current_rank ASC, title ASC 
            LIMIT %s OFFSET %s
            """
            if is_sqlite:
                query = query.replace("ILIKE", "LIKE").replace("%s", "?")
            cursor.execute(query, (f"%{search_q}%", per_page, offset))
        else:
            query = """
            SELECT id, title, type, release_year, current_rank, platform, play_url 
            FROM shows 
            ORDER BY CASE WHEN current_rank IS NULL THEN 1 ELSE 0 END, current_rank ASC, title ASC 
            LIMIT %s OFFSET %s
            """
            if is_sqlite:
                query = query.replace("%s", "?")
            cursor.execute(query, (per_page, offset))
            
        rows = cursor.fetchall()
        conn.close()
        
        shows = []
        for r in rows:
            shows.append({
                "id": r[0],
                "title": r[1],
                "type": r[2],
                "release_year": r[3],
                "current_rank": r[4],
                "platform": r[5],
                "play_url": r[6]
            })
            
        return jsonify({
            "shows": shows,
            "total": total_items,
            "page": page,
            "per_page": per_page
        }), 200
    except Exception as e:
        print(f"Error in admin_get_shows: {e}")
        return jsonify({"error": "Failed to fetch shows", "details": str(e)}), 500

@admin_bp.route("/api/admin/shows/<show_id>", methods=["GET"])
@requires_admin_auth
def admin_get_show_details(show_id):
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        query = """
        SELECT id, title, type, release_year, current_rank, platform, plot, poster_url, creators, stars, 
               play_url, trailer_url, global_rating, global_vote_count, runtime_seconds,
               reach, total_time_spent, f_under_18, f_18_24, f_25_35, f_35_plus,
               m_under_18, m_18_24, m_25_35, m_35_plus, female, male,
               week, market, content_format, paid_free, content_type, languages
        FROM shows 
        WHERE id = %s
        """
        if is_sqlite:
            query = query.replace("%s", "?")
        cursor.execute(query, (show_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return jsonify({"error": "Show not found"}), 404
            
        # Fetch genres
        genre_query = "SELECT genre FROM show_genres WHERE show_id = %s"
        if is_sqlite:
            genre_query = genre_query.replace("%s", "?")
        cursor.execute(genre_query, (show_id,))
        genres = [r[0] for r in cursor.fetchall()]
        
        # Fetch reviews
        reviews_query = """
        SELECT id, author_username, rating, summary, content 
        FROM show_reviews 
        WHERE show_id = %s
        ORDER BY submission_date DESC
        """
        if is_sqlite:
            reviews_query = reviews_query.replace("%s", "?")
        cursor.execute(reviews_query, (show_id,))
        reviews_rows = cursor.fetchall()
        
        reviews = []
        for r in reviews_rows:
            reviews.append({
                "id": r[0],
                "author_username": r[1] or "Anonymous",
                "rating": r[2],
                "summary": r[3] or "",
                "content": r[4] or ""
            })
            
        conn.close()
        
        show_details = {
            "id": row[0],
            "title": row[1],
            "type": row[2],
            "release_year": row[3],
            "current_rank": row[4],
            "platform": row[5],
            "plot": row[6],
            "poster_url": row[7],
            "creators": row[8],
            "stars": row[9],
            "play_url": row[10],
            "trailer_url": row[11],
            "global_rating": float(row[12]) if row[12] is not None else None,
            "global_vote_count": row[13],
            "runtime_seconds": row[14],
            "reach": float(row[15]) if row[15] is not None else None,
            "total_time_spent": float(row[16]) if row[16] is not None else None,
            "f_under_18": float(row[17]) if row[17] is not None else None,
            "f_18_24": float(row[18]) if row[18] is not None else None,
            "f_25_35": float(row[19]) if row[19] is not None else None,
            "f_35_plus": float(row[20]) if row[20] is not None else None,
            "m_under_18": float(row[21]) if row[21] is not None else None,
            "m_18_24": float(row[22]) if row[22] is not None else None,
            "m_25_35": float(row[23]) if row[23] is not None else None,
            "m_35_plus": float(row[24]) if row[24] is not None else None,
            "female": float(row[25]) if row[25] is not None else None,
            "male": float(row[26]) if row[26] is not None else None,
            "week": row[27],
            "market": row[28],
            "content_format": row[29],
            "paid_free": row[30],
            "content_type": row[31],
            "languages": row[32],
            "genres": genres,
            "reviews": reviews
        }
        return jsonify(show_details), 200
    except Exception as e:
        print(f"Error in admin_get_show_details: {e}")
        return jsonify({"error": "Failed to fetch show details", "details": str(e)}), 500

@admin_bp.route("/api/admin/shows/<show_id>/play-url", methods=["PUT"])
@requires_admin_auth
def admin_update_play_url(show_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    play_url = data.get("play_url", "").strip()
    trailer_url = data.get("trailer_url", "").strip()
    
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # Check if show exists
        check_query = "SELECT COUNT(*) FROM shows WHERE id = %s"
        if is_sqlite:
            check_query = check_query.replace("%s", "?")
        cursor.execute(check_query, (show_id,))
        if cursor.fetchone()[0] == 0:
            conn.close()
            return jsonify({"error": "Show not found"}), 404
            
        # Get admin user ID from email
        user_query = "SELECT id FROM users WHERE email = %s"
        if is_sqlite:
            user_query = user_query.replace("%s", "?")
        cursor.execute(user_query, (g.current_admin,))
        user_row = cursor.fetchone()
        user_id = user_row[0] if user_row else g.current_admin
        
        # Update play_url, trailer_url, and updated_by
        update_query = "UPDATE shows SET play_url = %s, trailer_url = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        if is_sqlite:
            update_query = update_query.replace("%s", "?")
        cursor.execute(update_query, (play_url if play_url else None, trailer_url if trailer_url else None, user_id, show_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            "message": "Streaming details updated successfully", 
            "play_url": play_url,
            "trailer_url": trailer_url
        }), 200
    except Exception as e:
        print(f"Error in admin_update_play_url: {e}")
        return jsonify({"error": "Failed to update streaming details", "details": str(e)}), 500

@admin_bp.route("/api/admin/shows/<show_id>", methods=["PUT"])
@requires_admin_auth
def admin_update_show_details(show_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    title = data.get("title", "").strip()
    show_type = data.get("type", "").strip()
    
    try:
        release_year = int(data.get("release_year")) if data.get("release_year") is not None and str(data.get("release_year")).strip() != "" else None
    except ValueError:
        release_year = None

    try:
        current_rank = int(data.get("current_rank")) if data.get("current_rank") is not None and str(data.get("current_rank")).strip() != "" else None
    except ValueError:
        current_rank = None

    try:
        global_rating = float(data.get("global_rating")) if data.get("global_rating") is not None and str(data.get("global_rating")).strip() != "" else None
    except ValueError:
        global_rating = None

    try:
        global_vote_count = int(data.get("global_vote_count")) if data.get("global_vote_count") is not None and str(data.get("global_vote_count")).strip() != "" else None
    except ValueError:
        global_vote_count = None

    try:
        runtime_mins = int(data.get("runtime_mins")) if data.get("runtime_mins") is not None and str(data.get("runtime_mins")).strip() != "" else None
        runtime_seconds = runtime_mins * 60 if runtime_mins is not None else None
    except ValueError:
        runtime_seconds = None

    def parse_optional_float(key):
        val = data.get(key)
        if val is None or str(val).strip() == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    reach = parse_optional_float("reach")
    total_time_spent = parse_optional_float("total_time_spent")
    f_under_18 = parse_optional_float("f_under_18")
    f_18_24 = parse_optional_float("f_18_24")
    f_25_35 = parse_optional_float("f_25_35")
    f_35_plus = parse_optional_float("f_35_plus")
    m_under_18 = parse_optional_float("m_under_18")
    m_18_24 = parse_optional_float("m_18_24")
    m_25_35 = parse_optional_float("m_25_35")
    m_35_plus = parse_optional_float("m_35_plus")
    female = parse_optional_float("female")
    male = parse_optional_float("male")

    platform = data.get("platform", "").strip()
    plot = data.get("plot", "").strip()
    poster_url = data.get("poster_url", "").strip()
    creators = data.get("creators", "").strip()
    stars = data.get("stars", "").strip()
    play_url = data.get("play_url", "").strip()
    trailer_url = data.get("trailer_url", "").strip()
    genres = data.get("genres", [])
    reviews = data.get("reviews", [])
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
        
    try:
        conn, is_sqlite = get_db()
        cursor = conn.cursor()
        
        # Check if show exists and fetch its current week
        check_query = "SELECT week FROM shows WHERE id = %s"
        if is_sqlite:
            check_query = check_query.replace("%s", "?")
        cursor.execute(check_query, (show_id,))
        show_row = cursor.fetchone()
        if not show_row:
            conn.close()
            return jsonify({"error": "Show not found"}), 404
        current_week = show_row[0]
            
        # Get admin user ID from email
        user_query = "SELECT id FROM users WHERE email = %s"
        if is_sqlite:
            user_query = user_query.replace("%s", "?")
        cursor.execute(user_query, (g.current_admin,))
        user_row = cursor.fetchone()
        user_id = user_row[0] if user_row else g.current_admin
        
        # Update shows table (use COALESCE for COTT/demographic fields so existing values are never wiped if omitted)
        update_query = """
        UPDATE shows 
        SET title = %s, type = %s, release_year = %s, current_rank = %s, platform = %s, 
            plot = %s, poster_url = %s, creators = %s, stars = %s, play_url = %s, 
            trailer_url = %s, global_rating = %s, global_vote_count = %s, runtime_seconds = %s,
            reach = COALESCE(%s, reach),
            total_time_spent = COALESCE(%s, total_time_spent),
            f_under_18 = COALESCE(%s, f_under_18),
            f_18_24 = COALESCE(%s, f_18_24),
            f_25_35 = COALESCE(%s, f_25_35),
            f_35_plus = COALESCE(%s, f_35_plus),
            m_under_18 = COALESCE(%s, m_under_18),
            m_18_24 = COALESCE(%s, m_18_24),
            m_25_35 = COALESCE(%s, m_25_35),
            m_35_plus = COALESCE(%s, m_35_plus),
            female = COALESCE(%s, female),
            male = COALESCE(%s, male),
            updated_by = %s, updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
        """
        if is_sqlite:
            update_query = update_query.replace("%s", "?")
            
        cursor.execute(update_query, (
            title, 
            show_type if show_type else None, 
            release_year, 
            current_rank, 
            platform if platform else None, 
            plot if plot else None, 
            poster_url if poster_url else None, 
            creators if creators else None, 
            stars if stars else None, 
            play_url if play_url else None, 
            trailer_url if trailer_url else None, 
            global_rating,
            global_vote_count,
            runtime_seconds,
            reach,
            total_time_spent,
            f_under_18,
            f_18_24,
            f_25_35,
            f_35_plus,
            m_under_18,
            m_18_24,
            m_25_35,
            m_35_plus,
            female,
            male,
            user_id,
            show_id
        ))
        
        # Keep show_weekly_rankings in sync for the show's current week if present
        if current_week:
            update_wr_query = """
            UPDATE show_weekly_rankings
            SET current_rank = COALESCE(%s, current_rank),
                reach = COALESCE(%s, reach),
                total_time_spent = COALESCE(%s, total_time_spent),
                f_under_18 = COALESCE(%s, f_under_18),
                f_18_24 = COALESCE(%s, f_18_24),
                f_25_35 = COALESCE(%s, f_25_35),
                f_35_plus = COALESCE(%s, f_35_plus),
                m_under_18 = COALESCE(%s, m_under_18),
                m_18_24 = COALESCE(%s, m_18_24),
                m_25_35 = COALESCE(%s, m_25_35),
                m_35_plus = COALESCE(%s, m_35_plus),
                female = COALESCE(%s, female),
                male = COALESCE(%s, male)
            WHERE show_id = %s AND week = %s
            """
            if is_sqlite:
                update_wr_query = update_wr_query.replace("%s", "?")
            cursor.execute(update_wr_query, (
                current_rank, reach, total_time_spent,
                f_under_18, f_18_24, f_25_35, f_35_plus,
                m_under_18, m_18_24, m_25_35, m_35_plus,
                female, male, show_id, current_week
            ))
        
        # Update genres
        delete_genres_query = "DELETE FROM show_genres WHERE show_id = %s"
        if is_sqlite:
            delete_genres_query = delete_genres_query.replace("%s", "?")
        cursor.execute(delete_genres_query, (show_id,))
        
        if isinstance(genres, list) and len(genres) > 0:
            insert_genre_query = """
            INSERT INTO show_genres (show_id, genre)
            VALUES (%s, %s)
            """
            if is_sqlite:
                insert_genre_query = insert_genre_query.replace("%s", "?")
                
            from config import normalize_genre
            for genre in genres:
                if genre:
                    clean_genre = normalize_genre(genre.strip())
                    if clean_genre:
                        try:
                            cursor.execute(insert_genre_query, (show_id, clean_genre))
                        except Exception:
                            pass
                            
        # Update reviews
        submitted_review_ids = [r.get("id") for r in reviews if r.get("id")]
        
        if submitted_review_ids:
            placeholders = ",".join(["%s"] * len(submitted_review_ids))
            delete_reviews_query = f"DELETE FROM show_reviews WHERE show_id = %s AND id NOT IN ({placeholders})"
            if is_sqlite:
                delete_reviews_query = delete_reviews_query.replace("%s", "?")
            cursor.execute(delete_reviews_query, (show_id, *submitted_review_ids))
        else:
            delete_reviews_query = "DELETE FROM show_reviews WHERE show_id = %s"
            if is_sqlite:
                delete_reviews_query = delete_reviews_query.replace("%s", "?")
            cursor.execute(delete_reviews_query, (show_id,))
            
        import uuid
        for r in reviews:
            rev_id = r.get("id")
            author = r.get("author_username", "").strip() or "Anonymous"
            rev_rating = r.get("rating")
            try:
                rev_rating = int(rev_rating) if rev_rating is not None and str(rev_rating).strip() != "" else None
            except ValueError:
                rev_rating = None
            summary = r.get("summary", "").strip()
            content = r.get("content", "").strip()
            
            if not summary and not content:
                continue
                
            if rev_id:
                update_rev_query = """
                UPDATE show_reviews 
                SET author_username = %s, rating = %s, summary = %s, content = %s 
                WHERE id = %s AND show_id = %s
                """
                if is_sqlite:
                    update_rev_query = update_rev_query.replace("%s", "?")
                cursor.execute(update_rev_query, (author, rev_rating, summary, content, rev_id, show_id))
            else:
                new_id = f"rev_{uuid.uuid4().hex[:12]}"
                insert_rev_query = """
                INSERT INTO show_reviews (id, show_id, author_username, rating, summary, content, submission_date)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE)
                """
                if is_sqlite:
                    insert_rev_query = insert_rev_query.replace("%s", "?")
                cursor.execute(insert_rev_query, (new_id, show_id, author, rev_rating, summary, content))
                            
        conn.commit()
        conn.close()
        
        return jsonify({
            "message": "Show details updated successfully"
        }), 200
    except Exception as e:
        print(f"Error in admin_update_show_details: {e}")
        return jsonify({"error": "Failed to update show details", "details": str(e)}), 500

@admin_bp.route("/api/admin/upload-image", methods=["POST"])
@requires_admin_auth
def admin_upload_image():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if not file:
        return jsonify({"error": "File is empty"}), 400
        
    try:
        # Retrieve ImageKit credentials from environment
        private_key = os.environ.get("IMAGEKIT_PRIVATE_KEY")
        
        if not private_key:
            return jsonify({"error": "ImageKit private key not configured on server"}), 500
            
        import requests
        # Prepare the files and data for ImageKit
        file_bytes = file.read()
        
        files = {
            'file': (file.filename, file_bytes, file.content_type)
        }
        data = {
            'fileName': file.filename,
            'folder': '/cott-posters'
        }
        
        # Call ImageKit upload API
        response = requests.post(
            'https://upload.imagekit.io/api/v1/files/upload',
            files=files,
            data=data,
            auth=(private_key, '')
        )
        
        if response.status_code != 200:
            try:
                err_details = response.json()
            except Exception:
                err_details = response.text
            return jsonify({
                "error": "Failed to upload image to ImageKit",
                "details": err_details
            }), response.status_code
            
        res_data = response.json()
        image_url = res_data.get("url")
        
        return jsonify({
            "message": "Image uploaded successfully to ImageKit",
            "url": image_url
        }), 200
        
    except Exception as e:
        print(f"Error in admin_upload_image: {e}")
        return jsonify({"error": "Failed to process image upload", "details": str(e)}), 500

