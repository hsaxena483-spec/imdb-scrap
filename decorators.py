from functools import wraps
from flask import request, jsonify, g
from itsdangerous import SignatureExpired, BadSignature
from config import token_serializer
from db import get_db, get_user

def requires_auth(f):
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
        user = get_user(conn, is_sqlite, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not user.get("is_active"):
            return jsonify({"error": "Account is inactive"}), 403
            
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def requires_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Admin authorization token is missing"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            # Admin token is valid for 7 days
            admin_email = token_serializer.loads(token, salt="admin-auth", max_age=7 * 24 * 3600)
            if admin_email not in ["admin@cott.com", "superadmin@cott.com"]:
                return jsonify({"error": "Unauthorized admin access"}), 403
        except SignatureExpired:
            return jsonify({"error": "Admin token has expired"}), 401
        except BadSignature:
            return jsonify({"error": "Invalid admin token"}), 401
            
        g.current_admin = admin_email
        return f(*args, **kwargs)
    return decorated

def get_current_user_from_request():
    """
    Safely inspects the Authorization header.
    Returns user dict if valid Bearer token, otherwise None.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.split(" ")[1]
    try:
        user_id = token_serializer.loads(token, max_age=30 * 24 * 3600)
        conn, is_sqlite = get_db()
        user = get_user(conn, is_sqlite, user_id)
        if user and user.get("is_active"):
            return user
    except Exception:
        pass
    return None

def get_allowed_weeks_for_request():
    """
    Returns (allowed_weeks_list, is_restricted).
    If user is not authenticated or allowed_weeks is NULL/None/0,
    returns (None, False), which means ALL WEEKS are allowed by default.
    If user has an integer limit (e.g. 4 or 8), returns (top_N_weeks, True).
    """
    user = get_current_user_from_request()
    if not user:
        return None, False
        
    allowed_weeks_limit = user.get("allowed_weeks")
    if allowed_weeks_limit is None:
        return None, False
    try:
        limit = int(allowed_weeks_limit)
        if limit <= 0:
            return None, False
    except (ValueError, TypeError):
        return None, False
        
    from db import get_db_data
    import re
    weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings WHERE week IS NOT NULL")
    raw_weeks = [r[0] for r in weeks_rows if r[0]]
    
    def sort_weeks_key(w_code):
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        return (int(match.group(2)), int(match.group(1))) if match else (0, 0)
        
    sorted_desc = sorted(raw_weeks, key=sort_weeks_key, reverse=True)
    return sorted_desc[:limit], True
