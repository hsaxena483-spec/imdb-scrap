# IMDb Scraper Implementation Plan

This plan outlines the design and implementation of a Python-based IMDb scraper that fetches the 100 most popular TV shows (recent/trending), their detailed metadata, their ratings broken down by country (with average ratings and vote counts), and user reviews, storing all of this in a PostgreSQL database.

## User Review Required

> [!WARNING]
> IMDb employs advanced anti-bot protections (AWS WAF challenges). To bypass this, the scraper uses **Selenium** in headless mode with realistic browser headers to extract the page data. 
> Since Selenium runs a real browser instance, scraping is slower than standard requests. A delay (e.g., 2–5 seconds) between page loads is necessary to prevent being rate-limited or blocked.

> [!IMPORTANT]
> PostgreSQL is not currently running or installed on your system's default port (`5432`). 
> We will configure the database connection using environment variables in a `.env` file, allowing you to point the scraper to your external/existing PostgreSQL instance. 
> To facilitate local testing, we will also implement a automatic **SQLite fallback** option if the PostgreSQL database is unreachable.

## Open Questions

> [!NOTE]
> Please review these questions and provide your preferences. We will proceed with the implementation based on your choices.

1. **Scraping Limits**: Do you want to scrape all 100 shows from the Most Popular TV Shows list, or should we make it configurable (e.g., a default limit of 10 or 20 shows for speed)?
2. **Review Count**: How many reviews do you want to save per show? (IMDb's reviews page loads the top 25 reviews by default. Loading more requires clicking a "Load More" button which increases scraping time).
3. **Database Fallback**: Are you comfortable with the SQLite fallback option for local testing, or do you want to strictly use PostgreSQL (which would require you to supply a running PostgreSQL instance in the `.env` file before execution)?

## Proposed Changes

We will create a self-contained Python project in your workspace: `c:\Users\saxen\OneDrive\Desktop\projects\Imdbscrap`.

---

### Database Schema Design

We will define 4 tables to store the structured data:

1. **`shows`**: Holds show details.
   - `id` (VARCHAR(15) PRIMARY KEY): IMDb show identifier (e.g., `tt11198330`).
   - `title` (VARCHAR(255)): Title of the show.
   - `type` (VARCHAR(50)): Type (e.g., `tvSeries`).
   - `release_year` (INTEGER): Start year of the show.
   - `end_year` (INTEGER): End year of the show (NULL if ongoing).
   - `global_rating` (NUMERIC(3, 1)): Combined global weighted rating (1.0 to 10.0).
   - `global_vote_count` (INTEGER): Total count of votes globally.
   - `runtime_seconds` (INTEGER): Runtime in seconds.
   - `certificate` (VARCHAR(50)): Content rating (e.g., `TV-MA`).
   - `plot` (TEXT): Synopsis / storyline of the show.
   - `poster_url` (VARCHAR(500)): URL of the show's poster image.
   - `release_date` (DATE): Full release date of the show.
   - `total_episodes` (INTEGER): Total number of episodes.
   - `creators` (TEXT): Comma-separated list of show creators.
   - `stars` (TEXT): Comma-separated list of lead stars/actors.
   - `current_rank` (INTEGER): Popularity rank on the IMDb TV Meter chart.
   - `created_at` (TIMESTAMP): Time of insertion.
   - `updated_at` (TIMESTAMP): Time of last modification.

2. **`show_genres`**: M-to-N relation mapping shows to genres.
   - `show_id` (VARCHAR(15) REFERENCES `shows(id)`): Foreign key.
   - `genre` (VARCHAR(50)): Genre name (e.g., `Drama`).
   - PRIMARY KEY (`show_id`, `genre`).

3. **`show_country_ratings`**: Ratings segmented by country.
   - `show_id` (VARCHAR(15) REFERENCES `shows(id)`): Foreign key.
   - `country_code` (VARCHAR(10)): 2-character country code (e.g., `US`, `IN`).
   - `country_name` (VARCHAR(100)): Display name of the country (e.g., `United States`).
   - `rating` (NUMERIC(3, 1)): Country-specific average rating.
   - `vote_count` (INTEGER): Number of votes cast by users in that country.
   - PRIMARY KEY (`show_id`, `country_code`).

4. **`show_reviews`**: User reviews details.
   - `id` (VARCHAR(50) PRIMARY KEY): IMDb review ID (e.g., `rw5731695`).
   - `show_id` (VARCHAR(15) REFERENCES `shows(id)`): Foreign key.
   - `author_username` (VARCHAR(255)): Username of the reviewer.
   - `author_id` (VARCHAR(50)): IMDb profile identifier of the reviewer.
   - `rating` (INTEGER): Rating given by the reviewer (1-10, NULL if none).
   - `summary` (VARCHAR(500)): Review title/summary.
   - `content` (TEXT): Full body of the review.
   - `submission_date` (DATE): Review creation date.
   - `up_votes` (INTEGER): Helpfulness up-votes.
   - `down_votes` (INTEGER): Helpfulness down-votes.
   - `is_spoiler` (BOOLEAN): Whether it's marked as containing spoilers.
   - `created_at` (TIMESTAMP): Insertion timestamp.

---

### Project Files

#### [NEW] [db.py](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/db.py)
Handles PostgreSQL database connections, schema creation, data insertion using upsert queries (`INSERT ... ON CONFLICT DO UPDATE`), and a connection verification function that triggers SQLite fallback if PostgreSQL connection parameters fail.

#### [NEW] [scraper.py](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/scraper.py)
Main scraper script that performs:
1. **Initialize Selenium**: Starts headless Chrome with customized headers to avoid blocking.
2. **Fetch TV Meter Chart**: Navigates to `https://www.imdb.com/chart/tvmeter/` to collect trending shows list and details.
3. **Fetch Country Ratings**: For each show, navigates to `https://www.imdb.com/title/{id}/ratings/` and parses country statistics.
4. **Fetch User Reviews**: For each show, navigates to `https://www.imdb.com/title/{id}/reviews/` and extracts user reviews.
5. **Parse JSON payload**: Extracts data cleanly from the `__NEXT_DATA__` JSON block rather than relying on brittle HTML DOM selectors.
6. **Save to Database**: Saves the structured object records to `db.py` in batches.

#### [NEW] [.env](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/.env)
Contains PostgreSQL login credentials, connection settings, and scraper configuration options:
```ini
# Database Connection Settings
DB_TYPE=postgresql  # Option: 'postgresql' or 'sqlite'
DB_HOST=localhost
DB_PORT=5432
DB_NAME=imdb_db
DB_USER=postgres
DB_PASSWORD=your_password

# Scraper Settings
SCRAPE_LIMIT=10        # Limit number of shows to scrape
REVIEWS_LIMIT=10       # Max reviews to extract per show
RANDOM_DELAY_MIN=2     # Minimum delay between page fetches
RANDOM_DELAY_MAX=5     # Maximum delay between page fetches
```

#### [NEW] [requirements.txt](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/requirements.txt)
Specifies Python package requirements:
```text
requests==2.34.2
beautifulsoup4==4.15.0
selenium==4.45.0
webdriver-manager==4.1.2
python-dotenv==1.2.2
psycopg2-binary==2.9.9
```

---

## Verification Plan

### Automated Tests
- Run `scraper.py` on a single test show (e.g. limit to 1 show) and verify database entries are populated.
- Run SQL queries checking table counts, relationships, and data completeness.
- Verify PostgreSQL connection and SQLite connection fallback.

### Manual Verification
- Output logs showing real-time status of scraping (page requests, WAF bypass, data parsing, database insertion progress).
- Verify the content of DB tables using a python diagnostic script to query and display the data.
