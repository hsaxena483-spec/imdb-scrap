import os
import sqlite3
import psycopg2
from dotenv import load_dotenv
import sys

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

db_url = os.getenv("DATABASE_URL")
db_type = os.getenv("DB_TYPE", "postgresql").lower()

if db_url and db_type == "postgresql":
    print(f"Connecting to Neon PostgreSQL database using DATABASE_URL...")
    conn = psycopg2.connect(db_url)
    is_sqlite = False
else:
    print("Connecting to local SQLite database 'imdb.db'...")
    conn = sqlite3.connect("imdb.db")
    is_sqlite = True

cursor = conn.cursor()

def print_table_data(table_name):
    print(f"\n--- Data in Table: {table_name} ---")
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    
    # Get column names
    col_names = [description[0] for description in cursor.description]
    print("Columns:", col_names)
    print(f"Total Rows: {len(rows)}")
    
    for r in rows[:5]:  # print first 5 rows
        # Format output gracefully
        formatted_row = {}
        for col, val in zip(col_names, r):
            if isinstance(val, str) and len(val) > 80:
                formatted_row[col] = val[:80] + "..."
            else:
                formatted_row[col] = val
        print(formatted_row)
        print("-" * 10)

try:
    print_table_data("shows")
    print_table_data("show_genres")
    print_table_data("show_country_ratings")
    print_table_data("show_reviews")
except Exception as e:
    print("Error querying database:", e)
finally:
    conn.close()
