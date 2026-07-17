# COTT Multi-Week Trend Analysis Walkthrough

We have successfully migrated the database schema to support multi-week historical tracking, updated the scraper to act as a chronologically sorted hybrid Excel importer, and implemented interactive line charts on a new dedicated **Trending** page and individual show detail pages.

All files are active in your workspace at `c:\Users\saxen\OneDrive\Desktop\projects\Imdbscrap`.

---

## 🚀 Key Features Implemented

### 1. Chronological Hybrid Importer (`scraper.py`)
- **Directory Scan**: Scans a directory (defaults to `data_input/`) for all `.xlsx` files.
- **Chronological Sorting**: Parses the week code (e.g. `WK-19,2026` ... `WK-26,2026`) from each sheet dynamically, extracts the week number and year, and sorts the files chronologically.
- **Duplication Checks**: Looks up each show title in the database before scraping. If it exists, it skips all Selenium/IMDb requests, immediately reusing the ID. If new, it queries IMDb to pull rich metadata.
- **Title Hashing**: Generates consistent MD5-based IDs (`xl_<hash>`) for shows not found on IMDb so that they still link correctly week-over-week.
- **Multi-Week Metadata**: Saves time periods and locations for all weeks to `metadata.json`.

### 2. Multi-Week Database Schema (`db.py`)
- Added the `show_weekly_rankings` table:
  - Fields: `show_id`, `week`, `current_rank`, `reach`, `platform`, `content_format`, `paid_free`, `content_type`, `market`.
  - Primary Key: `(show_id, week)` to store rankings for multiple weeks without overwriting.

### 3. Dedicated Trending Page (`/trending`)
- Displays three interactive tabs with line charts using **Chart.js**:
  - **Show Trends**: Select a show from the searchable dropdown to view its Rank (inverted scale on right axis) and Reach (left axis) over time.
  - **Platform & Format Trends**: Side-by-side line charts of weekly total reach shares by platforms and formats.
  - **Genre & Language Trends**: Side-by-side line charts of reach percentage shifts of different genres and languages.

### 4. Show Details Trend Line (`show.html`)
- Displays an interactive line chart directly on each show's detail page showing its 8-week Rank and Reach history (fully populated dynamically).

### 5. Single Week Analytics Dropdown (`analytics.html`)
- Added a **Select Analysis Week** dropdown at the top of the Analytics page.
- Selecting a week automatically reloads the page to show platform, format, genre, and language snapshot distributions for that specific week.

---

## 🛠️ Verification & Test Results

1. **Database Schema Creation**:
   - Running `db.py` successfully created the `show_weekly_rankings` table in your cloud database:
     ```text
     Creating table: show_weekly_rankings...
     Database initialized successfully.
     ```

2. **Excel Import Run**:
   - Placed a test Excel sheet `imdb_analysis_test.xlsx` (WK-26) in the `data_input/` directory and ran `python scraper.py`.
   - The importer successfully scanned the file, skipped web scraping for all 50 shows (as they already existed), and wrote the rankings directly:
     ```text
     Sorted Excel files chronologically:
       1. data_input\imdb_analysis_test.xlsx (Week: WK-26,2026)
     Loaded 50 shows from data_input\imdb_analysis_test.xlsx.
     [1/50] Show 'England vs India T20 Series 2026' exists in DB. Skipping IMDb scrape.
     ...
     Excel Import process finished successfully.
     ```
   - Verified that 50 rows were written to `show_weekly_rankings`.

---

## 📖 How to Run & Import Your Data

### 1. Place Your 8 Excel Files
Create the `data_input` folder inside the project and copy your 8 Excel files there:
`c:\Users\saxen\OneDrive\Desktop\projects\Imdbscrap\data_input`

### 2. Run the Importer
Run the importer from your terminal:
```bash
python scraper.py
```
*The importer will sort the files, check for existing shows, and import all 8 weeks in seconds.*

### 3. Run the Dashboard
Start your web server:
```bash
python app.py
```
Navigate to **[http://127.0.0.1:5000](http://127.0.0.1:5000)** to browse the new pages!
- Click **Trending** in the navigation header to see multi-week trends.
- Click **Analytics** and change the dropdown to view snapshots of specific weeks.
- Click on any show card to see its detail page along with its individual trend chart!
