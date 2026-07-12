import os
import sqlite3
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "postgresql").lower()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "imdb_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_connection():
    """
    Attempts to connect to PostgreSQL. If configured to use SQLite,
    or if PostgreSQL connection fails, it falls back to SQLite.
    Returns:
        conn: The database connection object.
        is_sqlite: Boolean indicating if it's an SQLite connection.
    """
    if DB_TYPE == "sqlite":
        print("Using SQLite database as configured.")
        conn = sqlite3.connect("imdb.db")
        # Enable foreign keys in SQLite
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn, True
        
    try:
        # Try to connect to PostgreSQL
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            conn = psycopg2.connect(db_url)
            print("Successfully connected to PostgreSQL database using DATABASE_URL.")
        else:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print(f"Successfully connected to PostgreSQL database '{DB_NAME}' at {DB_HOST}:{DB_PORT}.")
        return conn, False
    except Exception as e:
        print(f"Warning: Failed to connect to PostgreSQL ({e}).")
        print("Falling back to local SQLite database ('imdb.db').")
        conn = sqlite3.connect("imdb.db")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn, True

def execute_query(conn, is_sqlite, query_template, params=None):
    """
    Executes a query by automatically adapting placeholders between %s (Postgres) and ? (SQLite).
    """
    if is_sqlite:
        query = query_template.replace("%s", "?")
    else:
        query = query_template
        
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    except Exception as e:
        conn.rollback()
        raise e

def init_db():
    """
    Initializes database tables for both PostgreSQL and SQLite.
    """
    conn, is_sqlite = get_connection()
    cursor = conn.cursor()
    
    # Enable autocommit for initial table creation
    if not is_sqlite:
        conn.autocommit = True
        
    try:
        # 1. Create shows table
        print("Creating table: shows...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS shows (
            id VARCHAR(15) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            type VARCHAR(50),
            release_year INTEGER,
            end_year INTEGER,
            global_rating NUMERIC(3, 1),
            global_vote_count INTEGER,
            runtime_seconds INTEGER,
            certificate VARCHAR(50),
            plot TEXT,
            poster_url VARCHAR(500),
            release_date DATE,
            total_episodes INTEGER,
            creators TEXT,
            stars TEXT,
            current_rank INTEGER,
            platform VARCHAR(100),
            content_format VARCHAR(100),
            paid_free VARCHAR(20),
            content_type VARCHAR(50),
            languages TEXT,
            reach NUMERIC(10, 5),
            week VARCHAR(50),
            market VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 2. Create show_genres table
        print("Creating table: show_genres...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS show_genres (
            show_id VARCHAR(15) REFERENCES shows(id) ON DELETE CASCADE,
            genre VARCHAR(50),
            PRIMARY KEY (show_id, genre)
        );
        """)
        
        # 3. Create show_country_ratings table
        print("Creating table: show_country_ratings...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS show_country_ratings (
            show_id VARCHAR(15) REFERENCES shows(id) ON DELETE CASCADE,
            country_code VARCHAR(10),
            country_name VARCHAR(100),
            rating NUMERIC(3, 1),
            vote_count INTEGER,
            PRIMARY KEY (show_id, country_code)
        );
        """)
        
        # 4. Create show_reviews table
        print("Creating table: show_reviews...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS show_reviews (
            id VARCHAR(50) PRIMARY KEY,
            show_id VARCHAR(15) REFERENCES shows(id) ON DELETE CASCADE,
            author_username VARCHAR(255),
            author_id VARCHAR(50),
            rating INTEGER,
            summary VARCHAR(500),
            content TEXT,
            submission_date DATE,
            up_votes INTEGER,
            down_votes INTEGER,
            is_spoiler BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 5. Create platform_gender table
        print("Creating table: platform_gender...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS platform_gender (
            platform VARCHAR(100) PRIMARY KEY,
            total_reach NUMERIC(10, 5),
            male_pct NUMERIC(5, 3),
            female_pct NUMERIC(5, 3)
        );
        """)
        
        if is_sqlite:
            conn.commit()
            
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise e
    finally:
        conn.close()

def save_show(conn, is_sqlite, show_data):
    """
    Saves or updates a show details row in the database.
    """
    query = """
    INSERT INTO shows (
        id, title, type, release_year, end_year, global_rating, global_vote_count,
        runtime_seconds, certificate, plot, poster_url, release_date, total_episodes,
        creators, stars, current_rank, platform, content_format, paid_free,
        content_type, languages, reach, week, market, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
    ) ON CONFLICT (id) DO UPDATE SET
        title = EXCLUDED.title,
        type = EXCLUDED.type,
        release_year = EXCLUDED.release_year,
        end_year = EXCLUDED.end_year,
        global_rating = EXCLUDED.global_rating,
        global_vote_count = EXCLUDED.global_vote_count,
        runtime_seconds = EXCLUDED.runtime_seconds,
        certificate = EXCLUDED.certificate,
        plot = EXCLUDED.plot,
        poster_url = EXCLUDED.poster_url,
        release_date = EXCLUDED.release_date,
        total_episodes = EXCLUDED.total_episodes,
        creators = EXCLUDED.creators,
        stars = EXCLUDED.stars,
        current_rank = EXCLUDED.current_rank,
        platform = EXCLUDED.platform,
        content_format = EXCLUDED.content_format,
        paid_free = EXCLUDED.paid_free,
        content_type = EXCLUDED.content_type,
        languages = EXCLUDED.languages,
        reach = EXCLUDED.reach,
        week = EXCLUDED.week,
        market = EXCLUDED.market,
        updated_at = CURRENT_TIMESTAMP;
    """
    params = (
        show_data.get('id'),
        show_data.get('title'),
        show_data.get('type'),
        show_data.get('release_year'),
        show_data.get('end_year'),
        show_data.get('global_rating'),
        show_data.get('global_vote_count'),
        show_data.get('runtime_seconds'),
        show_data.get('certificate'),
        show_data.get('plot'),
        show_data.get('poster_url'),
        show_data.get('release_date'),
        show_data.get('total_episodes'),
        show_data.get('creators'),
        show_data.get('stars'),
        show_data.get('current_rank'),
        show_data.get('platform'),
        show_data.get('content_format'),
        show_data.get('paid_free'),
        show_data.get('content_type'),
        show_data.get('languages'),
        show_data.get('reach'),
        show_data.get('week'),
        show_data.get('market')
    )
    execute_query(conn, is_sqlite, query, params)

def save_genres(conn, is_sqlite, show_id, genres):
    """
    Saves genres for a show. Duplicate values are ignored.
    """
    query = """
    INSERT INTO show_genres (show_id, genre)
    VALUES (%s, %s)
    ON CONFLICT (show_id, genre) DO NOTHING;
    """
    for genre in genres:
        if genre:
            execute_query(conn, is_sqlite, query, (show_id, genre))

def save_country_ratings(conn, is_sqlite, show_id, country_ratings):
    """
    Saves or updates ratings broken down by country.
    """
    query = """
    INSERT INTO show_country_ratings (show_id, country_code, country_name, rating, vote_count)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (show_id, country_code) DO UPDATE SET
        rating = EXCLUDED.rating,
        vote_count = EXCLUDED.vote_count;
    """
    for r in country_ratings:
        params = (
            show_id,
            r['country_code'],
            r['country_name'],
            r['rating'],
            r['vote_count']
        )
        execute_query(conn, is_sqlite, query, params)

def save_reviews(conn, is_sqlite, show_id, reviews):
    """
    Saves or updates user reviews.
    """
    query = """
    INSERT INTO show_reviews (
        id, show_id, author_username, author_id, rating, summary, content,
        submission_date, up_votes, down_votes, is_spoiler
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        rating = EXCLUDED.rating,
        summary = EXCLUDED.summary,
        content = EXCLUDED.content,
        up_votes = EXCLUDED.up_votes,
        down_votes = EXCLUDED.down_votes,
        is_spoiler = EXCLUDED.is_spoiler;
    """
    for r in reviews:
        params = (
            r['id'],
            show_id,
            r['author_username'],
            r['author_id'],
            r['rating'],
            r['summary'],
            r['content'],
            r['submission_date'],
            r['up_votes'],
            r['down_votes'],
            r['is_spoiler']
        )
        execute_query(conn, is_sqlite, query, params)

def clear_all_ranks(conn, is_sqlite):
    """
    Sets current_rank to NULL for all shows.
    """
    query = "UPDATE shows SET current_rank = NULL"
    execute_query(conn, is_sqlite, query)

def is_show_fresh(conn, is_sqlite, show_id):
    """
    Checks if a show exists and was updated within the last 24 hours.
    """
    if is_sqlite:
        query = "SELECT 1 FROM shows WHERE id = %s AND datetime(updated_at) >= datetime('now', '-24 hours')"
    else:
        query = "SELECT 1 FROM shows WHERE id = %s AND updated_at >= NOW() - INTERVAL '24 hours'"
        
    try:
        cursor = execute_query(conn, is_sqlite, query, (show_id,))
        res = cursor.fetchone()
        return res is not None
    except Exception as e:
        print(f"Warning: Error checking show freshness: {e}")
        return False

def save_platform_gender(conn, is_sqlite, data):
    query = """
    INSERT INTO platform_gender (platform, total_reach, male_pct, female_pct)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (platform) DO UPDATE SET
        total_reach = EXCLUDED.total_reach,
        male_pct = EXCLUDED.male_pct,
        female_pct = EXCLUDED.female_pct;
    """
    execute_query(conn, is_sqlite, query, (
        data['platform'], data['total_reach'], data['male_pct'], data['female_pct']
    ))

def get_all_platform_gender(conn, is_sqlite):
    query = "SELECT platform, total_reach, male_pct, female_pct FROM platform_gender ORDER BY total_reach DESC"
    cursor = execute_query(conn, is_sqlite, query)
    return cursor.fetchall()

if __name__ == "__main__":
    init_db()
