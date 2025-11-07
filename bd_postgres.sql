-- bd_postgres.sql
-- Schema for Postgres

CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY,
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
    vote_count INTEGER,
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
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    genre_id INTEGER REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE IF NOT EXISTS production_companies (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS movie_companies (
    movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES production_companies(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, company_id)
);

CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title);
CREATE INDEX IF NOT EXISTS idx_genres_name ON genres(name);
CREATE INDEX IF NOT EXISTS idx_companies_name ON production_companies(name);

