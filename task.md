# Tasks

- [x] Implement Scraper Enhancements
  - [x] Add `is_show_fresh` check in `db.py`
  - [x] Configure eager loading and block images in Chrome options in `scraper.py`
  - [x] Implement database connection reuse in `scraper.py` (open once, close at end)
  - [x] Integrate resumability skip logic in `scraper.py`
- [x] Implement Flask Web Dashboard
  - [x] Build Flask routing server in `app.py`
  - [x] Create core dark-mode/glassmorphic CSS styles in `static/style.css`
  - [x] Build home dashboard template in `templates/index.html`
  - [x] Build single show detail page in `templates/show.html`
- [x] Verify Implementation
  - [x] Verify scraper skips already fresh records (resumability)
  - [x] Start Flask server and test UI pages in browser
