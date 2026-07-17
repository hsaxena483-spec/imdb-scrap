"""
Fix all duplicate/inconsistent platform, language, content_type, content_format data in the DB.
Also clean up show_genres table for genre duplicates.
"""
import db

# ─────────────────────────────────────────────────────────────────────
# CANONICAL MAPPINGS
# ─────────────────────────────────────────────────────────────────────

PLATFORM_MAP = {
    "amazon mx player":   "Amazon MX Player",
    "amazon mxplayer":    "Amazon MX Player",
    "amazon prime video": "Amazon Prime Video",
    "amazon prime":       "Amazon Prime Video",
    "apple tv":           "Apple TV",
    "apple tv+":          "Apple TV+",
    "appletv":            "Apple TV",
    "jio hotstar":        "JioHotstar",
    "jiohotstar":         "JioHotstar",
    "jio cinema":         "JioCinema",
    "jiocinema":          "JioCinema",
    "sony liv":           "SonyLIV",
    "sonyliv":            "SonyLIV",
    "sony":               "SonyLIV",
    "zee5":               "ZEE5",
    "zee 5":              "ZEE5",
    "netflix":            "Netflix",
    "hoichoi":            "Hoichoi",
    "shemaroo me":        "Shemaroo Me",
    "manorama max":       "Manorama Max",
    "lionsgate play":     "Lionsgate Play",
    "zee tv":             "Zee TV",
    "star plus":          "Star Plus",
    "sun tv":             "Sun TV",
    "colors tv":          "Colors TV",
    "colors":             "Colors TV",
}

LANGUAGE_MAP = {
    "hindi":       "Hindi",
    "hinidi":      "Hindi",
    "english":     "English",
    "telugu":      "Telugu",
    "tamil":       "Tamil",
    "kannada":     "Kannada",
    "malayalam":   "Malayalam",
    "bengali":     "Bengali",
    "marathi":     "Marathi",
    "punjabi":     "Punjabi",
    "odia":        "Odia",
    "odiya":       "Odia",
    "gujarati":    "Gujarati",
    "bhojpuri":    "Bhojpuri",
    "haryanvi":    "Haryanvi",
    "harayanvi":   "Haryanvi",
    "haraynavi":   "Haryanvi",
    "korean":      "Korean",
    "japanese":    "Japanese",
    "spanish":     "Spanish",
    "french":      "French",
    "arabic":      "Arabic",
    "turkish":     "Turkish",
    "indonesian":  "Indonesian",
    "thai":        "Thai",
    "portuguese":  "Portuguese",
}

CONTENT_TYPE_MAP = {
    "live":        "Live",
    "movies":      "Movies",
    "shows":       "Shows",
    "sport":       "Sport",
    "sports":      "Sport",
    "tv catchup":  "TV CatchUp",
    "tv catch-up": "TV CatchUp",
    "tv catch up": "TV CatchUp",
    "tv catchup":  "TV CatchUp",
}

CONTENT_FORMAT_MAP = {
    "avod originals shows":  "AVOD Originals Shows",
    "svod originals shows":  "SVOD Originals Shows",
    "svod originals movies": "SVOD Originals Movies",
    "theatrical movies":     "Theatrical Movies",
    "theatrical releases":   "Theatrical Movies",
    "tv catch-up":           "TV Catch-Up",
    "tv catchup":            "TV Catch-Up",
    "live event":            "Live Event",
}

GENRE_MAP = {
    "adeventure": "Adventure",
    "adevnture":  "Adventure",
    "adventure":  "Adventure",
    "action":     "Action",
    "comedy":     "Comedy",
    "drama":      "Drama",
    "thriller":   "Thriller",
    "romance":    "Romance",
    "horror":     "Horror",
    "sci-fi":     "Sci-Fi",
    "scifi":      "Sci-Fi",
    "science fiction": "Sci-Fi",
    "animation":  "Animation",
    "biography":  "Biography",
    "biographical": "Biography",
    "biopic":     "Biography",
    "crime":      "Crime",
    "mystery":    "Mystery",
    "family":     "Family",
    "fantasy":    "Fantasy",
    "history":    "History",
    "historical": "History",
    "sport":      "Sport",
    "sports":     "Sport",
    "documentary": "Documentary",
    "reality":    "Reality",
    "reality tv": "Reality",
    "talk show":  "Talk Show",
    "talk-show":  "Talk Show",
    "music":      "Music",
    "musical":    "Music",
    "war":        "War",
    "western":    "Western",
    "superhero":  "Superhero",
    "kids":       "Kids",
    "children":   "Kids",
    "short":      "Short",
    "news":       "News",
}


def normalize_field(val, mapping):
    if not val:
        return val
    return mapping.get(val.strip().lower(), val.strip())


def normalize_languages(raw):
    """Normalize a comma-separated language string, dedup, sort."""
    if not raw:
        return raw
    items = [x.strip() for x in raw.split(",") if x.strip()]
    cleaned = []
    seen = set()
    for item in items:
        canonical = LANGUAGE_MAP.get(item.lower(), item.strip())
        key = canonical.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(canonical)
    return ", ".join(sorted(cleaned))


def fix_shows_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, platform, languages, content_type, content_format FROM shows")
    rows = cur.fetchall()
    updated = 0
    for row in rows:
        show_id, platform, languages, content_type, content_format = row
        new_platform       = normalize_field(platform, PLATFORM_MAP)
        new_languages      = normalize_languages(languages)
        new_content_type   = normalize_field(content_type, CONTENT_TYPE_MAP)
        new_content_format = normalize_field(content_format, CONTENT_FORMAT_MAP)

        if (new_platform != platform or new_languages != languages or
                new_content_type != content_type or new_content_format != content_format):
            cur.execute(
                "UPDATE shows SET platform=%s, languages=%s, content_type=%s, content_format=%s WHERE id=%s",
                (new_platform, new_languages, new_content_type, new_content_format, show_id)
            )
            updated += 1

    conn.commit()
    print(f"[shows] Updated {updated} rows.")


def fix_weekly_rankings_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT show_id, week, platform, content_type, content_format FROM show_weekly_rankings")
    rows = cur.fetchall()
    updated = 0
    for row in rows:
        show_id, week, platform, content_type, content_format = row
        new_platform       = normalize_field(platform, PLATFORM_MAP)
        new_content_type   = normalize_field(content_type, CONTENT_TYPE_MAP)
        new_content_format = normalize_field(content_format, CONTENT_FORMAT_MAP)

        if (new_platform != platform or
                new_content_type != content_type or new_content_format != content_format):
            cur.execute(
                "UPDATE show_weekly_rankings SET platform=%s, content_type=%s, content_format=%s WHERE show_id=%s AND week=%s",
                (new_platform, new_content_type, new_content_format, show_id, week)
            )
            updated += 1

    conn.commit()
    print(f"[show_weekly_rankings] Updated {updated} rows.")


def fix_show_genres_table(conn):
    """Normalize genre names and remove duplicates per show."""
    cur = conn.cursor()
    cur.execute("SELECT show_id, genre FROM show_genres")
    rows = cur.fetchall()

    # Group by show_id
    by_show = {}
    for show_id, genre in rows:
        by_show.setdefault(show_id, []).append(genre)

    updated_shows = 0
    for show_id, raw_genres in by_show.items():
        cleaned = {}
        for g in raw_genres:
            if not g:
                continue
            canonical = GENRE_MAP.get(g.strip().lower(), g.strip().title())
            key = canonical.lower()
            cleaned[key] = canonical  # dedup by lowercase key

        # Delete all existing genres for this show and re-insert clean ones
        cur.execute("DELETE FROM show_genres WHERE show_id=%s", (show_id,))
        for canonical in cleaned.values():
            cur.execute("INSERT INTO show_genres (show_id, genre) VALUES (%s, %s)", (show_id, canonical))
        updated_shows += 1

    conn.commit()
    print(f"[show_genres] Cleaned genres for {updated_shows} shows.")


def audit(conn):
    cur = conn.cursor()
    print("\n=== PLATFORMS ===")
    cur.execute("SELECT DISTINCT platform FROM shows ORDER BY platform")
    for r in cur.fetchall():
        print(" ", r[0])

    print("\n=== CONTENT_TYPE ===")
    cur.execute("SELECT DISTINCT content_type FROM shows ORDER BY content_type")
    for r in cur.fetchall():
        print(" ", r[0])

    print("\n=== CONTENT_FORMAT ===")
    cur.execute("SELECT DISTINCT content_format FROM shows ORDER BY content_format")
    for r in cur.fetchall():
        print(" ", r[0])

    print("\n=== GENRES ===")
    cur.execute("SELECT DISTINCT genre FROM show_genres ORDER BY genre")
    for r in cur.fetchall():
        print(" ", r[0])

    print("\n=== LANGUAGES (distinct raw) ===")
    cur.execute("SELECT DISTINCT languages FROM shows WHERE languages IS NOT NULL ORDER BY languages")
    lang_set = set()
    for r in cur.fetchall():
        for l in r[0].split(","):
            lang_set.add(l.strip())
    for l in sorted(lang_set):
        print(" ", l)


if __name__ == "__main__":
    conn, is_sqlite = db.get_connection()

    print("1) Fixing shows table...")
    fix_shows_table(conn)

    print("2) Fixing show_weekly_rankings table...")
    fix_weekly_rankings_table(conn)

    print("3) Fixing show_genres table...")
    fix_show_genres_table(conn)

    print("\n--- AUDIT AFTER FIX ---")
    audit(conn)

    conn.close()
    print("\nAll done!")
