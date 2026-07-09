# IMDb Scraper & Dashboard Free Deployment Guide

Since you already use a cloud database (**Neon PostgreSQL**), your data is already hosted in the cloud. To deploy your web dashboard and scraping runner completely for free, the most robust and professional architecture is to **split them**:

1. **The Web Dashboard (Flask)**: Deploy it on **Render** (Free tier). Since it only queries Neon and displays data, it is extremely lightweight and runs perfectly within Render's free limit.
2. **The Scraper (Selenium)**: Deploy it on **GitHub Actions** (Free tier). GitHub Actions runners have 7GB RAM and **Google Chrome pre-installed**. It can run automatically on a schedule (e.g., daily) and update your Neon database.

---

## Part 1: Deploying the Dashboard on Render (100% Free)

Render is a cloud platform that hosts Flask apps for free.

### Step 1: Prepare your Code Repository
1. Initialize a Git repository in your project folder:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```
2. Create a new repository on GitHub (e.g., `imdb-scraper-dashboard`) and push your code there.

### Step 2: Create a Render Web Service
1. Sign up for a free account at [Render](https://render.com/).
2. Click **New** -> **Web Service**.
3. Connect your GitHub account and select your `imdb-scraper-dashboard` repository.
4. Set the following configuration details:
   - **Name**: `imdb-dashboard`
   - **Environment**: `Python 3`
   - **Region**: Choose one closest to you (e.g., Oregon or Frankfurt)
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app` (Note: Add `gunicorn` to your requirements.txt first).
   - **Instance Type**: `Free`

### Step 3: Add Environment Variables
On Render, click the **Environment** tab on your service dashboard and add:
- `DATABASE_URL`: *(Your Neon PostgreSQL connection string)*
- `FLASK_ENV`: `production`

Click **Deploy Web Service**. Once finished, Render will give you a free URL (e.g., `https://imdb-dashboard.onrender.com`) to view your dashboard!

---

## Part 2: Deploying the Scraper on GitHub Actions (100% Free)

To run the Selenium scraper automatically in the cloud, you can use GitHub Actions.

### Step 1: Create the GitHub Workflow File
In your project folder, create the directories and the workflow file:
`c:\Users\saxen\OneDrive\Desktop\projects\Imdbscrap\.github\workflows\scrape.yml`

Write the following content into it:
```yaml
name: Run IMDb Scraper

on:
  schedule:
    - cron: '0 0 * * *' # Runs automatically every day at midnight UTC
  workflow_dispatch: # Allows you to trigger the scraper manually with a button click on GitHub!

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          pip install -r requirements.txt

      - name: Run Scraper
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          SCRAPE_LIMIT: 30
          REVIEWS_LIMIT: 10
          RANDOM_DELAY_MIN: 2
          RANDOM_DELAY_MAX: 5
        run: python scraper.py
```

### Step 2: Add secrets to GitHub Repository
1. On your GitHub repository page, click **Settings** -> **Secrets and variables** -> **Actions**.
2. Click **New repository secret**.
3. Add:
   - **Name**: `DATABASE_URL`
   - **Value**: *(Your Neon PostgreSQL database URL)*
4. Commit and push the `.github/workflows/scrape.yml` file to GitHub.

### Step 3: Run the Scraper manually on GitHub
1. Go to your GitHub repository.
2. Click the **Actions** tab at the top.
3. Select **Run IMDb Scraper** on the left menu.
4. Click **Run workflow** -> **Run workflow**. 
5. The GitHub runner will spin up a VM, install Google Chrome, run your `scraper.py` file, populate your Neon database, and shut down. Your Render web dashboard will immediately reflect the updated numbers!
