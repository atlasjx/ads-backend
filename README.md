# ads-backend

This repository contains a minimal Flask API and scripts to populate a movies database from the Kaggle "The Movies Dataset" CSV. It supports two population modes:
- SQLite (local) — `scripts/load_movies.py` + `bd.sql`
- PostgreSQL (Docker/compose) — `scripts/load_movies_pg.py` + `bd_postgres.sql`

There is also a `docker-compose.yml` with three services:
- `db` — Postgres database
- `web` — Flask app
- `populate` — one-shot job that downloads the dataset and populates the Postgres DB

This README explains how to run the stack, populate the database, and some troubleshooting tips.

---

## Requirements

- Docker (and docker compose) installed on your machine
- Optional: Python 3.8+ if you prefer running loaders locally
- (If you want automatic Kaggle downloads) Kaggle account and API token (~/.kaggle/kaggle.json) or otherwise download the CSV manually

---

## Quick start (Docker)

1. Build images and start only the DB

```bash
docker compose build
docker compose up -d db
```

2. Populate the DB (one-shot)

This step downloads the dataset (or uses a CSV you provide) and loads it into the Postgres database.

```bash
docker compose run --rm populate
```

If the Kaggle download fails (often requires authentication), see "If curl download fails" below.

3. Start the Flask app

```bash
docker compose up -d web
docker compose logs -f web
```

4. Verify data in Postgres

```bash
docker compose exec db psql -U movies_user -d movies_db -c "SELECT count(*) FROM movies;"
docker compose exec db psql -U movies_user -d movies_db -c "SELECT id, title FROM movies LIMIT 10;"
```

5. Tear down

```bash
docker compose down -v
```

---

## Using a local CSV (if Kaggle download fails)

If the dataset cannot be downloaded automatically (Kaggle auth required), download `movies_metadata.csv` manually and place it in a local `./data` folder. Then run the populate service while mounting that folder into the container.

```bash
mkdir -p data
# put movies_metadata.csv inside ./data
# run populate and mount local data folder into the container so the script finds the CSV
docker compose run --rm -v "$(pwd)/data:/data" populate
```

Or skip Docker and run the SQLite loader locally (fast for testing):

```bash
pip install -r requirements.txt
# Either download movies_metadata.csv into ./data manually, or use the helper script
./scripts/download_and_populate.sh ./data
# OR if CSV already present
python3 scripts/load_movies.py ./data/movies_metadata.csv ./data/movies.db
```

The SQLite loader will create `./data/movies.db` with the contents.

---

## Notes about Kaggle automated download

The compose `populate` service executes `./scripts/download_and_populate.sh /data`. That script uses `curl` to fetch the Kaggle dataset zip from a Kaggle API URL. Many Kaggle dataset downloads require authentication. If the `curl` download fails, the script prints a message with alternatives:

- Use the Kaggle CLI locally:

```bash
# install kaggle CLI and configure ~/.kaggle/kaggle.json
kaggle datasets download -d rounakbanik/the-movies-dataset -p ./data
unzip -o ./data/the-movies-dataset.zip -d ./data
# then run populate mounting ./data
docker compose run --rm -v "$(pwd)/data:/data" populate
```

- Manually download `movies_metadata.csv` from the Kaggle web UI and put it into `./data` and run the populate service with the mounted directory (see previous section).

---

## Environment variables and configuration

`docker-compose.yml` configures DB credentials as:

- POSTGRES_USER: `movies_user`
- POSTGRES_PASSWORD: `movies_pass`
- POSTGRES_DB: `movies_db`

`web` and `populate` services set these as: `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` so the loader can find the DB.

Change them in `docker-compose.yml` if you'd like different credentials.

---

## How population works

- `populate` service runs `scripts/download_and_populate.sh /data`.
- That script will try to download the Kaggle ZIP, unzip it into `/data`, and then run `scripts/load_movies_pg.py /data/movies_metadata.csv` because the environment contains `DATABASE_HOST`.
- `scripts/load_movies_pg.py` connects to Postgres and creates the schema (from `bd_postgres.sql`) and inserts movies, genres and companies, handling JSON-ish fields somewhat robustly.

For local development, `scripts/load_movies.py` can populate a local SQLite DB (`bd.sql` schema).

---

## Inspecting and querying the data

- Using `psql` inside the Postgres container (see examples above).
- Using any Postgres client connect string: `postgresql://movies_user:movies_pass@localhost:5432/movies_db` (adjust host/port if needed).

---

## Development notes

- The Flask app is minimal (root endpoint returns `ads-backend`). You can extend it to add endpoints that query the DB.
- Loaders are intentionally conservative: they parse the CSV row-by-row, try to normalize Python-style JSON dumps (single quotes, True/False/None) into valid JSON for parsing, and insert rows using upserts/ignore semantics to avoid duplicates on re-run.
- The Postgres loader uses psycopg2 which is declared in `requirements.txt`.

---

## Troubleshooting

- If `docker compose run --rm populate` fails with download errors: provide the CSV locally and re-run with `-v "$(pwd)/data:/data"`.
- If the DB is reported as not ready: increase healthcheck retries or check logs: `docker compose logs db`.
- If Python deps are missing locally: `pip install -r requirements.txt`.
- If you see permission errors when mounting host folders into containers, check that Docker has permission to access the project folder and that files are readable.

---

## Next steps (optional)

If you'd like I can:
- Add endpoints to the Flask app to query movies/genres/companies and include tests.
- Change the Postgres loader to use COPY for faster ingestion and add batching.
- Add a lightweight `Makefile` with convenient targets (build, populate, up, down).

Tell me which of these you'd prefer and I'll implement it.

