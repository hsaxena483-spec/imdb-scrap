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
            ORDER BY title ASC 
            LIMIT %s OFFSET %s
            """
            if is_sqlite:
                query = query.replace("ILIKE", "LIKE").replace("%s", "?")
            cursor.execute(query, (f"%{search_q}%", per_page, offset))
        else:
            query = """
            SELECT id, title, type, release_year, current_rank, platform, play_url 
            FROM shows 
            ORDER BY title ASC 
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
        SELECT id, title, type, release_year, current_rank, platform, plot, poster_url, creators, stars, play_url, trailer_url
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
            "genres": genres
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
            
        # Update play_url and trailer_url
        update_query = "UPDATE shows SET play_url = %s, trailer_url = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        if is_sqlite:
            update_query = update_query.replace("%s", "?")
        cursor.execute(update_query, (play_url if play_url else None, trailer_url if trailer_url else None, show_id))
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
