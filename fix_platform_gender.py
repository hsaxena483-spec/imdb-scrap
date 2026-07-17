import db
conn, is_sqlite = db.get_connection()
cur = conn.cursor()

PLATFORM_MAP = {
    "amazon mx player":   "Amazon MX Player",
    "amazon mxplayer":    "Amazon MX Player",
    "jio hotstar":        "JioHotstar",
    "jiohotstar":         "JioHotstar",
    "sony liv":           "SonyLIV",
    "sonyliv":            "SonyLIV",
    "zee5":               "ZEE5",
    "zee 5":              "ZEE5",
    "apple tv":           "Apple TV",
}

# Read all rows
cur.execute("SELECT platform, total_reach, male_pct, female_pct FROM platform_gender")
rows = cur.fetchall()

# Merge by canonical name (weighted average for percentages, sum for reach)
merged = {}  # canonical -> {total_reach, male_reach, female_reach}
for platform, total_reach, male_pct, female_pct in rows:
    canonical = PLATFORM_MAP.get(platform.strip().lower(), platform.strip())
    total_reach = float(total_reach) if total_reach else 0.0
    male_pct = float(male_pct) if male_pct else 0.0
    female_pct = float(female_pct) if female_pct else 0.0

    if canonical not in merged:
        merged[canonical] = {"total_reach": 0.0, "male_reach": 0.0, "female_reach": 0.0}
    merged[canonical]["total_reach"] += total_reach
    merged[canonical]["male_reach"] += total_reach * male_pct
    merged[canonical]["female_reach"] += total_reach * female_pct

# Delete all rows
cur.execute("DELETE FROM platform_gender")
print(f"Deleted all platform_gender rows")

# Re-insert merged clean rows
for canonical, data in merged.items():
    total = data["total_reach"]
    male_pct = round(data["male_reach"] / total, 3) if total > 0 else 0.0
    female_pct = round(1.0 - male_pct, 3)
    cur.execute(
        "INSERT INTO platform_gender (platform, total_reach, male_pct, female_pct) VALUES (%s, %s, %s, %s)",
        (canonical, round(total, 5), male_pct, female_pct)
    )
    print(f"  Inserted: {canonical} | reach={round(total,2)} | male={male_pct} | female={female_pct}")

conn.commit()

# Final audit
print("\n=== FINAL platform_gender ===")
cur.execute("SELECT platform, total_reach, male_pct, female_pct FROM platform_gender ORDER BY total_reach DESC")
for r in cur.fetchall():
    print(f"  {r[0]} | reach={r[1]} | male={r[2]*100:.1f}% | female={r[3]*100:.1f}%")

conn.close()
print("\nDone!")
