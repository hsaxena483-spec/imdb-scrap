import os
import sqlite3
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load environment variables relative to db.py directory
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

DB_TYPE = os.getenv("DB_TYPE", "postgresql").lower()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "imdb_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def normalize_platform(name):
    if not name:
        return ""
    p = str(name).strip().lower()
    mapping = {
        "zee5": "ZEE5",
        "sonyliv": "SonyLIV",
        "sony liv": "SonyLIV",
        "jiohotstar": "JioHotstar",
        "jio hotstar": "JioHotstar",
        "netflix": "Netflix",
        "hoichoi": "Hoichoi",
        "lionsgate play": "Lionsgate Play",
        "manorama max": "Manorama Max",
        "shemaroo me": "Shemaroo Me",
        "shemaroome": "Shemaroo Me",
        "amazon prime video": "Amazon Prime Video",
        "prime video": "Amazon Prime Video",
        "disney+ hotstar": "Disney+ Hotstar",
        "disney+hotstar": "Disney+ Hotstar",
        "disney hotstar": "Disney+ Hotstar",
        "hotstar": "Disney+ Hotstar",
        "disney+": "Disney+",
        "aha": "Aha",
        "sun nxt": "Sun NXT",
        "sunnxt": "Sun NXT",
        "altbalaji": "AltBalaji",
        "mx player": "MX Player",
        "mxplayer": "MX Player",
        "amazon mx player": "Amazon MX Player",
        "amazon mxplayer": "Amazon MX Player",
        "apple tv": "Apple TV",
        "eros now": "Eros Now",
        "erosnow": "Eros Now",
        "youtube": "YouTube"
    }
    return mapping.get(p, str(name).strip().title())

def normalize_paid_free(val):
    if not val:
        return ""
    v = str(val).strip().lower()
    if "free" in v:
        return "Free"
    if "paid" in v:
        return "Paid"
    return str(val).strip().title()

def normalize_content_format(val):
    if not val:
        return ""
    v = str(val).strip().lower()
    if "shows/live content" in v or "shows/live" in v or "show/live" in v:
        return "Shows/Live Content"
    return str(val).strip().title()

def normalize_content_type(val):
    if not val:
        return ""
    v = str(val).strip().lower()
    if v in ["show", "shows"]:
        return "Show"
    if v in ["movie", "movies"]:
        return "Movie"
    if v in ["sport", "sports"]:
        return "Sports"
    if v in ["tv catchup", "tv-catchup", "tvcatchup"]:
        return "TV Catchup"
    return str(val).strip().title()

def normalize_market(val):
    if not val:
        return "ALL INDIA"
    v = str(val).strip().upper()
    if v in ["ALL INDIA", "ALL-INDIA", "INDIA"]:
        return "ALL INDIA"
    return str(val).strip().upper()

def normalize_languages(val):
    if not val:
        return ""
    langs = [l.strip().title() for l in str(val).split(",") if l.strip()]
    cleaned = []
    for l in langs:
        if l.lower() == "english":
            cleaned.append("English")
        else:
            cleaned.append(l)
    return ", ".join(cleaned)

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
            conn = psycopg2.connect(db_url, connect_timeout=15)
            print("Successfully connected to PostgreSQL database using DATABASE_URL.")
        else:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=15
            )
            print(f"Successfully connected to PostgreSQL database '{DB_NAME}' at {DB_HOST}:{DB_PORT}.")
            
        # Set database query statement timeout to 30 seconds
        try:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = 30000;")
        except Exception as timeout_err:
            print(f"Warning: Failed to set PostgreSQL statement_timeout: {timeout_err}")
            
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
            play_url VARCHAR(500),
            trailer_url VARCHAR(500),
            total_time_spent NUMERIC(15, 5),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Alter table to add trailer_url column if database already exists
        try:
            execute_query(conn, is_sqlite, "ALTER TABLE shows ADD COLUMN trailer_url VARCHAR(500)")
            conn.commit()
            print("Successfully added trailer_url column to shows table")
        except Exception as alter_err:
            # Ignored if column already exists
            print(f"trailer_url column not added (may already exist): {alter_err}")
        
        # Alter table to add play_url column if database already exists
        try:
            execute_query(conn, is_sqlite, "ALTER TABLE shows ADD COLUMN play_url VARCHAR(500)")
            conn.commit()
            print("Successfully added play_url column to shows table")
        except Exception as alter_err:
            # Ignored if column already exists
            print(f"play_url column not added (may already exist): {alter_err}")

        # Alter table to add total_time_spent column if database already exists
        try:
            execute_query(conn, is_sqlite, "ALTER TABLE shows ADD COLUMN total_time_spent NUMERIC(15, 5)")
            conn.commit()
            print("Successfully added total_time_spent column to shows table")
        except Exception as alter_err:
            # Ignored if column already exists
            print(f"total_time_spent column not added (may already exist): {alter_err}")
        
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

        # 6. Create show_weekly_rankings table
        print("Creating table: show_weekly_rankings...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS show_weekly_rankings (
            show_id VARCHAR(15) REFERENCES shows(id) ON DELETE CASCADE,
            week VARCHAR(50),
            current_rank INTEGER,
            reach NUMERIC(10, 5),
            platform VARCHAR(100),
            content_format VARCHAR(100),
            paid_free VARCHAR(20),
            content_type VARCHAR(50),
            market VARCHAR(50),
            total_time_spent NUMERIC(15, 5),
            PRIMARY KEY (show_id, week)
        );
        """)

        # Alter table to add total_time_spent column if database already exists
        try:
            execute_query(conn, is_sqlite, "ALTER TABLE show_weekly_rankings ADD COLUMN total_time_spent NUMERIC(15, 5)")
            conn.commit()
            print("Successfully added total_time_spent column to show_weekly_rankings table")
        except Exception as alter_err:
            # Ignored if column already exists
            print(f"total_time_spent column not added to show_weekly_rankings (may already exist): {alter_err}")

        # 7. Create users table
        print("Creating table: users...")
        execute_query(conn, is_sqlite, """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(255) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255),
            picture VARCHAR(500),
            phone_number VARCHAR(20),
            user_role VARCHAR(50) DEFAULT 'normal user',
            is_active BOOLEAN DEFAULT TRUE,
            account_type VARCHAR(50) DEFAULT 'free',
            plan_status VARCHAR(50) DEFAULT 'none',
            password VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Alter table to add password column if database already exists
        try:
            execute_query(conn, is_sqlite, "ALTER TABLE users ADD COLUMN password VARCHAR(255)")
            conn.commit()
            print("Successfully added password column to users table")
        except Exception as alter_err:
            # Ignored if column already exists
            print(f"Password column not added (may already exist): {alter_err}")

        # Seed the admin user if not exists
        try:
            from werkzeug.security import generate_password_hash
            hashed_pw = generate_password_hash("cott@123")
            hashed_super_pw = generate_password_hash("Supercott@123")
            
            # Check if admin@cott.com exists
            cursor = conn.cursor()
            query = "SELECT COUNT(*) FROM users WHERE email = %s"
            if is_sqlite:
                query = query.replace("%s", "?")
            cursor.execute(query, ("admin@cott.com",))
            admin_exists = cursor.fetchone()[0] > 0
            
            if not admin_exists:
                print("Seeding admin user into database...")
                insert_query = """
                INSERT INTO users (id, email, name, password, user_role, account_type, plan_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                if is_sqlite:
                    insert_query = insert_query.replace("%s", "?")
                cursor.execute(insert_query, (
                    "admin-cott",
                    "admin@cott.com",
                    "Admin",
                    hashed_pw,
                    "admin",
                    "paid",
                    "active"
                ))
                conn.commit()
                print("Admin user seeded successfully!")
            else:
                # Update password/role if they are not set or outdated
                update_query = """
                UPDATE users 
                SET password = %s, user_role = %s
                WHERE email = %s
                """
                if is_sqlite:
                    update_query = update_query.replace("%s", "?")
                cursor.execute(update_query, (hashed_pw, "admin", "admin@cott.com"))
                conn.commit()
                print("Admin user password/role updated successfully in DB.")
            
            # Seed the superadmin user if not exists
            cursor.execute(query, ("superadmin@cott.com",))
            superadmin_exists = cursor.fetchone()[0] > 0
            
            if not superadmin_exists:
                print("Seeding superadmin user into database...")
                insert_query = """
                INSERT INTO users (id, email, name, password, user_role, account_type, plan_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                if is_sqlite:
                    insert_query = insert_query.replace("%s", "?")
                cursor.execute(insert_query, (
                    "superadmin-cott",
                    "superadmin@cott.com",
                    "Super Admin",
                    hashed_super_pw,
                    "superadmin",
                    "paid",
                    "active"
                ))
                conn.commit()
                print("Superadmin user seeded successfully!")
            else:
                # Update password/role if they are not set or outdated
                update_query = """
                UPDATE users 
                SET password = %s, user_role = %s
                WHERE email = %s
                """
                if is_sqlite:
                    update_query = update_query.replace("%s", "?")
                cursor.execute(update_query, (hashed_super_pw, "superadmin", "superadmin@cott.com"))
                conn.commit()
                print("Superadmin user password/role updated successfully in DB.")
                
            cursor.close()
        except Exception as seed_err:
            print(f"Error seeding admin/superadmin user: {seed_err}")

        # 8. Create scraping_jobs table
        print("Creating table: scraping_jobs...")
        create_jobs_sql = """
        CREATE TABLE IF NOT EXISTS scraping_jobs (
            id SERIAL PRIMARY KEY,
            status VARCHAR(50) DEFAULT 'pending',
            total_shows INTEGER DEFAULT 0,
            processed_shows INTEGER DEFAULT 0,
            current_show VARCHAR(255),
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        if is_sqlite:
            conn.commit()
            
        print("Database initialized successfully.")
        
        # Run cleanup and standardization
        try:
            cleanup_and_standardize_data(conn, is_sqlite)
        except Exception as clean_err:
            print(f"Error standardizing data on startup: {clean_err}")
            
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise e
    finally:
        conn.close()

def cleanup_and_standardize_data(conn, is_sqlite):
    """
    Standardizes existing records in the shows, show_genres, and platform_gender tables,
    converting platforms, languages, formats, paid/free tags, content types,
    and genres to a single normalized casing style to eliminate duplicates.
    """
    cursor = conn.cursor()
    
    # 1. Standardize shows table columns
    cursor.execute("SELECT id, platform, content_format, paid_free, content_type, languages, market FROM shows")
    rows = cursor.fetchall()
    
    updates = []
    for r in rows:
        show_id, platform, content_format, paid_free, content_type, languages, market = r
        
        clean_platform = normalize_platform(platform) if platform else None
        clean_format = normalize_content_format(content_format) if content_format else None
        clean_paid_free = normalize_paid_free(paid_free) if paid_free else None
        clean_content_type = normalize_content_type(content_type) if content_type else None
        clean_languages = normalize_languages(languages) if languages else None
        clean_market = normalize_market(market) if market else "ALL INDIA"
        
        if (clean_platform != platform or 
            clean_format != content_format or 
            clean_paid_free != paid_free or 
            clean_content_type != content_type or 
            clean_languages != languages or 
            clean_market != market):
            
            updates.append((clean_platform, clean_format, clean_paid_free, clean_content_type, clean_languages, clean_market, show_id))
            
    if updates:
        print(f"Cleaning up {len(updates)} shows records with legacy casings...")
        update_query = """
        UPDATE shows SET 
            platform = %s, 
            content_format = %s, 
            paid_free = %s, 
            content_type = %s, 
            languages = %s, 
            market = %s 
        WHERE id = %s
        """
        if is_sqlite:
            update_query = update_query.replace("%s", "?")
            
        for u in updates:
            cursor.execute(update_query, u)
        conn.commit()
        
    # 2. Standardize show_genres table
    cursor.execute("SELECT show_id, genre FROM show_genres")
    genre_rows = cursor.fetchall()
    
    genre_updates = []
    genres_to_delete = []
    seen = set()
    
    from config import normalize_genre
    for show_id, genre in genre_rows:
        clean_genre = normalize_genre(genre)
        if clean_genre in ['Sport', 'Sports']:
            genres_to_delete.append((show_id, genre))
            continue
            
        key = (show_id, clean_genre)
        if key in seen:
            genres_to_delete.append((show_id, genre))
        else:
            seen.add(key)
            if clean_genre != genre:
                genre_updates.append((clean_genre, show_id, genre))
                
    if genres_to_delete:
        print(f"Deleting {len(genres_to_delete)} duplicate/invalid genre entries...")
        delete_query = "DELETE FROM show_genres WHERE show_id = %s AND genre = %s"
        if is_sqlite:
            delete_query = delete_query.replace("%s", "?")
        for d in genres_to_delete:
            cursor.execute(delete_query, d)
        conn.commit()
        
    if genre_updates:
        print(f"Standardizing {len(genre_updates)} genre labels in the database...")
        update_genre_query = "UPDATE show_genres SET genre = %s WHERE show_id = %s AND genre = %s"
        if is_sqlite:
            update_genre_query = update_genre_query.replace("%s", "?")
        for g in genre_updates:
            try:
                cursor.execute(update_genre_query, g)
            except Exception as e:
                print(f"Error standardizing genre: {e}. Deleting duplicate.")
                fallback_delete = "DELETE FROM show_genres WHERE show_id = %s AND genre = %s"
                if is_sqlite:
                    fallback_delete = fallback_delete.replace("%s", "?")
                cursor.execute(fallback_delete, (g[1], g[2]))
        conn.commit()

    # 3. Standardize platform_gender table
    cursor.execute("SELECT platform, total_reach, male_pct, female_pct FROM platform_gender")
    pg_rows = cursor.fetchall()
    
    pg_groups = {}
    for platform, total_reach, male_pct, female_pct in pg_rows:
        norm_p = normalize_platform(platform)
        if norm_p not in pg_groups:
            pg_groups[norm_p] = []
        pg_groups[norm_p].append({
            'original': platform,
            'reach': float(total_reach) if total_reach else 0.0,
            'male': float(male_pct) if male_pct else 0.0,
            'female': float(female_pct) if female_pct else 0.0
        })
        
    for norm_p, items in pg_groups.items():
        if len(items) > 1 or items[0]['original'] != norm_p:
            avg_reach = max(i['reach'] for i in items)
            avg_male = sum(i['male'] for i in items) / len(items)
            avg_female = sum(i['female'] for i in items) / len(items)
            
            delete_pg = "DELETE FROM platform_gender WHERE platform = %s"
            if is_sqlite:
                delete_pg = delete_pg.replace("%s", "?")
            for i in items:
                cursor.execute(delete_pg, (i['original'],))
            conn.commit()
            
            insert_pg = "INSERT INTO platform_gender (platform, total_reach, male_pct, female_pct) VALUES (%s, %s, %s, %s)"
            if is_sqlite:
                insert_pg = insert_pg.replace("%s", "?")
            cursor.execute(insert_pg, (norm_p, avg_reach, avg_male, avg_female))
            conn.commit()

    # 4. Standardize show_weekly_rankings table
    cursor.execute("SELECT show_id, week, platform, content_format, paid_free, content_type, market FROM show_weekly_rankings")
    ranking_rows = cursor.fetchall()
    
    ranking_updates = []
    for r in ranking_rows:
        show_id, week, platform, content_format, paid_free, content_type, market = r
        
        clean_platform = normalize_platform(platform) if platform else None
        clean_format = normalize_content_format(content_format) if content_format else None
        clean_paid_free = normalize_paid_free(paid_free) if paid_free else None
        clean_content_type = normalize_content_type(content_type) if content_type else None
        clean_market = normalize_market(market) if market else "ALL INDIA"
        
        if (clean_platform != platform or 
            clean_format != content_format or 
            clean_paid_free != paid_free or 
            clean_content_type != content_type or 
            clean_market != market):
            
            ranking_updates.append((clean_platform, clean_format, clean_paid_free, clean_content_type, clean_market, show_id, week))
            
    if ranking_updates:
        print(f"Cleaning up {len(ranking_updates)} show_weekly_rankings records with legacy casings...")
        update_ranking_query = """
        UPDATE show_weekly_rankings SET 
            platform = %s, 
            content_format = %s, 
            paid_free = %s, 
            content_type = %s, 
            market = %s 
        WHERE show_id = %s AND week = %s
        """
        if is_sqlite:
            update_ranking_query = update_ranking_query.replace("%s", "?")
            
        for u in ranking_updates:
            cursor.execute(update_ranking_query, u)
        conn.commit()

    cursor.close()

def save_show(conn, is_sqlite, show_data):
    """
    Saves or updates a show details row in the database.
    """
    query = """
    INSERT INTO shows (
        id, title, type, release_year, end_year, global_rating, global_vote_count,
        runtime_seconds, certificate, plot, poster_url, release_date, total_episodes,
        creators, stars, current_rank, platform, content_format, paid_free,
        content_type, languages, reach, week, market, total_time_spent, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
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
        total_time_spent = EXCLUDED.total_time_spent,
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
        normalize_platform(show_data.get('platform')) if show_data.get('platform') else None,
        normalize_content_format(show_data.get('content_format')) if show_data.get('content_format') else None,
        normalize_paid_free(show_data.get('paid_free')) if show_data.get('paid_free') else None,
        normalize_content_type(show_data.get('content_type')) if show_data.get('content_type') else None,
        normalize_languages(show_data.get('languages')) if show_data.get('languages') else None,
        show_data.get('reach'),
        show_data.get('week'),
        normalize_market(show_data.get('market')) if show_data.get('market') else "ALL INDIA",
        show_data.get('total_time_spent')
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
    from config import normalize_genre
    for genre in genres:
        if genre:
            clean_genre = normalize_genre(genre)
            if clean_genre and clean_genre not in ['Sport', 'Sports']:
                execute_query(conn, is_sqlite, query, (show_id, clean_genre))

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

def save_weekly_ranking(conn, is_sqlite, ranking_data):
    """
    Saves or updates a show's weekly ranking in the show_weekly_rankings table.
    """
    query = """
    INSERT INTO show_weekly_rankings (
        show_id, week, current_rank, reach, platform, content_format, paid_free, content_type, market, total_time_spent
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    ) ON CONFLICT (show_id, week) DO UPDATE SET
        current_rank = EXCLUDED.current_rank,
        reach = EXCLUDED.reach,
        platform = EXCLUDED.platform,
        content_format = EXCLUDED.content_format,
        paid_free = EXCLUDED.paid_free,
        content_type = EXCLUDED.content_type,
        market = EXCLUDED.market,
        total_time_spent = EXCLUDED.total_time_spent;
    """
    params = (
        ranking_data.get('show_id'),
        ranking_data.get('week'),
        ranking_data.get('current_rank'),
        ranking_data.get('reach'),
        normalize_platform(ranking_data.get('platform')) if ranking_data.get('platform') else None,
        normalize_content_format(ranking_data.get('content_format')) if ranking_data.get('content_format') else None,
        normalize_paid_free(ranking_data.get('paid_free')) if ranking_data.get('paid_free') else None,
        normalize_content_type(ranking_data.get('content_type')) if ranking_data.get('content_type') else None,
        normalize_market(ranking_data.get('market')) if ranking_data.get('market') else "ALL INDIA",
        ranking_data.get('total_time_spent')
    )
    execute_query(conn, is_sqlite, query, params)

def get_user(conn, is_sqlite, user_id):
    """
    Fetches a user by their Google subject ID.
    """
    query = "SELECT id, email, name, picture, phone_number, user_role, is_active, account_type, plan_status, created_at, updated_at FROM users WHERE id = %s"
    try:
        cursor = execute_query(conn, is_sqlite, query, (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
    except Exception as e:
        print(f"Warning: Error fetching user {user_id}: {e}")
    return None

def upsert_user(conn, is_sqlite, user_data):
    """
    Creates or updates user details upon successful Google Login.
    """
    query = """
    INSERT INTO users (
        id, email, name, picture, phone_number, user_role, is_active, account_type, plan_status, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
    ) ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        picture = EXCLUDED.picture,
        phone_number = COALESCE(EXCLUDED.phone_number, users.phone_number),
        updated_at = CURRENT_TIMESTAMP;
    """
    params = (
        user_data.get('id'),
        user_data.get('email'),
        user_data.get('name'),
        user_data.get('picture'),
        user_data.get('phone_number'),
        user_data.get('user_role', 'normal user'),
        user_data.get('is_active', True),
        user_data.get('account_type', 'free'),
        user_data.get('plan_status', 'none')
    )
    execute_query(conn, is_sqlite, query, params)
    conn.commit()

def update_user_profile(conn, is_sqlite, user_id, profile_data):
    """
    Updates the name and phone number for a user in the database.
    """
    query = "UPDATE users SET name = %s, phone_number = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
    params = (profile_data.get('name'), profile_data.get('phone_number'), user_id)
    execute_query(conn, is_sqlite, query, params)
    conn.commit()

def get_db():
    from flask import has_app_context, g
    if has_app_context():
        if 'db' not in g:
            g.db, g.is_sqlite = get_connection()
        return g.db, g.is_sqlite
    else:
        return get_connection()

def get_db_data(query, params=None):
    conn, is_sqlite = get_db()
    cursor = execute_query(conn, is_sqlite, query, params)
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    from flask import has_app_context
    if not has_app_context():
        cursor.close()
        conn.close()
    return rows, columns

if __name__ == "__main__":
    init_db()
