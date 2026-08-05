import sys
import os
import re
import random
import time
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import scraper
import db

def rescrape_all_missing():
    print("Initializing Database connection...")
    db.init_db()
    conn, is_sqlite = db.get_connection()
    
    cursor = conn.cursor()
    # Find all shows where poster_url is missing or ID starts with 'xl_'
    cursor.execute("""
        SELECT id, title, type, release_date, current_rank, platform, 
               content_format, paid_free, content_type, languages, reach, week, market
        FROM shows 
        WHERE poster_url IS NULL OR poster_url = '' OR id LIKE 'xl_%%'
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} titles to inspect/rescrape.")
    
    if not rows:
        cursor.close()
        conn.close()
        print("No missing titles to process.")
        return
        
    driver = None
    processed_count = 0
    success_count = 0
    
    try:
        for idx, row in enumerate(rows, 1):
            old_id = row[0]
            title = row[1]
            content_type = row[8]
            
            print(f"\n[{idx}/{len(rows)}] Processing '{title}' (Current ID: {old_id})")
            
            if not driver:
                print("  Initializing headless Chrome webdriver...")
                driver = scraper.init_driver()
                
            # 1. Search IMDb for correct ID
            new_id = scraper.search_imdb_show(driver, title)
            if not new_id:
                print(f"  No valid IMDb ID found for '{title}'. Skipping rescrape.")
                continue
                
            print(f"  Found IMDb ID: {new_id}")
            
            # 2. Scrape details
            detail_url = f"https://www.imdb.com/title/{new_id}/"
            detail_json = scraper.get_next_data(driver, detail_url)
            
            imdb_data = {}
            imdb_genres = []
            if detail_json:
                page_props = detail_json.get('props', {}).get('pageProps', {})
                above_fold = page_props.get('aboveTheFoldData', {})
                if above_fold:
                    ratings = above_fold.get('ratingsSummary', {})
                    imdb_data['global_rating'] = ratings.get('aggregateRating')
                    imdb_data['global_vote_count'] = ratings.get('voteCount')
                    
                    cert = above_fold.get('certificate', {})
                    imdb_data['certificate'] = cert.get('rating') if cert else None
                    
                    runtime_obj = above_fold.get('runtime', {})
                    imdb_data['runtime_seconds'] = runtime_obj.get('seconds') if runtime_obj else None
                    
                    release_year_obj = above_fold.get('releaseYear', {})
                    imdb_data['release_year'] = release_year_obj.get('year') if release_year_obj else None
                    imdb_data['end_year'] = release_year_obj.get('endYear') if release_year_obj else None
                    
                    title_type = above_fold.get('titleType', {})
                    imdb_data['type'] = title_type.get('id') if title_type else None
                    
                    plot_obj = above_fold.get('plot', {})
                    if plot_obj:
                        plot_text = plot_obj.get('plotText', {})
                        imdb_data['plot'] = plot_text.get('plainText') if plot_text else None
                    
                    img = above_fold.get('primaryImage', {})
                    imdb_data['poster_url'] = img.get('url') if img else None
                    if not imdb_data['poster_url'] and detail_json.get('fallback_poster_url'):
                        imdb_data['poster_url'] = detail_json['fallback_poster_url']
                    
                    genres_obj = above_fold.get('genres', {}).get('genres', [])
                    for g in genres_obj:
                        g_text = g.get('text')
                        if g_text:
                            imdb_genres.append(g_text)
                            
                    creators_list = []
                    stars_list = []
                    for credit in above_fold.get('principalCreditsV2', []):
                        grouping_text = credit.get('grouping', {}).get('text', '').lower()
                        names = [c.get('name', {}).get('nameText', {}).get('text', '') for c in credit.get('credits', [])]
                        names = [n for n in names if n]
                        if 'creator' in grouping_text or 'director' in grouping_text or 'writer' in grouping_text:
                            creators_list.extend(names)
                        elif 'star' in grouping_text or 'cast' in grouping_text or 'actor' in grouping_text:
                            stars_list.extend(names)
                            
                    if not creators_list and not stars_list:
                        main_col_data = page_props.get('mainColumnData', {})
                        for credit in main_col_data.get('principalCredits', []):
                            category = credit.get('category', {}).get('text', '').lower()
                            names = [c.get('name', {}).get('nameText', {}).get('text', '') for c in credit.get('credits', [])]
                            names = [n for n in names if n]
                            if 'creator' in category or 'director' in category or 'writer' in category:
                                creators_list.extend(names)
                            elif 'star' in category or 'cast' in category or 'actor' in category:
                                stars_list.extend(names)
                                
                    imdb_data['creators'] = ', '.join(creators_list) if creators_list else None
                    imdb_data['stars'] = ', '.join(stars_list) if stars_list else None

            # Fetch ratings and reviews
            ratings_url = f"https://www.imdb.com/title/{new_id}/ratings/"
            ratings_json = scraper.get_next_data(driver, ratings_url)
            country_ratings = scraper.extract_country_ratings(ratings_json)
            
            reviews_url = f"https://www.imdb.com/title/{new_id}/reviews/"
            try: driver.delete_all_cookies()
            except Exception: pass
            reviews_json = scraper.get_next_data(driver, reviews_url)
            reviews = scraper.extract_reviews(reviews_json)
            
            # 3. Construct show details dict preserving original metadata
            show_data = {
                'id': new_id,
                'title': title,
                'type': imdb_data.get('type', row[8]),
                'release_year': imdb_data.get('release_year'),
                'end_year': imdb_data.get('end_year'),
                'global_rating': imdb_data.get('global_rating'),
                'global_vote_count': imdb_data.get('global_vote_count'),
                'runtime_seconds': imdb_data.get('runtime_seconds'),
                'certificate': imdb_data.get('certificate'),
                'plot': imdb_data.get('plot'),
                'poster_url': imdb_data.get('poster_url'),
                'release_date': row[3],
                'total_episodes': None,
                'creators': imdb_data.get('creators'),
                'stars': imdb_data.get('stars'),
                'current_rank': row[4],
                'platform': row[5],
                'content_format': row[6],
                'paid_free': row[7],
                'content_type': row[8],
                'languages': row[9],
                'reach': row[10],
                'week': row[11],
                'market': row[12],
            }
            
            # 4. Save and Migrate ID in Database
            try:
                # Save details under new ID
                db.save_show(conn, is_sqlite, show_data)
                
                # If ID changed, migrate references and delete old record
                if old_id != new_id:
                    print(f"  Migrating ID from '{old_id}' to '{new_id}' in all referencing tables...")
                    sub_tables = ['show_genres', 'show_country_ratings', 'show_reviews', 'show_weekly_rankings']
                    for table in sub_tables:
                        query_mig = f"UPDATE {table} SET show_id = %s WHERE show_id = %s"
                        if is_sqlite:
                            query_mig = query_mig.replace("%s", "?")
                        
                        sub_cursor = conn.cursor()
                        try:
                            sub_cursor.execute(query_mig, (new_id, old_id))
                        except Exception as table_err:
                            print(f"    Warning: Failed to migrate table {table}: {table_err}")
                        finally:
                            sub_cursor.close()
                    
                    # Delete old record
                    query_del = "DELETE FROM shows WHERE id = %s"
                    if is_sqlite:
                        query_del = query_del.replace("%s", "?")
                    del_cursor = conn.cursor()
                    del_cursor.execute(query_del, (old_id,))
                    del_cursor.close()
                
                # Save scraped sub-details under the new ID
                db.save_genres(conn, is_sqlite, new_id, imdb_genres)
                db.save_country_ratings(conn, is_sqlite, new_id, country_ratings)
                db.save_reviews(conn, is_sqlite, new_id, reviews)
                
                conn.commit()
                print(f"  Successfully rescraped and updated '{title}'!")
                success_count += 1
            except Exception as db_err:
                conn.rollback()
                print(f"  Error updating database for '{title}': {db_err}")
                
            processed_count += 1
            
    finally:
        if driver:
            driver.quit()
        cursor.close()
        conn.close()
        
    print(f"\nRescrape finished! Successfully updated {success_count} out of {processed_count} processed titles.")

if __name__ == "__main__":
    rescrape_all_missing()
