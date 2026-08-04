import sys
import time
import db
import scraper

def backfill():
    conn, is_sqlite = db.get_connection()
    try:
        cursor = conn.cursor()
        # Find all shows that have no reviews in show_reviews table
        cursor.execute("""
            SELECT DISTINCT s.id, s.title 
            FROM shows s
            LEFT JOIN show_reviews r ON s.id = r.show_id
            WHERE r.show_id IS NULL AND s.id LIKE 'tt%'
        """)
        shows = cursor.fetchall()
        print(f"Found {len(shows)} shows with 0 reviews in the database.")
        
        if not shows:
            print("All shows already have reviews!")
            return
            
        print("Starting Selenium driver...")
        driver = scraper.init_driver()
        
        for i, (show_id, title) in enumerate(shows):
            print(f"[{i+1}/{len(shows)}] Scraping reviews for '{title}' ({show_id})...")
            try:
                url = f"https://www.imdb.com/title/{show_id}/reviews/"
                next_data = scraper.get_next_data(driver, url)
                if next_data:
                    reviews = scraper.extract_reviews(next_data)
                    print(f"  Found {len(reviews)} reviews.")
                    if reviews:
                        # Save reviews to DB
                        db.save_reviews(conn, is_sqlite, show_id, reviews)
                        conn.commit()
                        print(f"  Successfully saved reviews for '{title}'.")
                    else:
                        print("  No reviews found on page.")
                else:
                    print("  Failed to retrieve page or blocked by WAF.")
            except Exception as e:
                print(f"  Error scraping '{title}': {e}")
            # Respectful delay
            time.sleep(3)
            
        driver.quit()
        print("Backfill completed successfully!")
    finally:
        conn.close()

if __name__ == "__main__":
    backfill()
