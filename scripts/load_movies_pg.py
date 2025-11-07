#!/usr/bin/env python3
"""
Load movies CSV into a Postgres database. Connection uses environment variables or CLI args.
Usage: python scripts/load_movies_pg.py /path/to/movies_metadata.csv

Environment variables (fall back to defaults):
  DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD
"""
import os
import csv
import json
import sys
import psycopg2
import re
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)

CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./movies_metadata.csv")
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "bd_postgres.sql"

DB_HOST = os.environ.get('DATABASE_HOST', 'localhost')
DB_PORT = os.environ.get('DATABASE_PORT', '5432')
DB_NAME = os.environ.get('DATABASE_NAME', 'movies_db')
DB_USER = os.environ.get('DATABASE_USER', 'postgres')
DB_PASS = os.environ.get('DATABASE_PASSWORD', '')

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_json_field(val):
    if not val or val.strip() == "":
        return []
    try:
        return json.loads(val)
    except Exception:
        try:
            txt = val.replace("'", '"')
            txt = txt.replace('None', 'null')
            txt = txt.replace('True', 'true').replace('False', 'false')
            return json.loads(txt)
        except Exception:
            return []


def sanitize_date(val):
    """Return a YYYY-MM-DD string or None. Try several common formats and normalize to ISO date.

    If parsing fails, return None (so Postgres stores NULL).
    """
    if not val:
        return None
    s = val.strip()
    if s == "":
        return None
    # Direct match YYYY-MM-DD
    if DATE_RE.match(s):
        return s

    # Try known common formats
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s[:10], fmt) if fmt == "%Y-%m-%d" or fmt == "%m/%d/%Y" else datetime.strptime(s, fmt)
            return dt.date().isoformat()
        except Exception:
            continue

    # As a last resort, if first 10 chars look like YYYY-MM-DD, accept that slice
    if len(s) >= 10 and DATE_RE.match(s[:10]):
        return s[:10]

    logging.debug("Unparseable release_date '%s' -> storing NULL", s)
    return None


def apply_schema(conn):
    sql = SCHEMA_FILE.read_text()
    cur = conn.cursor()
    # Split statements by semicolon and execute each to avoid psycopg2 error with multi-statement execution
    for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
        cur.execute(stmt)
    conn.commit()


def get_or_create_genre(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT id FROM genres WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO genres(name) VALUES(%s) RETURNING id", (name,))
    gid = cur.fetchone()[0]
    conn.commit()
    return gid


def get_or_create_company(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT id FROM production_companies WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO production_companies(name) VALUES(%s) RETURNING id", (name,))
    cid = cur.fetchone()[0]
    conn.commit()
    return cid

def ensure_database_exists():
    tmp_conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname='postgres', user=DB_USER, password=DB_PASS)
    tmp_conn.autocommit = True
    cur = tmp_conn.cursor()
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {DB_NAME}")
        print(f"Database {DB_NAME} created.")
    tmp_conn.close()

def main():
    if not CSV_PATH.exists():
        print(f"CSV file not found: {CSV_PATH}")
        sys.exit(1)

    ensure_database_exists()
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    apply_schema(conn)

    skipped_rows = 0
    inserted = 0
    malformed_dates = 0

    with CSV_PATH.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        cur = conn.cursor()
        for idx, row in enumerate(reader, start=1):
            try:
                movie_id = int(row.get('id')) if row.get('id') else None
            except Exception:
                movie_id = None
            # Skip rows without a valid numeric id to avoid inserting NULL into PK
            if movie_id is None:
                skipped_rows += 1
                logging.debug("Skipping row %d: missing/invalid id", idx)
                continue
            imdb_id = row.get('imdb_id')
            title = row.get('title')
            original_title = row.get('original_title')
            overview = row.get('overview')
            # sanitize release_date so empty strings don't get inserted into a DATE column
            release_date_raw = row.get('release_date')
            release_date = sanitize_date(release_date_raw)
            if release_date_raw and not release_date:
                malformed_dates += 1
                logging.debug("Row %d: malformed release_date '%s'", idx, release_date_raw)
            adult = row.get('adult') in ('True', 'true', '1', 't')
            try:
                budget = int(row.get('budget')) if row.get('budget') else 0
            except Exception:
                budget = 0
            try:
                revenue = int(row.get('revenue')) if row.get('revenue') else 0
            except Exception:
                revenue = 0
            try:
                runtime = float(row.get('runtime')) if row.get('runtime') else None
            except Exception:
                runtime = None
            try:
                popularity = float(row.get('popularity')) if row.get('popularity') else None
            except Exception:
                popularity = None
            try:
                vote_average = float(row.get('vote_average')) if row.get('vote_average') else None
            except Exception:
                vote_average = None
            try:
                vote_count = int(row.get('vote_count')) if row.get('vote_count') else None
            except Exception:
                vote_count = None

            original_language = row.get('original_language')
            status = row.get('status')
            tagline = row.get('tagline')
            homepage = row.get('homepage')
            poster_path = row.get('poster_path')

            raw_genres = row.get('genres')
            raw_companies = row.get('production_companies')

            # Insert movie
            try:
                cur.execute(
                    "INSERT INTO movies(id, imdb_id, title, original_title, overview, release_date, adult, budget, revenue, runtime, popularity, vote_average, vote_count, original_language, status, tagline, homepage, poster_path, raw_genres, raw_production_companies) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title",
                    (movie_id, imdb_id, title, original_title, overview, release_date, adult, budget, revenue, runtime, popularity, vote_average, vote_count, original_language, status, tagline, homepage, poster_path, raw_genres, raw_companies)
                )
                inserted += 1
            except Exception as e:
                logging.exception("Failed to insert movie id=%s at row %d: %s", movie_id, idx, e)
                # skip to next row without aborting entire load
                continue

            # Handle genres
            genres_list = parse_json_field(raw_genres)
            if isinstance(genres_list, dict):
                genres_list = [genres_list]
            for g in genres_list:
                name = g.get('name') if isinstance(g, dict) else None
                if name:
                    gid = get_or_create_genre(conn, name)
                    try:
                        cur.execute("INSERT INTO movie_genres(movie_id, genre_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (movie_id, gid))
                    except Exception:
                        pass

            # Handle companies
            comp_list = parse_json_field(raw_companies)
            if isinstance(comp_list, dict):
                comp_list = [comp_list]
            for c in comp_list:
                name = c.get('name') if isinstance(c, dict) else None
                if name:
                    cid = get_or_create_company(conn, name)
                    try:
                        cur.execute("INSERT INTO movie_companies(movie_id, company_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (movie_id, cid))
                    except Exception:
                        pass

        conn.commit()
    conn.close()
    print(f"Loaded data into Postgres DB: inserted={inserted}, skipped_rows={skipped_rows}, malformed_dates={malformed_dates}")


if __name__ == '__main__':
    main()
