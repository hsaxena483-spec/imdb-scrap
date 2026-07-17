"""
Backfill creators, stars, and certificate for all shows currently missing them.
Re-scrapes only the main title page (NOT ratings/reviews) to save time.
"""
import time, json, random
import db
from scraper import init_driver, get_next_data

def backfill():
    conn, is_sqlite = db.get_connection()
    cur = conn.cursor()

    # Get shows missing creators OR stars
    cur.execute("""
        SELECT id, title FROM shows
        WHERE (creators IS NULL OR creators = '')
           OR (stars IS NULL OR stars = '')
        ORDER BY id
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Shows to backfill: {total}")

    driver = init_driver()
    try:
        for i, (show_id, title) in enumerate(rows, 1):
            print(f"\n[{i}/{total}] {title} ({show_id})")

            url = f"https://www.imdb.com/title/{show_id}/"
            next_data = get_next_data(driver, url)

            if not next_data:
                print(f"  Skipping — no JSON data")
                continue

            page_props = next_data.get('props', {}).get('pageProps', {})
            above_fold = page_props.get('aboveTheFoldData', {})

            creators_list = []
            stars_list = []

            # Primary: principalCreditsV2 (grouping.text)
            for credit in above_fold.get('principalCreditsV2', []):
                grouping_text = credit.get('grouping', {}).get('text', '').lower()
                names = [c.get('name', {}).get('nameText', {}).get('text', '') for c in credit.get('credits', [])]
                names = [n for n in names if n]
                if 'creator' in grouping_text or 'director' in grouping_text or 'writer' in grouping_text:
                    creators_list.extend(names)
                elif 'star' in grouping_text or 'cast' in grouping_text or 'actor' in grouping_text:
                    stars_list.extend(names)

            # Fallback: mainColumnData principalCredits
            if not creators_list and not stars_list:
                main_col = page_props.get('mainColumnData', {})
                for credit in main_col.get('principalCredits', []):
                    category = credit.get('category', {}).get('text', '').lower()
                    names = [c.get('name', {}).get('nameText', {}).get('text', '') for c in credit.get('credits', [])]
                    names = [n for n in names if n]
                    if 'creator' in category or 'director' in category or 'writer' in category:
                        creators_list.extend(names)
                    elif 'star' in category or 'cast' in category or 'actor' in category:
                        stars_list.extend(names)

            # Also get certificate if missing
            cert_obj = above_fold.get('certificate', {})
            certificate = cert_obj.get('rating') if cert_obj else None

            creators_str = ', '.join(creators_list) if creators_list else None
            stars_str    = ', '.join(stars_list) if stars_list else None

            print(f"  creators: {creators_str}")
            print(f"  stars:    {stars_str}")
            print(f"  cert:     {certificate}")

            if creators_str or stars_str or certificate:
                cur.execute("""
                    UPDATE shows SET
                        creators = COALESCE(%s, creators),
                        stars     = COALESCE(%s, stars),
                        certificate = COALESCE(%s, certificate)
                    WHERE id = %s
                """, (creators_str, stars_str, certificate, show_id))
                conn.commit()
                print(f"  ✓ Saved")
            else:
                print(f"  ✗ Nothing found")

    finally:
        driver.quit()
        conn.close()
        print("\nBackfill complete!")

if __name__ == "__main__":
    backfill()
