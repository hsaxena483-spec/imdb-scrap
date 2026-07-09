import os
import random
import time
import json
import sys
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

import db

# Load configurations
load_dotenv()

SCRAPE_LIMIT = int(os.getenv("SCRAPE_LIMIT", "10"))
REVIEWS_LIMIT = int(os.getenv("REVIEWS_LIMIT", "10"))
RANDOM_DELAY_MIN = float(os.getenv("RANDOM_DELAY_MIN", "2.0"))
RANDOM_DELAY_MAX = float(os.getenv("RANDOM_DELAY_MAX", "5.0"))


sys.stdout.reconfigure(encoding='utf-8')

def init_driver():
    """
    Initializes headless Chrome webdriver with optimized arguments (eager load, block images).
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Enable eager page load strategy (stops waiting for images and subresources)
    options.page_load_strategy = 'eager'
    
    # Block images and flash content to save bandwidth and load faster
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)
    
    # Suppress unnecessary messages
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def get_next_data(driver, url):
    """
    Loads page, waits randomly to mimic human activity, and extracts
    the __NEXT_DATA__ JSON script payload.
    """
    delay = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
    print(f"Loading URL: {url} (waiting {delay:.2f}s before fetching...)")
    time.sleep(delay)
    
    try:
        driver.get(url)
        # Wait to ensure page navigation, Javascript rendering, and WAF challenge reloads complete
        time.sleep(4.0)
        
        soup = BeautifulSoup(driver.page_source, "lxml")
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        
        if next_data_script and next_data_script.string:
            return json.loads(next_data_script.string)
        else:
            print(f"Warning: No __NEXT_DATA__ script tag found for {url}")
            return None
    except Exception as e:
        print(f"Error fetching page {url}: {e}")
        return None

def parse_release_date(date_dict):
    """
    Takes release date dict {day, month, year} and formats it as YYYY-MM-DD.
    """
    if not date_dict or not isinstance(date_dict, dict):
        return None
    year = date_dict.get('year')
    month = date_dict.get('month') or 1
    day = date_dict.get('day') or 1
    if year:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None

def extract_tv_shows_list(next_data):
    """
    Parses the tvmeter chart JSON payload to extract show details.
    """
    shows = []
    if not next_data:
        return shows
        
    edges = next_data.get("props", {}).get("pageProps", {}).get("pageData", {}).get("chartTitles", {}).get("edges", [])
    print(f"Total shows in chart data: {len(edges)}")
    
    for idx, edge in enumerate(edges):
        node = edge.get("node", {})
        if not node:
            continue
            
        show_id = node.get("id")
        title = node.get("titleText", {}).get("text", "Unknown Title")
        show_type = node.get("titleType", {}).get("id")
        
        release_year = node.get("releaseYear", {}).get("year")
        end_year = node.get("releaseYear", {}).get("endYear")
        
        ratings = node.get("ratingsSummary", {})
        global_rating = ratings.get("aggregateRating")
        global_vote_count = ratings.get("voteCount")
        
        runtime = node.get("runtime", {})
        runtime_seconds = runtime.get("seconds") if runtime else None
        
        cert = node.get("certificate", {})
        certificate = cert.get("rating") if cert else None
        
        plot_obj = node.get("plot", {})
        plot = plot_obj.get("plotText", {}).get("plainText") if plot_obj else None
        
        img = node.get("primaryImage", {})
        poster_url = img.get("url") if img else None
        
        release_date = parse_release_date(node.get("releaseDate"))
        
        episodes_obj = node.get("episodes", {})
        total_episodes = None
        if episodes_obj and episodes_obj.get("episodes"):
            total_episodes = episodes_obj.get("episodes", {}).get("total")
            
        # Parse creators and stars
        creators_list = []
        stars_list = []
        for credit in node.get("principalCreditsV2", []):
            grouping = credit.get("grouping", {})
            group_text = grouping.get("text", "").lower()
            group_id = grouping.get("groupingId", "").lower()
            
            is_creator = "creator" in group_text or "creator" in group_id or "writer" in group_text or "director" in group_text
            is_star = "star" in group_text or "star" in group_id or "actor" in group_text or "cast" in group_text
            
            names = []
            for cred in credit.get("credits", []):
                name_text = cred.get("name", {}).get("nameText", {}).get("text")
                if name_text:
                    names.append(name_text)
                    
            if is_creator:
                creators_list.extend(names)
            elif is_star:
                stars_list.extend(names)
                
        creators_str = ", ".join(list(set(creators_list))) if creators_list else None
        stars_str = ", ".join(list(set(stars_list))) if stars_list else None
        
        # Parse genres
        genres = []
        genres_list = node.get("titleGenres", {}).get("genres", [])
        for g in genres_list:
            g_text = g.get("genre", {}).get("text")
            if g_text:
                genres.append(g_text)
                
        rank_obj = node.get("meterRanking", {})
        current_rank = rank_obj.get("currentRank") if rank_obj else (idx + 1)
        
        show_data = {
            "id": show_id,
            "title": title,
            "type": show_type,
            "release_year": release_year,
            "end_year": end_year,
            "global_rating": global_rating,
            "global_vote_count": global_vote_count,
            "runtime_seconds": runtime_seconds,
            "certificate": certificate,
            "plot": plot,
            "poster_url": poster_url,
            "release_date": release_date,
            "total_episodes": total_episodes,
            "creators": creators_str,
            "stars": stars_str,
            "genres": genres,
            "current_rank": current_rank
        }
        shows.append(show_data)
        
    return shows

def extract_country_ratings(next_data):
    """
    Extracts ratings by country from ratings page JSON.
    """
    country_ratings = []
    if not next_data:
        return country_ratings
        
    content_data = next_data.get("props", {}).get("pageProps", {}).get("contentData", {})
    
    # Option 1: props.pageProps.contentData.data.title.aggregateRatingsBreakdown.ratingsSummaryByCountry
    list1 = content_data.get("data", {}).get("title", {}).get("aggregateRatingsBreakdown", {}).get("ratingsSummaryByCountry", [])
    if list1:
        for item in list1:
            code = item.get("country")
            name = item.get("displayText", {}).get("value") if isinstance(item.get("displayText"), dict) else item.get("displayText")
            rating = item.get("aggregate")
            votes = item.get("voteCount")
            if code and name:
                country_ratings.append({
                    "country_code": code,
                    "country_name": name,
                    "rating": rating,
                    "vote_count": votes
                })
                
    # Option 2 Fallback: props.pageProps.contentData.histogramData.countryData
    if not country_ratings:
        list2 = content_data.get("histogramData", {}).get("countryData", [])
        for item in list2:
            code = item.get("countryCode")
            name = item.get("displayText")
            rating = item.get("aggregateRating")
            votes = item.get("totalVoteCount")
            if code and name:
                country_ratings.append({
                    "country_code": code,
                    "country_name": name,
                    "rating": rating,
                    "vote_count": votes
                })
                
    return country_ratings

def extract_reviews(next_data):
    """
    Extracts user reviews from reviews page JSON.
    """
    reviews = []
    if not next_data:
        return reviews
        
    page_props = next_data.get("props", {}).get("pageProps", {})
    content_data = page_props.get("contentData", {})
    
    # Option 1: props.pageProps.contentData.reviews
    list1 = content_data.get("reviews", [])
    for item in list1:
        r = item.get("review", {})
        if not r:
            continue
        
        author_info = r.get("author", {})
        author_username = author_info.get("displayName") or author_info.get("username", {}).get("text") or "Anonymous"
        author_id = author_info.get("userId") or ""
        
        h = r.get("helpfulnessVotes", {}) or {}
        up_votes = h.get("upVotes") or 0
        down_votes = h.get("downVotes") or 0
        
        r_summary = r.get("reviewSummary") or ""
        r_content = r.get("reviewText") or ""
        
        reviews.append({
            "id": r.get("reviewId"),
            "author_username": author_username,
            "author_id": author_id,
            "rating": r.get("authorRating"),
            "summary": r_summary,
            "content": r_content,
            "submission_date": r.get("submissionDate"),
            "up_votes": up_votes,
            "down_votes": down_votes,
            "is_spoiler": bool(r.get("spoiler"))
        })
        
    # Option 2 Fallback: props.pageProps.contentData.data.title.reviews.edges
    if not reviews:
        edges = content_data.get("data", {}).get("title", {}).get("reviews", {}).get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            if not node:
                continue
                
            author_info = node.get("author", {}) or {}
            author_username = author_info.get("username", {}).get("text") or "Anonymous"
            author_id = author_info.get("userId") or ""
            
            summary_obj = node.get("summary", {}) or {}
            r_summary = summary_obj.get("originalText") or summary_obj.get("text") or ""
            
            text_obj = node.get("text", {}) or {}
            r_content = text_obj.get("originalText") or text_obj.get("text") or ""
            
            h = node.get("helpfulness", {}) or {}
            up_votes = h.get("upVotes") or 0
            down_votes = h.get("downVotes") or 0
            
            reviews.append({
                "id": node.get("id"),
                "author_username": author_username,
                "author_id": author_id,
                "rating": node.get("authorRating"),
                "summary": r_summary,
                "content": r_content,
                "submission_date": node.get("submissionDate"),
                "up_votes": up_votes,
                "down_votes": down_votes,
                "is_spoiler": bool(node.get("spoiler"))
            })
            
    # Apply limit
    return reviews[:REVIEWS_LIMIT]

def main():
    print("IMDb Show Scraper Initialization...")
    
    # Create a lock file to indicate that the scraper is active
    with open("scraper.lock", "w") as f:
        f.write("running")
        
    # Make sure tables exist
    db.init_db()
    
    # Start web driver
    print("Starting Selenium Headless Web Browser...")
    driver = init_driver()
    
    try:
        # Connect to DB once for the session (PostgreSQL with SQLite fallback)
        conn, is_sqlite = db.get_connection()
        
        try:
            # Step 1: Fetch TV Meter Chart (100 popular shows) FIRST
            chart_url = "https://www.imdb.com/chart/tvmeter/"
            print("Fetching trending TV shows from IMDb TV Meter...")
            chart_json = get_next_data(driver, chart_url)
            
            if not chart_json:
                print("Error: Could not retrieve TV Meter data. Aborting.")
                return
                
            shows = extract_tv_shows_list(chart_json)
            print(f"Extracted {len(shows)} shows from chart list.")
            
            if not shows:
                print("Error: No shows could be parsed. Aborting.")
                return
                
            # Limit the number of shows to scrape
            shows_to_scrape = shows[:SCRAPE_LIMIT]
            print(f"Configured to scrape details for {len(shows_to_scrape)} shows (SCRAPE_LIMIT = {SCRAPE_LIMIT}).")
            
            # Step 2: Now that we have valid chart data, clear old ranks and bulk-save all new ranks immediately
            # This ensures the dashboard always has complete rank data even while detail scraping is in progress
            print("Updating show rankings in database...")
            try:
                db.clear_all_ranks(conn, is_sqlite)
                for show in shows_to_scrape:
                    db.save_show(conn, is_sqlite, show)
                conn.commit()
                print(f"  Updated ranks for {len(shows_to_scrape)} shows.")
            except Exception as rank_err:
                conn.rollback()
                print(f"Warning: Could not update rankings: {rank_err}")
            
            for i, show in enumerate(shows_to_scrape, 1):
                show_id = show["id"]
                title = show["title"]
                
                # Check show freshness in the database (resumability)
                if db.is_show_fresh(conn, is_sqlite, show_id):
                    print(f"\n--- [{i}/{len(shows_to_scrape)}] Skipping {title} ({show_id}) - Data is already fresh (scraped within last 24h) ---")
                    # Update rank in DB even if details are fresh
                    try:
                        db.save_show(conn, is_sqlite, show)
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                    continue
                    
                print(f"\n--- [{i}/{len(shows_to_scrape)}] Processing show: {title} ({show_id}) ---")
                
                # Step 2: Fetch Ratings Breakdown page
                ratings_url = f"https://www.imdb.com/title/{show_id}/ratings/"
                ratings_json = get_next_data(driver, ratings_url)
                country_ratings = extract_country_ratings(ratings_json)
                print(f"  Found {len(country_ratings)} country-specific rating records.")
                
                # Step 3: Fetch Reviews page (clear cookies first to ensure full reviews payload loads)
                reviews_url = f"https://www.imdb.com/title/{show_id}/reviews/"
                try:
                    driver.delete_all_cookies()
                except Exception as cookie_err:
                    print(f"  Warning: Failed to clear cookies: {cookie_err}")
                reviews_json = get_next_data(driver, reviews_url)
                reviews = extract_reviews(reviews_json)
                print(f"  Found {len(reviews)} reviews.")
                
                # Step 4: Write to DB
                try:
                    # Save show details
                    db.save_show(conn, is_sqlite, show)
                    
                    # Save genres
                    db.save_genres(conn, is_sqlite, show_id, show["genres"])
                    
                    # Save country ratings
                    db.save_country_ratings(conn, is_sqlite, show_id, country_ratings)
                    
                    # Save user reviews
                    db.save_reviews(conn, is_sqlite, show_id, reviews)
                    
                    conn.commit()
                    print(f"  Successfully saved {title} data to the database.")
                except Exception as e:
                    conn.rollback()
                    print(f"  Error: Failed to save {title} data to DB: {e}")
                    
            print("\nIMDb Scraping process finished successfully.")
        finally:
            conn.close()
            print("Database connection closed.")
    finally:
        driver.quit()
        print("Headless browser closed.")
        # Remove lock file when finished
        if os.path.exists("scraper.lock"):
            os.remove("scraper.lock")

if __name__ == "__main__":
    main()
