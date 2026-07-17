"""
Use Selenium to check what IMDb's __NEXT_DATA__ actually contains for credits.
"""
import json, re, time
from scraper import init_driver, get_next_data

driver = init_driver()
try:
    url = "https://www.imdb.com/title/tt9088294/"
    print(f"Loading: {url}")
    next_data = get_next_data(driver, url)
    
    if not next_data:
        print("ERROR: No __NEXT_DATA__")
    else:
        page_props = next_data.get('props', {}).get('pageProps', {})
        above_fold = page_props.get('aboveTheFoldData', {})
        
        print("aboveTheFoldData keys:", list(above_fold.keys()))
        
        # Check principalCredits
        pc = above_fold.get('principalCredits', [])
        print(f"\nprincipalCredits count: {len(pc)}")
        for c in pc[:5]:
            cat = c.get('category', {})
            names = [cr.get('name', {}).get('nameText', {}).get('text') for cr in c.get('credits', [])]
            print(f"  category.text={cat.get('text')} | names={names[:3]}")
        
        # Check principalCreditsV2
        pc2 = above_fold.get('principalCreditsV2', [])
        print(f"\nprincipalCreditsV2 count: {len(pc2)}")
        for c in pc2[:5]:
            g = c.get('grouping', {})
            names = [cr.get('name', {}).get('nameText', {}).get('text') for cr in c.get('credits', [])]
            print(f"  grouping.text={g.get('text')} | names={names[:3]}")

        # Check mainColumnData
        main_col = page_props.get('mainColumnData', {})
        print(f"\nmainColumnData keys (first 15): {list(main_col.keys())[:15]}")
        pc3 = main_col.get('principalCredits', [])
        print(f"mainColumnData principalCredits count: {len(pc3)}")
        for c in pc3[:5]:
            cat = c.get('category', {})
            names = [cr.get('name', {}).get('nameText', {}).get('text') for cr in c.get('credits', [])]
            print(f"  category.text={cat.get('text')} | names={names[:3]}")

finally:
    driver.quit()
    print("\nDone.")
