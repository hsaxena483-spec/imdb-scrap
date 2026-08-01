import os
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv

# Load environment variables relative to this directory
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

JWT_SECRET = os.getenv("JWT_SECRET", "supersecret_jwt_signing_key")
token_serializer = URLSafeTimedSerializer(JWT_SECRET)

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
