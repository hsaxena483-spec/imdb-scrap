import os
import requests
from flask import Blueprint, request, jsonify, g
from config import token_serializer
from decorators import requires_auth
from db import get_db, get_user, upsert_user, update_user_profile

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/api/auth/google", methods=["POST"])
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
        existing_user = get_user(conn, is_sqlite, user_id)
        
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
        
        upsert_user(conn, is_sqlite, user_data)
        
        # Generate session token (valid for 30 days)
        session_token = token_serializer.dumps(user_id)
        
        return jsonify({
            "token": session_token,
            "user": user_data
        }), 200
        
    except Exception as e:
        print(f"Error in google_auth: {e}")
        return jsonify({"error": "Authentication failed", "details": str(e)}), 500

@auth_bp.route("/api/auth/me", methods=["GET"])
@requires_auth
def get_me():
    return jsonify(g.current_user), 200

@auth_bp.route("/api/auth/profile", methods=["PUT"])
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
        
        update_user_profile(conn, is_sqlite, g.current_user["id"], profile_data)
        
        # Fetch the updated user details
        updated_user = get_user(conn, is_sqlite, g.current_user["id"])
        
        return jsonify(updated_user), 200
    except Exception as e:
        print(f"Error in update_profile: {e}")
        return jsonify({"error": "Failed to update profile", "details": str(e)}), 500

@auth_bp.route("/api/admin/login", methods=["POST"])
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
            if db_password_hash and check_password_hash(db_password_hash, password) and db_role in ["admin", "superadmin", "super admin"]:
                token = token_serializer.dumps(email, salt="admin-auth")
                return jsonify({
                    "token": token,
                    "email": email,
                    "role": db_role
                }), 200
        
        return jsonify({"error": "Invalid admin email or password"}), 401
    except Exception as e:
        print(f"Error in admin_login: {e}")
        return jsonify({"error": "Failed to complete login transaction", "details": str(e)}), 500
