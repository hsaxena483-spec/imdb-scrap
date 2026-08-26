# -*- coding: utf-8 -*-
"""
fix_missing_posters.py
======================
Diagnoses and fixes movies/shows with missing poster_url or IMDb data.

Key design:
 - Reconnects to DB before every save (Neon drops idle connections after ~5 min)
 - Restarts Chrome driver on TimeoutException and retries
 - 3 poster strategies: __NEXT_DATA__ primaryImage -> og:image -> direct HTML img
"""

import sys
import os
import re
import time
import json
import random
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import scraper
import db


def fresh_conn():
    """Always get a brand-new DB connection to avoid stale SSL issues."""
    conn, is_sqlite = db.get_connection()
    return conn, is_sqlite


def fetch_poster_from_html(driver, imdb_id):
    """
    Last-resort: visit IMDb title page and scrape poster image from rendered HTML.
    Returns URL string or None.
    """
    url = f"https://www.imdb.com/title/{imdb_id}/"
    try:
        driver.get(url)
        time.sleep(4)
        soup = BeautifulSoup(driver.page_source, "lxml")

        # Strategy A: og:image meta tag
        og = soup.find("meta", property="og:image")
        if og and og.get("content") and "social/imdb_logo" not in og.get("content", ""):
            return og["content"]

        # Strategy B: hero poster div
        for img in soup.select("div.ipc-media img, div[data-testid='hero-media__poster'] img"):
            src = img.get("src", "")
            if src and src.startswith("https://m.media-amazon.com/images/"):
                return src

        # Strategy C: any media-amazon poster image (filenames contain _V1_)
        for img in soup.find_all("img", src=re.compile(r"m\.media-amazon\.com/images/")):
            src = img.get("src", "")
            if src and "_V1_" in src:
                return src

    except Exception as e:
        print(f"    [warn] HTML poster fetch failed for {imdb_id}: {e}")
    return None


def scrape_full_details(driver, imdb_id):
    """
    Scrapes full IMDb details for a given ID.
    Returns (imdb_data dict, genres list, country_ratings list, reviews list).
    """
    detail_url = f"https://www.imdb.com/title/{imdb_id}/"
    detail_json = scraper.get_next_data(driver, detail_url)

    imdb_data = {}
    imdb_genres = []

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

            release_year_obj = above_fold.get("releaseYear", {})
            imdb_data["release_year"] = release_year_obj.get("year") if release_year_obj else None
            imdb_data["end_year"] = release_year_obj.get("endYear") if release_year_obj else None

            title_type = above_fold.get("titleType", {})
            imdb_data["type"] = title_type.get("id") if title_type else None

            plot_obj = above_fold.get("plot", {})
            if plot_obj:
                plot_text = plot_obj.get("plotText", {})
                imdb_data["plot"] = plot_text.get("plainText") if plot_text else None

            img = above_fold.get("primaryImage", {})
            imdb_data["poster_url"] = img.get("url") if img else None

            # Fallback 1: og:image captured during page load
            if not imdb_data["poster_url"] and detail_json.get("fallback_poster_url"):
                imdb_data["poster_url"] = detail_json["fallback_poster_url"]

            genres_obj = above_fold.get("genres", {}).get("genres", [])
            for g in genres_obj:
                g_text = g.get("text")
                if g_text:
                    imdb_genres.append(g_text)

            creators_list, stars_list = [], []
            for credit in above_fold.get("principalCreditsV2", []):
                grouping_text = credit.get("grouping", {}).get("text", "").lower()
                names = [c.get("name", {}).get("nameText", {}).get("text", "")
                         for c in credit.get("credits", [])]
                names = [n for n in names if n]
                if "creator" in grouping_text or "director" in grouping_text or "writer" in grouping_text:
                    creators_list.extend(names)
                elif "star" in grouping_text or "cast" in grouping_text or "actor" in grouping_text:
                    stars_list.extend(names)

            # Fallback credits from mainColumnData
            if not creators_list and not stars_list:
                main_col = page_props.get("mainColumnData", {})
                for credit in main_col.get("principalCredits", []):
                    category = credit.get("category", {}).get("text", "").lower()
                    names = [c.get("name", {}).get("nameText", {}).get("text", "")
                             for c in credit.get("credits", [])]
                    names = [n for n in names if n]
                    if "creator" in category or "director" in category or "writer" in category:
                        creators_list.extend(names)
                    elif "star" in category or "cast" in category or "actor" in category:
                        stars_list.extend(names)

            imdb_data["creators"] = ", ".join(creators_list) if creators_list else None
            imdb_data["stars"] = ", ".join(stars_list) if stars_list else None

    # Fallback 2: direct HTML scrape if poster still missing
    if not imdb_data.get("poster_url"):
        print("    [info] poster_url missing in JSON, trying direct HTML scrape...")
        poster_from_html = fetch_poster_from_html(driver, imdb_id)
        if poster_from_html:
            imdb_data["poster_url"] = poster_from_html
            print(f"    [ok] Found poster via HTML scrape")

    # Country ratings
    ratings_url = f"https://www.imdb.com/title/{imdb_id}/ratings/"
    ratings_json = scraper.get_next_data(driver, ratings_url)
    country_ratings = scraper.extract_country_ratings(ratings_json)

    # Reviews
    reviews_url = f"https://www.imdb.com/title/{imdb_id}/reviews/"
    try:
        driver.delete_all_cookies()
    except Exception:
        pass
    reviews_json = scraper.get_next_data(driver, reviews_url)
    reviews = scraper.extract_reviews(reviews_json)

    return imdb_data, imdb_genres, country_ratings, reviews


def safe_search(driver, title):
    """Search with driver-restart retry on timeout."""
    try:
        return scraper.search_imdb_show(driver, title)
    except Exception as e:
        print(f"  [WARN] Search error ({e.__class__.__name__}), restarting driver...")
        try:
            driver.quit()
        except Exception:
            pass
        driver = scraper.init_driver()
        try:
            return scraper.search_imdb_show(driver, title), driver
        except Exception:
            return None, driver
    return None, driver


def fix_missing_posters():
    print("=" * 60)
    print("  IMDb Missing Poster / Data Fixer")
    print("=" * 60)

    # Initial connection just to fetch the list of missing titles
    conn, is_sqlite = fresh_conn()
    cursor = conn.cursor()

    q = """
        SELECT id, title, type, release_date, current_rank, platform,
               content_format, paid_free, content_type, languages, reach, week, market
        FROM shows
        WHERE poster_url IS NULL OR poster_url = ''
        ORDER BY current_rank ASC NULLS LAST
    """
    if is_sqlite:
        q = q.replace("NULLS LAST", "")
    cursor.execute(q)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()  # Close immediately - don't hold open during scraping

    print(f"\n[DIAGNOSIS] Found {len(rows)} titles with missing poster_url:\n")
    for r in rows:
        print(f"  - [{r[0]}] {r[1]}")

    if not rows:
        print("\nNothing to fix. All titles have poster URLs.")
        return

    print(f"\n[FIX] Starting re-scrape for {len(rows)} titles...\n")

    driver = None
    success = 0
    failed = 0
    skipped = 0

    try:
        for idx, row in enumerate(rows, 1):
            old_id   = row[0]
            title    = row[1]
            old_type = row[2]

            print(f"\n[{idx}/{len(rows)}] '{title}'  (DB id: {old_id})")

            if not driver:
                print("  Initializing headless Chrome...")
                driver = scraper.init_driver()

            # ── Step 1: Resolve IMDb ID ───────────────────────────────────
            if old_id.startswith("xl_"):
                print("  ID is unmapped (xl_). Searching IMDb...")
                try:
                    new_id = scraper.search_imdb_show(driver, title)
                except Exception as e:
                    print(f"  [WARN] Search error ({e.__class__.__name__}), restarting driver...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = scraper.init_driver()
                    try:
                        new_id = scraper.search_imdb_show(driver, title)
                    except Exception:
                        new_id = None

                if not new_id:
                    print(f"  [SKIP] No IMDb ID found for '{title}'.")
                    skipped += 1
                    continue
                print(f"  Found IMDb ID: {new_id}")
            else:
                new_id = old_id
                print(f"  Re-scraping with existing ID: {new_id}")

            # ── Step 2: Scrape details (Selenium, long operation) ─────────
            try:
                imdb_data, imdb_genres, country_ratings, reviews = scrape_full_details(driver, new_id)
            except Exception as e:
                print(f"  [WARN] Scrape error ({e.__class__.__name__}), restarting driver and retrying...")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = scraper.init_driver()
                try:
                    imdb_data, imdb_genres, country_ratings, reviews = scrape_full_details(driver, new_id)
                except Exception as retry_err:
                    print(f"  [ERROR] Retry also failed for '{title}': {retry_err.__class__.__name__}")
                    failed += 1
                    continue

            poster_found = bool(imdb_data.get("poster_url"))
            if not poster_found:
                print(f"  [WARN] No poster image found anywhere for '{title}'.")

            show_data = {
                "id":                new_id,
                "title":             title,
                "type":              imdb_data.get("type", old_type),
                "release_year":      imdb_data.get("release_year"),
                "end_year":          imdb_data.get("end_year"),
                "global_rating":     imdb_data.get("global_rating"),
                "global_vote_count": imdb_data.get("global_vote_count"),
                "runtime_seconds":   imdb_data.get("runtime_seconds"),
                "certificate":       imdb_data.get("certificate"),
                "plot":              imdb_data.get("plot"),
                "poster_url":        imdb_data.get("poster_url"),
                "release_date":      row[3],
                "total_episodes":    None,
                "creators":          imdb_data.get("creators"),
                "stars":             imdb_data.get("stars"),
                "current_rank":      row[4],
                "platform":          row[5],
                "content_format":    row[6],
                "paid_free":         row[7],
                "content_type":      row[8],
                "languages":         row[9],
                "reach":             row[10],
                "week":              row[11],
                "market":            row[12],
            }

            # ── Step 3: Fresh DB connection per title (avoids SSL drop) ───
            try:
                save_conn, save_is_sqlite = fresh_conn()
            except Exception as conn_err:
                print(f"  [ERROR] Cannot connect to DB: {conn_err}")
                failed += 1
                continue

            try:
                db.save_show(save_conn, save_is_sqlite, show_data)

                # Migrate xl_ -> real IMDb ID in sub-tables
                if old_id != new_id:
                    print(f"  Migrating ID '{old_id}' -> '{new_id}'...")
                    for table in ["show_genres", "show_country_ratings", "show_reviews", "show_weekly_rankings"]:
                        qm = f"UPDATE {table} SET show_id = %s WHERE show_id = %s"
                        if save_is_sqlite:
                            qm = qm.replace("%s", "?")
                        try:
                            mc = save_conn.cursor()
                            mc.execute(qm, (new_id, old_id))
                            mc.close()
                        except Exception as te:
                            print(f"    [warn] Migration of {table}: {te}")

                    qd = "DELETE FROM shows WHERE id = %s"
                    if save_is_sqlite:
                        qd = qd.replace("%s", "?")
                    dc = save_conn.cursor()
                    dc.execute(qd, (old_id,))
                    dc.close()

                db.save_genres(save_conn, save_is_sqlite, new_id, imdb_genres)
                db.save_country_ratings(save_conn, save_is_sqlite, new_id, country_ratings)
                db.save_reviews(save_conn, save_is_sqlite, new_id, reviews)
                save_conn.commit()

                status_str = "poster found" if poster_found else "still no poster (IMDb may not have one)"
                print(f"  [OK] Updated '{title}' ({new_id}) -- {status_str}")
                success += 1

            except Exception as db_err:
                try:
                    save_conn.rollback()
                except Exception:
                    pass
                print(f"  [ERROR] DB save failed for '{title}': {db_err}")
                failed += 1
            finally:
                try:
                    save_conn.close()
                except Exception:
                    pass

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            print("\nBrowser closed.")

    print("\n" + "=" * 60)
    print(f"  Done!  Fixed: {success}  |  Skipped: {skipped}  |  Failed: {failed}  |  Total: {len(rows)}")
    print("=" * 60)


if __name__ == "__main__":
    fix_missing_posters()
