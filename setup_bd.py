#!/usr/bin/env python3
"""
Complete setup script for movies database:
1. Wait for Postgres to be ready (if using Postgres)
2. Download the movies dataset from Kaggle
3. Load data into Postgres database

Usage: python setup_movies_db.py [--data-dir /path/to/data]

Environment variables:
  DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD
  If DATABASE_HOST is not set, the script will use SQLite instead.
"""
import os
import csv
import json
import sys
import re
import time
import zipfile
import requests
import psycopg2
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import logging
from psycopg2.extras import execute_values
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)

    DB_HOST = parsed.hostname
    DB_PORT = parsed.port or 5432  # Default to 5432 if port not specified
    DB_NAME = parsed.path.lstrip("/")
    DB_USER = parsed.username
    DB_PASS = parsed.password

    DB_PORT = int(DB_PORT)

    logging.info("Usando configuração de base de dados a partir de DATABASE_URL")
    logging.info(f"DB_HOST={DB_HOST}, DB_PORT={DB_PORT}, DB_NAME={DB_NAME}, DB_USER={DB_USER}")
    
    if not DB_HOST:
        logging.error("DATABASE_URL provided but hostname is missing!")
        sys.exit(1)
else:
    # Fall back para variáveis tradicionais
    DB_HOST = os.environ.get('DATABASE_HOST')
    DB_PORT = os.environ.get('DATABASE_PORT', '5432')
    DB_NAME = os.environ.get('DATABASE_NAME', 'movies_db')
    DB_USER = os.environ.get('DATABASE_USER', 'postgres')
    DB_PASS = os.environ.get('DATABASE_PASSWORD', '')

    DB_PORT = int(DB_PORT)

    logging.info("Usando DATABASE_HOST / DATABASE_USER / etc. (DATABASE_URL não encontrada)")
    logging.info(f"DB_HOST={DB_HOST}, DB_PORT={DB_PORT}, DB_NAME={DB_NAME}, DB_USER={DB_USER}")
    
    if not DB_HOST:
        logging.error("Neither DATABASE_URL nor DATABASE_HOST is set. Cannot connect to database.")
        sys.exit(1)

# Dataset configuration
KAGGLE_DATASET_URL = "https://www.kaggle.com/api/v1/datasets/download/rounakbanik/the-movies-dataset"
CSV_FILENAME = "movies_metadata.csv"
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def wait_for_postgres(host, port, user, max_attempts=30):
    """Wait for Postgres to be ready using pg_isready."""
    logging.info(f"Waiting for postgres at {host}:{port}...")

    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                ['pg_isready', '-h', host, '-p', str(port), '-U', user],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logging.info("Postgres is ready")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # If pg_isready is not available, try a direct connection
            try:
                conn = psycopg2.connect(
                    host=host, port=port, dbname='postgres',
                    user=user, password=DB_PASS, connect_timeout=3
                )
                conn.close()
                logging.info("Postgres is ready")
                return True
            except Exception:
                pass

        if attempt < max_attempts:
            time.sleep(1)

    logging.error("Postgres did not become ready in time")
    return False


def download_dataset(save_dir):
    """Download and extract the movies dataset."""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    zip_path = save_dir / "the-movies-dataset.zip"
    csv_path = save_dir / CSV_FILENAME

    # Check if CSV already exists
    if csv_path.exists():
        logging.info(f"CSV file already exists at {csv_path}")
        return csv_path

    # Try to download the dataset
    logging.info(f"Downloading dataset to {zip_path}")
    try:
        response = requests.get(KAGGLE_DATASET_URL, stream=True, timeout=30)
        response.raise_for_status()

        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info("Download complete")
    except Exception as e:
        logging.error(f"Download failed: {e}")
        logging.info("To download manually, use the Kaggle CLI:")
        logging.info(f"  kaggle datasets download -d rounakbanik/the-movies-dataset -p {save_dir}")
        logging.info(f"Or manually place {CSV_FILENAME} into {save_dir}")

        if not csv_path.exists():
            raise FileNotFoundError(f"Could not download dataset and {csv_path} does not exist")
        return csv_path

    # Extract the zip file
    if zip_path.exists():
        logging.info("Unzipping dataset...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(save_dir)
            logging.info("Extraction complete")
        except Exception as e:
            logging.error(f"Failed to extract zip: {e}")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV {CSV_FILENAME} not found after extraction")

    return csv_path


def get_schema_sql():
    """Return the database schema SQL."""
    return """
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        imdb_id TEXT,
        title TEXT,
        original_title TEXT,
        overview TEXT,
        release_date DATE,
        adult BOOLEAN,
        budget BIGINT,
        revenue BIGINT,
        runtime REAL,
        popularity REAL,
        vote_average REAL,
        vote_count BIGINT,
        original_language TEXT,
        status TEXT,
        tagline TEXT,
        homepage TEXT,
        poster_path TEXT,
        raw_genres TEXT,
        raw_production_companies TEXT
    );

    CREATE TABLE IF NOT EXISTS genres (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS production_companies (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS movie_genres (
        movie_id INTEGER REFERENCES movies(id),
        genre_id INTEGER REFERENCES genres(id),
        PRIMARY KEY (movie_id, genre_id)
    );

    CREATE TABLE IF NOT EXISTS movie_companies (
        movie_id INTEGER REFERENCES movies(id),
        company_id INTEGER REFERENCES production_companies(id),
        PRIMARY KEY (movie_id, company_id)
    );

    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user' NOT NULL CHECK (role IN ('user', 'admin')),
        profile_picture_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id INTEGER,
        movie_id INTEGER,
        rating REAL NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, movie_id)
    );

    CREATE INDEX IF NOT EXISTS idx_movies_release_date ON movies(release_date);
    CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title);
    """


def apply_schema(conn):
    """Apply database schema."""
    sql_schema = get_schema_sql()
    cur = conn.cursor()
    for stmt in [s.strip() for s in sql_schema.split(';') if s.strip()]:
        cur.execute(stmt)


    conn.commit()
    cur.close()


def create_admin_user(conn):
    """Create default admin user if it doesn't exist."""
    import hashlib
    
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
    
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (admin_username, admin_email))
    if cur.fetchone():
        logging.info(f"Admin user '{admin_username}' already exists. Skipping creation.")
        cur.close()
        return
    
    try:
        cur.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'admin') RETURNING id",
            (admin_username, admin_email, password_hash)
        )
        admin_id = cur.fetchone()[0]
        conn.commit()
        logging.info(f"Admin user '{admin_username}' created successfully (ID: {admin_id})")
        logging.info(f"Admin credentials - Username: {admin_username}, Email: {admin_email}")
        logging.warning(f"Default admin password is '{admin_password}'. Please change it after first login!")
    except Exception as e:
        logging.error(f"Failed to create admin user: {e}")
        conn.rollback()
    finally:
        cur.close()


def ensure_database_exists():
    """Create database if it doesn't exist."""
    tmp_conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname='postgres',
        user=DB_USER, password=DB_PASS
    )
    tmp_conn.autocommit = True
    cur = tmp_conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {DB_NAME}")
        logging.info(f"Database {DB_NAME} created")
    cur.close()
    tmp_conn.close()


def get_or_create_genre(conn, name):
    """Get or create a genre by name."""
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
    """Get or create a production company by name."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM production_companies WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO production_companies(name) VALUES(%s) RETURNING id", (name,))
    cid = cur.fetchone()[0]
    conn.commit()
    return cid


def parse_real(value):
    """Parse a float value, returning None if empty or invalid."""
    try:
        return float(value) if value != "" else None
    except Exception:
        return None


def parse_int(value):
    """Parse an integer value, returning None if empty or invalid."""
    try:
        return int(value) if value != "" else None
    except Exception:
        return None


def parse_bool(value):
    """Parse a boolean value."""
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def parse_date(value):
    """Parse a date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except Exception:
        return None


def movies_table_has_data(conn) -> bool:
    """Check if the 'movies' table has any rows using COUNT(*)."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM movies;")
            row_count = cur.fetchone()[0]
            return row_count > 0
    except Exception as e:
        logging.debug(f"Could not check if 'movies' table has data: {e}")
        return False

def load_movies_and_ratings(movies_csv_path, ratings_csv_path, conn):
    """
    Load movies, genres, and ratings efficiently using batch inserts.
    """
    cur = conn.cursor()

    MAX_MOVIES = int(os.environ.get('MAX_MOVIES', '500'))
    logging.info(f"Limiting to {MAX_MOVIES} movies to save memory")

    # ----------------------------
    # Step 1: Load ratings CSV into memory map
    # ----------------------------
    logging.info("Loading ratings into memory...")
    ratings_map = {}  # key: old CSV movieId, value: list of (user_id, rating, timestamp)
    with open(ratings_csv_path, newline='', encoding='utf-8') as ratings_file:
        reader = csv.DictReader(ratings_file)
        for row in reader:
            movie_id = str(row['movieId'])
            ratings_map.setdefault(movie_id, []).append((
                int(row['userId']),
                float(row['rating']),
                int(row['timestamp'])
            ))

    # ----------------------------
    # Step 2: Process movies CSV
    # ----------------------------
    logging.info("Processing movies CSV...")
    movies_to_insert = []
    movie_id_map = {}  # CSV movie id -> DB movie id
    genres_to_insert = set()
    movie_genres_to_insert = []
    ratings_to_insert = []

    with open(movies_csv_path, newline='', encoding='utf-8') as movies_file:
        reader = csv.DictReader(movies_file)
        for row_num, row in enumerate(reader, start=1):
            if len(movies_to_insert) >= MAX_MOVIES:
                logging.info(f"Reached limit of {MAX_MOVIES} movies. Stopping processing.")
                break
                
            try:
                # Parse genres
                try:
                    genres_list = eval(row['genres']) if row.get('genres') else []
                    raw_genres = json.dumps(genres_list)
                except Exception as e:
                    logging.warning(f"Row {row_num}: Failed to parse genres. Using empty list. Error: {e}")
                    genres_list = []
                    raw_genres = '[]'

                # Sanitize fields
                release_date = parse_date(row.get('release_date', ''))
                adult = parse_bool(row.get('adult', False))
                budget = parse_int(row.get('budget', '0'))
                revenue = parse_int(row.get('revenue', '0'))
                runtime = parse_real(row.get('runtime', '0'))
                popularity = parse_real(row.get('popularity', '0'))
                vote_average = parse_real(row.get('vote_average', '0'))
                vote_count = parse_int(row.get('vote_count', '0'))

                # Prepare movie tuple
                movies_to_insert.append((
                    row.get('imdb_id'), row.get('title'), row.get('original_title'),
                    row.get('overview'), release_date, adult, budget, revenue, runtime,
                    popularity, vote_average, vote_count, row.get('original_language'),
                    row.get('status'), row.get('tagline'), row.get('poster_path'),
                    raw_genres, row['id']  # keep CSV id for mapping later
                ))

                # Collect genres
                for genre in genres_list:
                    genre_id = genre.get('id')
                    genre_name = genre.get('name')
                    if genre_id and genre_name:
                        genres_to_insert.add((genre_id, genre_name))

            except Exception as e:
                logging.error(f"Failed to process movie id={row.get('id')} at row {row_num}: {e}")

    # ----------------------------
    # Step 3: Insert genres
    # ----------------------------
    logging.info(f"Inserting {len(genres_to_insert)} genres...")
    execute_values(
        cur,
        """
        INSERT INTO genres(id, name) VALUES %s
        ON CONFLICT (id) DO NOTHING
        """,
        list(genres_to_insert)
    )

    # ----------------------------
    # Step 4: Insert movies and get DB IDs
    # ----------------------------
    logging.info(f"Inserting {len(movies_to_insert)} movies...")
    movie_id_map = {}
    for movie in movies_to_insert:
        cur.execute("""
            INSERT INTO movies(
                imdb_id, title, original_title, overview,
                release_date, adult, budget, revenue, runtime,
                popularity, vote_average, vote_count, original_language,
                status, tagline, poster_path, raw_genres
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, movie[:-1])
        db_movie_id = cur.fetchone()[0]
        csv_movie_id = movie[-1]
        movie_id_map[csv_movie_id] = db_movie_id

        # Prepare movie_genres batch
        raw_genres_list = json.loads(movie[16])
        for genre in raw_genres_list:
            genre_id = genre.get('id')
            if genre_id:
                movie_genres_to_insert.append((db_movie_id, genre_id))

        # Prepare ratings batch
        movie_ratings = ratings_map.get(str(csv_movie_id), [])
        for rating in movie_ratings:
            ratings_to_insert.append((
                rating[0], db_movie_id, rating[1], rating[2]
            ))

    conn.commit()  # commit movies, genres

    # ----------------------------
    # Step 5: Insert movie_genres
    # ----------------------------
    logging.info(f"Inserting {len(movie_genres_to_insert)} movie_genres...")
    execute_values(
        cur,
        """
        INSERT INTO movie_genres(movie_id, genre_id) VALUES %s
        ON CONFLICT (movie_id, genre_id) DO NOTHING
        """,
        movie_genres_to_insert
    )

    # ----------------------------
    # Step 6: Insert ratings
    # ----------------------------

    #cap ratings to 100k
    ratings_to_insert = ratings_to_insert[:100000]

    logging.info(f"Inserting {len(ratings_to_insert)} ratings...")
    execute_values(
        cur,
        """
        INSERT INTO ratings(user_id, movie_id, rating, timestamp)
        VALUES %s
        ON CONFLICT (user_id, movie_id) DO UPDATE
        SET rating = EXCLUDED.rating, timestamp = EXCLUDED.timestamp
        """,
        ratings_to_insert,
        template="(%s, %s, %s, to_timestamp(%s))"
    )

    conn.commit()
    cur.close()
    logging.info("Finished loading movies, genres, and ratings.")

def main():
    parser = argparse.ArgumentParser(description='Setup movies database')
    parser.add_argument('--data-dir', default='./data', help='Directory to save dataset')
    parser.add_argument('--skip-download', action='store_true', help='Skip dataset download')
    args = parser.parse_args()

    try:
        # Step 1: Validate configuration
        if not DB_HOST:
            logging.error("DATABASE_HOST not set. Postgres configuration required.")
            sys.exit(1)

        # Step 2: Wait for Postgres if configured
        if DB_HOST and DB_HOST != 'localhost':
            if not wait_for_postgres(DB_HOST, DB_PORT, DB_USER):
                logging.error("Failed to connect to Postgres")
                sys.exit(1)

        # Step 3: Ensure database exists
        ensure_database_exists()

        # Step 4: Connect to target database
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASS
        )

        # Step 5: Apply schema
        apply_schema(conn)

        # Step 6: Create admin user
        create_admin_user(conn)

        # Step 7: Check if movies table has data
        if movies_table_has_data(conn):
            logging.info("Movies table already has data. Skipping data load.")
            conn.close()
        else:
            logging.info("Movies table is empty. Downloading and loading data...")

            conn.close()

            # Download dataset if not skipped
            if not args.skip_download:
                csv_path = download_dataset(args.data_dir)
            else:
                csv_path = Path(args.data_dir) / CSV_FILENAME
                if not csv_path.exists():
                    logging.error(f"CSV file not found at {csv_path}")
                    sys.exit(1)

            # Reconnect and load data
            conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                user=DB_USER, password=DB_PASS
            )
            load_movies_and_ratings(csv_path,Path(args.data_dir) / "ratings.csv", conn)

            conn.close()

            logging.info("Data successfully loaded into Postgres!")

        logging.info("Setup complete!")

    except Exception as e:
        logging.exception(f"Setup failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()