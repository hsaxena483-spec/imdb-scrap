# Multi-Week Trend Analysis & Trending Page Plan

This plan details the database modifications, scraper updates, and dashboard enhancements needed to import 8 weeks of COTT Excel data. It enables tracking popularity, reach, and format/platform distributions week-over-week.

## User Review Required

> [strong]Database Schema Migration[/strong]
> We will migrate from a single-week schema to a normalized multi-week schema. To store history without overwriting, show rankings will be moved to a new table `show_weekly_rankings`. The `shows` table will contain only static IMDb metadata.
>
> [strong]Dynamic Hashing for Unmapped Shows[/strong]
> For shows not found on IMDb, we will generate a consistent ID based on the MD5 hash of their normalized title. This ensures the same show is tracked correctly across all 8 weeks without creating duplicates.
>
> [strong]New Dedicated Trending Page (`/trending`)[/strong]
> We will create a new, dedicated **Trending** page (accessible via `/trending` in the navigation bar) to display the historical trends. This allows the existing **Analytics** page to remain focused on single-week snapshot distributions (with a week selector).
>
> [strong]Show Details Trend Graph (`templates/show.html`)[/strong]
> When viewing a single show's detail page (e.g. *Lock Upp*), we will render an interactive Chart.js line graph showing its Rank and Reach trend history over the 8 weeks.
>
> [strong]Chronological Scraper Order[/strong]
> The scraper will scan all `.xlsx` files in the input directory, extract their week code (e.g., `WK-19`, `WK-20`, etc.), sort them chronologically, and import them in that exact order to guarantee database historical integrity.

## Open Questions

> [!WARNING]
> 1. **Directory Structure**: Where should the 8 Excel files be located? We propose creating a new directory `data_input/` in the project root where you can place all 8 files.
> 2. **Week Code Parsing**: Can we assume all week values follow the format `WK-XX, YYYY` (or similar) to allow alphabetical/numerical sorting? We will assume yes.

---

## Proposed Changes

### 1. Database Schema (`db.py`)

We will update [db.py](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/db.py) to add the `show_weekly_rankings` table and update insert functions.

#### [MODIFY] [db.py](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/db.py)
- Create `show_weekly_rankings` table:
  ```sql
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
      PRIMARY KEY (show_id, week)
  );
  ```
- Modify `save_show`: Keep only static IMDb fields in `shows` table (title, plot, poster, creators, stars, release_year, end_year, global_rating, global_vote_count, runtime_seconds, certificate).
- Add `save_weekly_ranking`: Saves week-specific columns to `show_weekly_rankings`.
- Add queries to retrieve historical rankings for a single show and aggregated weekly platform/format/genre shares.

---

### 2. Hybrid Excel Data Import Logic (`scraper.py`)

We will implement a hybrid import logic that minimizes IMDb scraping by checking for existing data first, ensuring no duplication, and executing as fast as possible.

#### [MODIFY] [scraper.py](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/scraper.py)
- Update import logic:
  - Loop through all `.xlsx` files in the input folder in chronological order.
  - Parse metadata for each week.
  - For each show title:
    - **Check Database First**: Look up the show in the `shows` table by title.
    - **If Exists**: Re-use the existing `show_id` and skip all IMDb search and detail scraping. Insert the new weekly ranking directly to `show_weekly_rankings`.
    - **If New (Not in DB)**: Search the show on IMDb, scrape its static details (plot, poster, creators, stars) and top reviews, save it to `shows`, and then write the weekly ranking to `show_weekly_rankings`.
    - **If search fails**: Generate a consistent title-hash ID (`xl_<hash_of_title>`) to save it with Excel details only.
- This ensures every show has rich metadata on the details page, while keeping scraping to an absolute minimum (only newly introduced shows are scraped once).

---

### 3. Dashboard Web Server & Templates (`app.py`, `templates/analytics.html`, `templates/trending.html`, `templates/show.html`)

We will enhance the server routes and front-end layouts to present historical week-over-week trends in a dedicated trending page, while retaining single-week snapshot analytics on the analytics page.

#### [MODIFY] [app.py](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/app.py)
- Add new `/trending` route that loads historical shows and metadata, and renders `trending.html`.
- Add API endpoints to fetch data for the trend charts:
  - `/api/show_trends?show_id=<id>`: Returns the rank and reach history sorted chronologically by week.
  - `/api/content_trends`: Returns platform and format reach shares per week.
  - `/api/genre_trends`: Returns genre and language reach shares per week.
- Update `/analytics` route to accept a `week` query parameter (defaulting to the latest week) to display single-week snapshots.
- Update `/show/<show_id>` route to fetch the show's weekly rank and reach history sorted chronologically, and pass it to `show.html`.

#### [MODIFY] [templates/analytics.html](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/templates/analytics.html)
- Add a week-selector dropdown at the top of the analytics page. When changed, it reloads the page to show platform, format, genre, and language snapshot distributions for the selected week.

#### [MODIFY] [templates/show.html](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/templates/show.html)
- Add a new full-width section to display a Chart.js double Y-axis line chart showing the show's 8-week Rank (inverted) and Reach trends.
- Include the Chart.js script tag in the template header.

#### [NEW] [trending.html](file:///c:/Users/saxen/OneDrive/Desktop/projects/Imdbscrap/templates/trending.html)
- Create a new template with a premium tabbed layout to display:
  - **Tab 1: Single Show Trends**: Search bar/dropdown to select a show and view a Chart.js double Y-axis line chart (Inverted Rank on right, Reach on left).
  - **Tab 2: Platform & Format Trends**: Line chart showing the share of reach or show counts of top platforms and formats week-over-week.
  - **Tab 3: Genre & Language Trends**: Line chart comparing genre and language reach trends over the 8 weeks.

- Update the navigation header across all templates (`index.html`, `show.html`, `analytics.html`, `trending.html`) to include the link to `/trending`.

---

## Verification Plan

### Automated Tests
- Syntax check on all modified python files: `python -m py_compile app.py db.py scraper.py`
- Test database migrations by running `init_db()` and verifying table structures.

### Manual Verification
1. Import 2-3 sample Excel files using the updated scraper and verify database records in `shows` and `show_weekly_rankings`.
2. Open the dashboard and navigate to **Trending**:
   - The dropdown list of shows loads correctly.
   - Selecting a show renders its weekly rank and reach trend lines.
   - Switching tabs displays platform, format, and genre trends accurately over the imported weeks.
3. Open the **Analytics** page and verify the week selector dropdown updates the single-week snapshots.
4. Click on a show card to open its detail page and verify that the 8-week Rank/Reach trend line graph is rendered successfully at the bottom.
