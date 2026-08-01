import os
import json
import re
import subprocess
import sys
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from db import get_db, get_db_data
from config import normalize_genre

trends_bp = Blueprint('trends', __name__)

@trends_bp.route("/analytics")
def analytics():
    # Check if we have weekly rankings table populated
    has_rankings_row, _ = get_db_data("SELECT 1 FROM show_weekly_rankings LIMIT 1")
    use_rankings_table = bool(has_rankings_row)

    available_weeks = []
    selected_week = None

    if use_rankings_table:
        weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
        def sort_weeks_key(w_code):
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key, reverse=True)
        
        selected_week = request.args.get("week")
        if not selected_week and available_weeks:
            selected_week = available_weeks[0]

    # Fallback default if not set or empty
    if not selected_week:
        selected_week = "WK-26,2026"

    # Query 1: Top 10 content
    if use_rankings_table:
        top_shows_rows, top_shows_cols = get_db_data("""
            SELECT s.title, w.reach, s.global_rating 
            FROM shows s 
            JOIN show_weekly_rankings w ON s.id = w.show_id 
            WHERE w.week = %s 
              AND w.current_rank IS NOT NULL 
              AND (w.content_type IS NULL OR LOWER(w.content_type) != 'sports')
            ORDER BY w.current_rank ASC 
            LIMIT 10
        """, (selected_week,))
    else:
        top_shows_rows, top_shows_cols = get_db_data("""
            SELECT title, reach, global_rating 
            FROM shows 
            WHERE current_rank IS NOT NULL 
              AND (content_type IS NULL OR LOWER(content_type) != 'sports')
            ORDER BY current_rank ASC 
            LIMIT 10
        """)
        
    top_shows = []
    for row in top_shows_rows:
        show = dict(zip(top_shows_cols, row))
        show['reach'] = float(show['reach']) if show['reach'] is not None else 0.0
        show['global_rating'] = float(show['global_rating']) if show['global_rating'] is not None else 0.0
        top_shows.append(show)
    top_shows = sorted(top_shows, key=lambda x: x['reach'], reverse=True)

    # Query 2: Platform distribution
    if use_rankings_table:
        platform_rows, platform_cols = get_db_data("""
            SELECT w.platform, COUNT(*) as count 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.platform IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.platform 
            ORDER BY count DESC
        """, (selected_week,))
    else:
        platform_rows, platform_cols = get_db_data("""
            SELECT platform, COUNT(*) as count 
            FROM shows 
            WHERE platform IS NOT NULL AND current_rank IS NOT NULL 
            GROUP BY platform 
            ORDER BY count DESC
        """)
    platforms = []
    for row in platform_rows:
        platforms.append({
            'platform': row[0],
            'count': int(row[1])
        })

    # Query 2b: Format distribution by reach
    if use_rankings_table:
        format_rows, _ = get_db_data("""
            SELECT w.content_format, SUM(w.reach) as total_reach 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.content_format IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.content_format 
            ORDER BY total_reach DESC
        """, (selected_week,))
    else:
        format_rows, _ = get_db_data("""
            SELECT content_format, SUM(reach) as total_reach 
            FROM shows 
            WHERE content_format IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
            GROUP BY content_format 
            ORDER BY total_reach DESC
        """)
    formats_by_reach = []
    for row in format_rows:
        formats_by_reach.append({
            'format': row[0],
            'reach': round(float(row[1]), 2)
        })

    # Query 3: Genre reach
    if use_rankings_table:
        genre_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, g.genre 
            FROM show_weekly_rankings w 
            JOIN show_genres g ON w.show_id = g.show_id 
            WHERE w.week = %s AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
        genre_rows, _ = get_db_data("""
            SELECT s.id, s.reach, g.genre 
            FROM shows s 
            JOIN show_genres g ON s.id = g.show_id 
            WHERE s.reach IS NOT NULL AND s.current_rank IS NOT NULL
        """)
    
    show_genres_map = {}
    for show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        if show_id not in show_genres_map:
            show_genres_map[show_id] = (float(reach) if reach is not None else 0.0, set())
        show_genres_map[show_id][1].add(norm_genre)
        
    genre_reach_map = {}
    for show_id, (reach, genres) in show_genres_map.items():
        for genre in genres:
            genre_reach_map[genre] = genre_reach_map.get(genre, 0.0) + reach
            
    total_genre_reach = sum(genre_reach_map.values())
    genre_percentages = []
    if total_genre_reach > 0:
        for genre, reach in genre_reach_map.items():
            pct = (reach / total_genre_reach) * 100
            genre_percentages.append({
                'genre': genre,
                'reach': round(reach, 2),
                'percentage': round(pct, 2)
            })
        genre_percentages = sorted(genre_percentages, key=lambda x: x['percentage'], reverse=True)

    # Query 4: Language reach
    if use_rankings_table:
        lang_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, s.languages 
            FROM show_weekly_rankings w 
            JOIN shows s ON w.show_id = s.id 
            WHERE w.week = %s AND s.languages IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
        lang_rows, _ = get_db_data("""
            SELECT id, reach, languages 
            FROM shows 
            WHERE languages IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL
        """)
        
    show_langs_map = {}
    for show_id, reach, languages_str in lang_rows:
        if not languages_str:
            continue
        parts = languages_str.split(',')
        unique_langs = set()
        for p in parts:
            lang = p.strip().title()
            if lang:
                unique_langs.add(lang)
        show_langs_map[show_id] = (float(reach) if reach is not None else 0.0, unique_langs)
        
    lang_reach_map = {}
    for show_id, (reach, langs) in show_langs_map.items():
        for lang in langs:
            lang_reach_map[lang] = lang_reach_map.get(lang, 0.0) + reach
            
    total_lang_reach = sum(lang_reach_map.values())
    lang_percentages = []
    if total_lang_reach > 0:
        for lang, reach in lang_reach_map.items():
            pct = (reach / total_lang_reach) * 100
            lang_percentages.append({
                'language': lang,
                'reach': round(reach, 2),
                'percentage': round(pct, 2)
            })
        lang_percentages = sorted(lang_percentages, key=lambda x: x['percentage'], reverse=True)

    # Load metadata from metadata.json
    metadata = {
        "time_period": "WK-26, 2026 ( 27 Jun 2026 - 3 Jul 2026 )",
        "market": "ALL INDIA"
    }
    if os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                # If nested week dictionary
                if selected_week in loaded_meta:
                    metadata = loaded_meta[selected_week]
                # Fallback for old single-week metadata format
                elif "time_period" in loaded_meta:
                    metadata = loaded_meta
        except Exception as e:
            print(f"Warning: Could not read metadata.json: {e}")

    return render_template(
        "analytics.html", 
        top_shows=top_shows, 
        platforms=platforms, 
        formats_by_reach=formats_by_reach,
        genre_percentages=genre_percentages, 
        lang_percentages=lang_percentages,
        metadata=metadata,
        available_weeks=available_weeks,
        selected_week=selected_week
    )

@trends_bp.route("/api/analytics")
def api_analytics_json():
    # Check if we have weekly rankings table populated
    has_rankings_row, _ = get_db_data("SELECT 1 FROM show_weekly_rankings LIMIT 1")
    use_rankings_table = bool(has_rankings_row)

    available_weeks = []
    selected_week = None

    if use_rankings_table:
        weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
        def sort_weeks_key(w_code):
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key, reverse=True)
        
        selected_week = request.args.get("week")
        if not selected_week and available_weeks:
            selected_week = available_weeks[0]

    # Fallback default if not set or empty
    if not selected_week:
        selected_week = "WK-26,2026"

    # Query 1: Top 10 content
    if use_rankings_table:
        top_shows_rows, top_shows_cols = get_db_data("""
            SELECT s.title, w.reach, s.global_rating 
            FROM shows s 
            JOIN show_weekly_rankings w ON s.id = w.show_id 
            WHERE w.week = %s 
              AND w.current_rank IS NOT NULL 
              AND (w.content_type IS NULL OR LOWER(w.content_type) != 'sports')
            ORDER BY w.current_rank ASC 
            LIMIT 10
        """, (selected_week,))
    else:
        top_shows_rows, top_shows_cols = get_db_data("""
            SELECT title, reach, global_rating 
            FROM shows 
            WHERE current_rank IS NOT NULL 
              AND (content_type IS NULL OR LOWER(content_type) != 'sports')
            ORDER BY current_rank ASC 
            LIMIT 10
        """)
        
    top_shows = []
    for row in top_shows_rows:
        show = dict(zip(top_shows_cols, row))
        show['reach'] = float(show['reach']) if show['reach'] is not None else 0.0
        show['global_rating'] = float(show['global_rating']) if show['global_rating'] is not None else 0.0
        top_shows.append(show)
    top_shows = sorted(top_shows, key=lambda x: x['reach'], reverse=True)

    # Query 2: Platform distribution
    if use_rankings_table:
        platform_rows, platform_cols = get_db_data("""
            SELECT w.platform, COUNT(*) as count 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.platform IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.platform 
            ORDER BY count DESC
        """, (selected_week,))
    else:
        platform_rows, platform_cols = get_db_data("""
            SELECT platform, COUNT(*) as count 
            FROM shows 
            WHERE platform IS NOT NULL AND current_rank IS NOT NULL 
            GROUP BY platform 
            ORDER BY count DESC
        """)
    platforms = []
    for row in platform_rows:
        platforms.append({
            'platform': row[0],
            'count': int(row[1])
        })

    # Query 2b: Format distribution by reach
    if use_rankings_table:
        format_rows, _ = get_db_data("""
            SELECT w.content_format, SUM(w.reach) as total_reach 
            FROM show_weekly_rankings w 
            WHERE w.week = %s AND w.content_format IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL 
            GROUP BY w.content_format 
            ORDER BY total_reach DESC
        """, (selected_week,))
    else:
        format_rows, _ = get_db_data("""
            SELECT content_format, SUM(reach) as total_reach 
            FROM shows 
            WHERE content_format IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
            GROUP BY content_format 
            ORDER BY total_reach DESC
        """)
    formats_by_reach = []
    for row in format_rows:
        formats_by_reach.append({
            'format': row[0],
            'reach': round(float(row[1]), 2)
        })

    # Query 3: Genre reach
    if use_rankings_table:
        genre_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, g.genre 
            FROM show_weekly_rankings w 
            JOIN show_genres g ON w.show_id = g.show_id 
            WHERE w.week = %s AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
        genre_rows, _ = get_db_data("""
            SELECT s.id, s.reach, g.genre 
            FROM shows s 
            JOIN show_genres g ON s.id = g.show_id 
            WHERE s.reach IS NOT NULL AND s.current_rank IS NOT NULL
        """)
    
    show_genres_map = {}
    for show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        if show_id not in show_genres_map:
            show_genres_map[show_id] = (float(reach) if reach is not None else 0.0, set())
        show_genres_map[show_id][1].add(norm_genre)
        
    genre_reach_map = {}
    for show_id, (reach, genres) in show_genres_map.items():
        for genre in genres:
            genre_reach_map[genre] = genre_reach_map.get(genre, 0.0) + reach
            
    total_genre_reach = sum(genre_reach_map.values())
    genre_percentages = []
    if total_genre_reach > 0:
        for genre, reach in genre_reach_map.items():
            pct = (reach / total_genre_reach) * 100
            genre_percentages.append({
                'genre': genre,
                'reach': round(reach, 2),
                'percentage': round(pct, 2)
            })
        genre_percentages = sorted(genre_percentages, key=lambda x: x['percentage'], reverse=True)

    # Query 4: Language reach
    if use_rankings_table:
        lang_rows, _ = get_db_data("""
            SELECT w.show_id, w.reach, s.languages 
            FROM show_weekly_rankings w 
            JOIN shows s ON w.show_id = s.id 
            WHERE w.week = %s AND s.languages IS NOT NULL AND w.reach IS NOT NULL AND w.current_rank IS NOT NULL
        """, (selected_week,))
    else:
        lang_rows, _ = get_db_data("""
            SELECT id, reach, languages 
            FROM shows 
            WHERE languages IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL
        """)
        
    show_langs_map = {}
    for show_id, reach, languages_str in lang_rows:
        if not languages_str:
            continue
        parts = languages_str.split(',')
        unique_langs = set()
        for p in parts:
            lang = p.strip().title()
            if lang:
                unique_langs.add(lang)
        show_langs_map[show_id] = (float(reach) if reach is not None else 0.0, unique_langs)
        
    lang_reach_map = {}
    for show_id, (reach, langs) in show_langs_map.items():
        for lang in langs:
            lang_reach_map[lang] = lang_reach_map.get(lang, 0.0) + reach
            
    total_lang_reach = sum(lang_reach_map.values())
    lang_percentages = []
    if total_lang_reach > 0:
        for lang, reach in lang_reach_map.items():
            pct = (reach / total_lang_reach) * 100
            lang_percentages.append({
                'language': lang,
                'reach': round(reach, 2),
                'percentage': round(pct, 2)
            })
        lang_percentages = sorted(lang_percentages, key=lambda x: x['percentage'], reverse=True)

    # Load metadata from metadata.json
    metadata = {
        "time_period": "WK-26, 2026 ( 27 Jun 2026 - 3 Jul 2026 )",
        "market": "ALL INDIA"
    }
    if os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                # If nested week dictionary
                if selected_week in loaded_meta:
                    metadata = loaded_meta[selected_week]
                # Fallback for old single-week metadata format
                elif "time_period" in loaded_meta:
                    metadata = loaded_meta
        except Exception as e:
            print(f"Warning: Could not read metadata.json: {e}")

    return jsonify({
        'top_shows': top_shows,
        'platforms': platforms,
        'formats_by_reach': formats_by_reach,
        'genre_percentages': genre_percentages,
        'lang_percentages': lang_percentages,
        'metadata': metadata,
        'available_weeks': available_weeks,
        'selected_week': selected_week
    })

@trends_bp.route("/api/platform_analytics")
def api_platform_analytics():
    # 1. Total content count platform-wise
    plat_rows, _ = get_db_data("""
        SELECT platform, COUNT(*) as count 
        FROM shows 
        WHERE platform IS NOT NULL 
        GROUP BY platform 
        ORDER BY count DESC
    """)
    platforms = []
    for r in plat_rows:
        platforms.append({
            'platform': r[0],
            'count': int(r[1])
        })
        
    # 2. Paid vs Free count platform-wise
    paid_free_rows, _ = get_db_data("""
        SELECT platform, paid_free, COUNT(*) as count 
        FROM shows 
        WHERE platform IS NOT NULL AND paid_free IS NOT NULL 
        GROUP BY platform, paid_free
    """)
    
    paid_free_data = {}
    for r in paid_free_rows:
        plat = r[0]
        pf_type = r[1]
        count = int(r[2])
        if plat not in paid_free_data:
            paid_free_data[plat] = {'Paid': 0, 'Free': 0}
        
        if pf_type in ['Paid', 'Free']:
            paid_free_data[plat][pf_type] = count
        elif pf_type.lower() == 'paid':
            paid_free_data[plat]['Paid'] = count
        elif pf_type.lower() == 'free':
            paid_free_data[plat]['Free'] = count
            
    paid_free_list = []
    for plat, counts in paid_free_data.items():
        paid_free_list.append({
            'platform': plat,
            'Paid': counts['Paid'],
            'Free': counts['Free']
        })
        
    response = jsonify({
        'platforms': platforms,
        'paid_free': paid_free_list
    })
    response.headers['Cache-Control'] = 'public, max-age=300'  # cache 5 minutes
    return response

@trends_bp.route("/api/all_shows")
def api_all_shows():
    shows_rows, _ = get_db_data("SELECT id, title FROM shows ORDER BY title")
    shows = [{'id': r[0], 'title': r[1]} for r in shows_rows]
    return jsonify({'shows': shows})

@trends_bp.route("/api/trending_metadata")
def api_trending_metadata():
    weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
    def sort_weeks_key(w_code):
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
    available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key)
    
    latest_metadata = {
        "time_period": "Historical Trends",
        "market": "ALL INDIA"
    }
    if available_weeks and os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                latest_week = available_weeks[-1]
                if latest_week in loaded_meta:
                    latest_metadata = loaded_meta[latest_week]
                elif "time_period" in loaded_meta:
                    latest_metadata = loaded_meta
        except Exception:
            pass
            
    return jsonify({
        'weeks': available_weeks,
        'metadata': latest_metadata
    })

@trends_bp.route("/trending")
def trending():
    shows_rows, _ = get_db_data("SELECT id, title FROM shows ORDER BY title")
    shows = [{'id': r[0], 'title': r[1]} for r in shows_rows]
    
    weeks_rows, _ = get_db_data("SELECT DISTINCT week FROM show_weekly_rankings")
    def sort_weeks_key(w_code):
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
    available_weeks = sorted([r[0] for r in weeks_rows if r[0]], key=sort_weeks_key)
    
    latest_metadata = {
        "time_period": "Historical Trends",
        "market": "ALL INDIA"
    }
    if available_weeks and os.path.exists("metadata.json"):
        try:
            with open("metadata.json", "r") as f:
                loaded_meta = json.load(f)
                latest_week = available_weeks[-1]
                if latest_week in loaded_meta:
                    latest_metadata = loaded_meta[latest_week]
                elif "time_period" in loaded_meta:
                    latest_metadata = loaded_meta
        except Exception:
            pass
            
    return render_template("trending.html", shows=shows, weeks=available_weeks, metadata=latest_metadata)

@trends_bp.route("/api/show_trends")
def api_show_trends():
    show_id = request.args.get("show_id")
    if not show_id:
        return jsonify({'error': 'show_id is required'}), 400
        
    rows, _ = get_db_data("""
        SELECT week, current_rank, reach 
        FROM show_weekly_rankings 
        WHERE show_id = %s
    """, (show_id,))
    
    def sort_weeks_key(row):
        w_code = row[0]
        match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
        if match:
            return (int(match.group(2)), int(match.group(1)))
        return (0, 0)
        
    sorted_rows = sorted(rows, key=sort_weeks_key)
    
    weeks = [r[0] for r in sorted_rows]
    ranks = [int(r[1]) if r[1] is not None else None for r in sorted_rows]
    reach = [round(float(r[2]), 2) if r[2] is not None else 0.0 for r in sorted_rows]
    
    title_rows, _ = get_db_data("SELECT title FROM shows WHERE id = %s", (show_id,))
    title = title_rows[0][0] if title_rows else "Unknown Show"
    
    return jsonify({
        'title': title,
        'weeks': weeks,
        'ranks': ranks,
        'reach': reach
    })

@trends_bp.route("/api/content_trends")
def api_content_trends():
    plat_rows, _ = get_db_data("""
        SELECT week, platform, SUM(reach) as total_reach 
        FROM show_weekly_rankings 
        WHERE platform IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
        GROUP BY week, platform
    """)
    
    format_rows, _ = get_db_data("""
        SELECT week, content_format, SUM(reach) as total_reach 
        FROM show_weekly_rankings 
        WHERE content_format IS NOT NULL AND reach IS NOT NULL AND current_rank IS NOT NULL 
        GROUP BY week, content_format
    """)
    
    def sort_weeks(w_list):
        def sort_weeks_key(w_code):
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        return sorted(list(set(w_list)), key=sort_weeks_key)
        
    plat_weeks = sort_weeks([r[0] for r in plat_rows])
    platforms = list(set([r[1] for r in plat_rows]))
    
    plat_trends = {p: [0.0] * len(plat_weeks) for p in platforms}
    for week, platform, reach in plat_rows:
        if week in plat_weeks:
            w_idx = plat_weeks.index(week)
            plat_trends[platform][w_idx] = round(float(reach), 2)
            
    form_weeks = sort_weeks([r[0] for r in format_rows])
    formats = list(set([r[1] for r in format_rows]))
    
    form_trends = {f: [0.0] * len(form_weeks) for f in formats}
    for week, content_format, reach in format_rows:
        if week in form_weeks:
            w_idx = form_weeks.index(week)
            form_trends[content_format][w_idx] = round(float(reach), 2)
            
    return jsonify({
        'platforms': {
            'weeks': plat_weeks,
            'labels': platforms,
            'trends': plat_trends
        },
        'formats': {
            'weeks': form_weeks,
            'labels': formats,
            'trends': form_trends
        }
    })

@trends_bp.route("/api/genre_trends")
def api_genre_trends():
    genre_rows, _ = get_db_data("""
        SELECT w.week, w.show_id, w.reach, g.genre 
        FROM show_weekly_rankings w 
        JOIN show_genres g ON w.show_id = g.show_id 
        WHERE w.reach IS NOT NULL AND w.current_rank IS NOT NULL
    """)
    
    lang_rows, _ = get_db_data("""
        SELECT w.week, w.show_id, w.reach, s.languages 
        FROM show_weekly_rankings w 
        JOIN shows s ON w.show_id = s.id 
        WHERE w.reach IS NOT NULL AND w.current_rank IS NOT NULL AND s.languages IS NOT NULL
    """)
    
    def sort_weeks(w_list):
        def sort_weeks_key(w_code):
            match = re.search(r'WK-(\d+)\s*,\s*(\d+)', str(w_code))
            if match:
                return (int(match.group(2)), int(match.group(1)))
            return (0, 0)
        return sorted(list(set(w_list)), key=sort_weeks_key)
        
    weeks_set = set()
    weekly_genre_totals = {}
    
    for week, show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        weeks_set.add(week)
        if week not in weekly_genre_totals:
            weekly_genre_totals[week] = {}
        
    show_genres_by_week = {}
    for week, show_id, reach, genre in genre_rows:
        norm_genre = normalize_genre(genre)
        if not norm_genre:
            continue
        weeks_set.add(week)
        if week not in show_genres_by_week:
            show_genres_by_week[week] = {}
        if show_id not in show_genres_by_week[week]:
            show_genres_by_week[week][show_id] = (float(reach), set())
        show_genres_by_week[week][show_id][1].add(norm_genre)
        
    genre_weeks = sort_weeks(list(weeks_set))
    all_genres = set()
    
    weekly_genre_shares = {w: {} for w in genre_weeks}
    for week in genre_weeks:
        if week in show_genres_by_week:
            for show_id, (reach, genres) in show_genres_by_week[week].items():
                for genre in genres:
                    all_genres.add(genre)
                    weekly_genre_shares[week][genre] = weekly_genre_shares[week].get(genre, 0.0) + reach
                    
    genres_list = sorted(list(all_genres))
    genre_trends = {g: [0.0] * len(genre_weeks) for g in genres_list}
    for w_idx, week in enumerate(genre_weeks):
        total_week_reach = sum(weekly_genre_shares[week].values())
        if total_week_reach > 0:
            for genre in genres_list:
                share_pct = (weekly_genre_shares[week].get(genre, 0.0) / total_week_reach) * 100
                genre_trends[genre][w_idx] = round(share_pct, 2)

    show_langs_by_week = {}
    lang_weeks_set = set()
    for week, show_id, reach, languages_str in lang_rows:
        if not languages_str:
            continue
        lang_weeks_set.add(week)
        parts = languages_str.split(',')
        unique_langs = set()
        for p in parts:
            lang = p.strip().title()
            if lang:
                unique_langs.add(lang)
        if week not in show_langs_by_week:
            show_langs_by_week[week] = {}
        show_langs_by_week[week][show_id] = (float(reach), unique_langs)
        
    lang_weeks = sort_weeks(list(lang_weeks_set))
    all_langs = set()
    
    weekly_lang_shares = {w: {} for w in lang_weeks}
    for week in lang_weeks:
        if week in show_langs_by_week:
            for show_id, (reach, langs) in show_langs_by_week[week].items():
                for lang in langs:
                    all_langs.add(lang)
                    weekly_lang_shares[week][lang] = weekly_lang_shares[week].get(lang, 0.0) + reach
                    
    langs_list = sorted(list(all_langs))
    lang_trends = {l: [0.0] * len(lang_weeks) for l in langs_list}
    for w_idx, week in enumerate(lang_weeks):
        total_week_reach = sum(weekly_lang_shares[week].values())
        if total_week_reach > 0:
            for lang in langs_list:
                share_pct = (weekly_lang_shares[week].get(lang, 0.0) / total_week_reach) * 100
                lang_trends[lang][w_idx] = round(share_pct, 2)
                
    return jsonify({
        'genres': {
            'weeks': genre_weeks,
            'labels': genres_list,
            'trends': genre_trends
        },
        'languages': {
            'weeks': lang_weeks,
            'labels': langs_list,
            'trends': lang_trends
        }
    })

@trends_bp.route("/update")
def update():
    # Trigger the scraper in a completely independent background process
    subprocess.Popen([sys.executable, "scraper.py"])
    return redirect(url_for('shows.index', syncing='true'))

@trends_bp.route("/sync_status")
def sync_status():
    running = os.path.exists("scraper.lock")
    return {"status": "syncing" if running else "idle"}
