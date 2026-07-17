"""
Debug: check what keys exist in aboveTheFoldData for a real IMDb show page.
Uses requests + BeautifulSoup (no Selenium) for quick check.
"""
import requests, json, re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

url = "https://www.imdb.com/title/tt9088294/"  # Squid Game
print(f"Fetching: {url}")
r = requests.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")

match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
if not match:
    print("ERROR: No __NEXT_DATA__ found")
    exit()

data = json.loads(match.group(1))
page_props = data.get('props', {}).get('pageProps', {})
above_fold = page_props.get('aboveTheFoldData', {})
main_col = page_props.get('mainColumnData', {})

print("\n=== aboveTheFoldData keys ===")
print(list(above_fold.keys()))

print("\n=== principalCredits in aboveTheFoldData ===")
pc = above_fold.get('principalCredits', [])
print(f"Count: {len(pc)}")
for c in pc:
    cat = c.get('category', {})
    names = [cr.get('name', {}).get('nameText', {}).get('text') for cr in c.get('credits', [])]
    print(f"  category: {cat} | names: {names[:3]}")

print("\n=== principalCreditsV2 in aboveTheFoldData ===")
pc2 = above_fold.get('principalCreditsV2', [])
print(f"Count: {len(pc2)}")
for c in pc2:
    g = c.get('grouping', {})
    names = [cr.get('name', {}).get('nameText', {}).get('text') for cr in c.get('credits', [])]
    print(f"  grouping: {g} | names: {names[:3]}")

print("\n=== mainColumnData keys (first 20) ===")
print(list(main_col.keys())[:20])
