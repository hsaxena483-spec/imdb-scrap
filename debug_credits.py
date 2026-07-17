"""
Test what the IMDb page JSON actually contains for one show.
Checks the principalCreditsV2 field specifically.
"""
import json, re
from scraper import load_url  # reuse the headless browser loader

# Pick a well-known show
test_url = "https://www.imdb.com/title/tt9088294/"  # Squid Game
print(f"Testing: {test_url}")

html = load_url(test_url)
if not html:
    print("ERROR: Could not load page")
    exit()

match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
if not match:
    print("ERROR: No __NEXT_DATA__ found")
    exit()

data = json.loads(match.group(1))

# Navigate to the show node
try:
    node = data['props']['pageProps']['aboveTheFoldData']
    print("Found aboveTheFoldData")
    print("Keys:", list(node.keys()))
    
    creds = node.get('principalCreditsV2', [])
    print(f"\nprincipalCreditsV2 entries: {len(creds)}")
    for c in creds:
        g = c.get('grouping', {})
        print(f"  group: {g.get('text')} | id: {g.get('groupingId')} | credits: {len(c.get('credits', []))}")
        names = [cr.get('name', {}).get('nameText', {}).get('text') for cr in c.get('credits', [])]
        print(f"    names: {names[:5]}")
        
except Exception as e:
    print(f"Error navigating JSON: {e}")
    # Try alternate path
    try:
        node = data['props']['pageProps']['mainColumnData']
        print("Found mainColumnData instead")
        creds = node.get('principalCreditsV2', [])
        print(f"principalCreditsV2 entries: {len(creds)}")
    except Exception as e2:
        print(f"Also failed: {e2}")
        print("Top-level props keys:", list(data.get('props', {}).get('pageProps', {}).keys())[:10])
