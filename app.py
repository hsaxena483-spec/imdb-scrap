import os
import urllib.parse
from flask import Flask, request, make_response, g
from config import basedir
import db

app = Flask(__name__)

# Register blueprints
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.shows import shows_bp
from routes.trends import trends_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(shows_bp)
app.register_blueprint(trends_bp)

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

@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

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