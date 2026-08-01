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
