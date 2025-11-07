#!/usr/bin/env bash
# Download the dataset zip using the Kaggle API URL then unzip and load into SQLite DB or Postgres.
# Usage: ./scripts/download_and_populate.sh /path/to/save_dir
set -euo pipefail
SAVE_DIR=${1:-./data}
mkdir -p "$SAVE_DIR"
ZIP_PATH="$SAVE_DIR/the-movies-dataset.zip"
CSV_NAME="movies_metadata.csv"

echo "Downloading dataset to $ZIP_PATH"
# Try curl to Kaggle API endpoint; if it fails, advise using kaggle CLI or manual download
if ! curl -L -o "$ZIP_PATH" "https://www.kaggle.com/api/v1/datasets/download/rounakbanik/the-movies-dataset"; then
  echo "curl download failed. If you're behind authentication, try using the kaggle CLI:"
  echo "  kaggle datasets download -d rounakbanik/the-movies-dataset -p $SAVE_DIR"
  echo "Or manually place $CSV_NAME into $SAVE_DIR"
fi

if [ -f "$ZIP_PATH" ]; then
  echo "Unzipping..."
  unzip -o "$ZIP_PATH" -d "$SAVE_DIR"
fi

if [ ! -f "$SAVE_DIR/$CSV_NAME" ]; then
  echo "CSV $CSV_NAME not found after unzip. If you already have the CSV locally, copy it to $SAVE_DIR/$CSV_NAME"
  ls -la "$SAVE_DIR" || true
  exit 1
fi

# Decide whether to load into Postgres or SQLite
if [ -n "${DATABASE_HOST:-}" ]; then
  echo "Detected DATABASE_HOST env var, populating Postgres database using psycopg2 script"
  python3 scripts/load_movies_pg.py "$SAVE_DIR/$CSV_NAME"
else
  echo "Populating SQLite DB..."
  python3 scripts/load_movies.py "$SAVE_DIR/$CSV_NAME" "$SAVE_DIR/movies.db"
fi

echo "Done. DB at $SAVE_DIR/movies.db"
