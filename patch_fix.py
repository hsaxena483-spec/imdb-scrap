"""
cleanup_remaining.py
Fixes the 6 remaining shows with missing posters:
- Arafta Season 2 (xl_) is a duplicate of tt39013436 which already has data - just delete xl_
- Spider Man No Way Home / Hathras 16 days / Laziness Saves / Beinteha / Fevi IdeaLabs - retry scrape
"""
import sys, os, re, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import scraper, db

def fresh_conn():
    conn, is_sqlite = db.get_connection()
    return conn, is_sqlite

def fix_arafta_duplicate():
    """Arafta Season 2 (xl_) is a duplicate of tt39013436 which already has full data. Just delete the xl_ stub."""
    print("\n[FIX] Arafta Season 2 duplicate cleanup...")
    conn, is_sqlite = fresh_conn()
    cur = conn.cursor()
    try:
        # Migrate weekly rankings from xl_ to real id (if any)
        for table in ["show_genres", "show_country_ratings", "show_reviews", "show_weekly_rankings"]:
            q = f"UPDATE {table} SET show_id = 'tt39013436' WHERE show_id = 'xl_ad7db451ad'"
            if is_sqlite: q = q.replace("'tt39013436'", "?").replace("'xl_ad7db451ad'", "?")
            try:
                cur.execute(q if not is_sqlite else q, () if not is_sqlite else ('tt39013436', 'xl_ad7db451ad'))
            except Exception as e:
                print(f"  [warn] {table}: {e}")
                conn.rollback()
                cur = conn.cursor()

        # Delete the xl_ duplicate stub
        cur.execute("DELETE FROM shows WHERE id = 'xl_ad7db451ad'")
        conn.commit()
        print("  [OK] Deleted xl_ad7db451ad duplicate, tt39013436 retained with poster.")
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] {e}")
    finally:
        cur.close()
        conn.close()

def scrape_and_fix(driver, title, old_id, row):
    """Search IMDb, scrape and save for one title."""
    print(f"\n  Searching IMDb for '{title}'...")
    try:
        new_id = scraper.search_imdb_show(driver, title)
    except Exception as e:
        print(f"  [WARN] Search error ({e.__class__.__name__}), restarting driver...")
        try: driver.quit()
        except: pass
        driver = scraper.init_driver()
        try:
            new_id = scraper.search_imdb_show(driver, title)
        except Exception:
            new_id = None

    if not new_id:
        print(f"  [SKIP] No IMDb ID found for '{title}'.")
        return driver, False

    print(f"  Found: {new_id}")

    # Scrape detail/ratings/reviews
    detail_url = f"https://www.imdb.com/title/{new_id}/"
    detail_json = scraper.get_next_data(driver, detail_url)

    imdb_data, imdb_genres = {}, []
    if detail_json:
        page_props = detail_json.get("props", {}).get("pageProps", {})
        above_fold = page_props.get("aboveTheFoldData", {})
        if above_fold:
            ratings = above_fold.get("ratingsSummary", {})
            imdb_data["global_rating"] = ratings.get("aggregateRating")
            imdb_data["global_vote_count"] = ratings.get("voteCount")
            cert = above_fold.get("certificate", {})
            imdb_data["certificate"] = cert.get("rating") if cert else None
            runtime_obj = above_fold.get("runtime", {})
            imdb_data["runtime_seconds"] = runtime_obj.get("seconds") if runtime_obj else None
            ry = above_fold.get("releaseYear", {})
            imdb_data["release_year"] = ry.get("year") if ry else None
            imdb_data["end_year"] = ry.get("endYear") if ry else None
            tt = above_fold.get("titleType", {})
            imdb_data["type"] = tt.get("id") if tt else None
            plot_obj = above_fold.get("plot", {})
            if plot_obj:
                pt = plot_obj.get("plotText", {})
                imdb_data["plot"] = pt.get("plainText") if pt else None
            img = above_fold.get("primaryImage", {})
            imdb_data["poster_url"] = img.get("url") if img else None
            if not imdb_data["poster_url"] and detail_json.get("fallback_poster_url"):
                imdb_data["poster_url"] = detail_json["fallback_poster_url"]
            # HTML fallback
            if not imdb_data["poster_url"]:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(driver.page_source, "lxml")
                og = soup.find("meta", property="og:image")
                if og and og.get("content") and "social/imdb_logo" not in og.get("content",""):
                    imdb_data["poster_url"] = og["content"]
            for g in above_fold.get("genres", {}).get("genres", []):
                if g.get("text"): imdb_genres.append(g["text"])
            cl, sl = [], []
            for credit in above_fold.get("principalCreditsV2", []):
                gt = credit.get("grouping", {}).get("text", "").lower()
                names = [c.get("name",{}).get("nameText",{}).get("text","") for c in credit.get("credits",[])]
                names = [n for n in names if n]
                if any(k in gt for k in ["creator","director","writer"]): cl.extend(names)
                elif any(k in gt for k in ["star","cast","actor"]): sl.extend(names)
            imdb_data["creators"] = ", ".join(cl) if cl else None
            imdb_data["stars"] = ", ".join(sl) if sl else None

    ratings_json = scraper.get_next_data(driver, f"https://www.imdb.com/title/{new_id}/ratings/")
    country_ratings = scraper.extract_country_ratings(ratings_json)
    try: driver.delete_all_cookies()
    except: pass
    reviews_json = scraper.get_next_data(driver, f"https://www.imdb.com/title/{new_id}/reviews/")
    reviews = scraper.extract_reviews(reviews_json)

    show_data = {
        "id": new_id, "title": title,
        "type": imdb_data.get("type", row[2]),
        "release_year": imdb_data.get("release_year"),
        "end_year": imdb_data.get("end_year"),
        "global_rating": imdb_data.get("global_rating"),
        "global_vote_count": imdb_data.get("global_vote_count"),
        "runtime_seconds": imdb_data.get("runtime_seconds"),
        "certificate": imdb_data.get("certificate"),
        "plot": imdb_data.get("plot"),
        "poster_url": imdb_data.get("poster_url"),
        "release_date": row[3], "total_episodes": None,
        "creators": imdb_data.get("creators"),
        "stars": imdb_data.get("stars"),
        "current_rank": row[4], "platform": row[5],
        "content_format": row[6], "paid_free": row[7],
        "content_type": row[8], "languages": row[9],
        "reach": row[10], "week": row[11], "market": row[12],
    }

    try:
        save_conn, save_is_sqlite = fresh_conn()
        db.save_show(save_conn, save_is_sqlite, show_data)
        if old_id != new_id:
            print(f"  Migrating '{old_id}' -> '{new_id}'...")
            for table in ["show_genres","show_country_ratings","show_reviews","show_weekly_rankings"]:
                qm = f"UPDATE {table} SET show_id = %s WHERE show_id = %s"
                if save_is_sqlite: qm = qm.replace("%s","?")
                try:
                    mc = save_conn.cursor(); mc.execute(qm,(new_id,old_id)); mc.close()
                except Exception as te:
                    print(f"    [warn] {table}: {te}")
                    save_conn.rollback()
            qd = "DELETE FROM shows WHERE id = %s"
            if save_is_sqlite: qd = qd.replace("%s","?")
            dc = save_conn.cursor(); dc.execute(qd,(old_id,)); dc.close()
        db.save_genres(save_conn, save_is_sqlite, new_id, imdb_genres)
        db.save_country_ratings(save_conn, save_is_sqlite, new_id, country_ratings)
        db.save_reviews(save_conn, save_is_sqlite, new_id, reviews)
        save_conn.commit()
        poster_status = "poster found" if imdb_data.get("poster_url") else "still no poster"
        print(f"  [OK] '{title}' ({new_id}) -- {poster_status}")
        save_conn.close()
        return driver, True
    except Exception as e:
        print(f"  [ERROR] DB save: {e}")
        try: save_conn.rollback(); save_conn.close()
        except: pass
        return driver, False


def main():
    print("=" * 55)
    print("  Cleanup Remaining 6 Missing Titles")
    print("=" * 55)

    # Step 1: Fix Arafta duplicate (no scraping needed)
    fix_arafta_duplicate()

    # Step 2: Fetch remaining xl_ titles that need IMDb scraping
    conn, is_sqlite = fresh_conn()
    cur = conn.cursor()
    q = """SELECT id, title, type, release_date, current_rank, platform,
                  content_format, paid_free, content_type, languages, reach, week, market
           FROM shows
           WHERE (poster_url IS NULL OR poster_url = '') AND id LIKE 'xl_%%'
           ORDER BY current_rank ASC NULLS LAST"""
    if is_sqlite: q = q.replace("NULLS LAST","").replace("%%","%")
    cur.execute(q)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("\nNo xl_ titles remain to scrape!")
    else:
        print(f"\nScraping {len(rows)} remaining xl_ titles...")
        driver = None
        success = skipped = 0
        try:
            driver = scraper.init_driver()
            for row in rows:
                old_id, title = row[0], row[1]
                print(f"\n[{rows.index(row)+1}/{len(rows)}] '{title}' ({old_id})")
                driver, ok = scrape_and_fix(driver, title, old_id, row)
                if ok: success += 1
                else: skipped += 1
        finally:
            if driver:
                try: driver.quit()
                except: pass
                print("\nBrowser closed.")
        print(f"\nScrape results: Fixed={success}, Skipped={skipped}")

    # Final summary
    conn, is_sqlite = fresh_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM shows WHERE poster_url IS NULL OR poster_url = ''")
    remaining = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM shows WHERE poster_url IS NOT NULL AND poster_url != ''")
    fixed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM shows")
    total = cur.fetchone()[0]
    cur.close(); conn.close()

    print("\n" + "=" * 55)
    print(f"  FINAL STATE: {fixed}/{total} shows have posters")
    print(f"  Still missing: {remaining}")
    print("=" * 55)

if __name__ == "__main__":
    main()
