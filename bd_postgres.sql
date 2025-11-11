-- ============================================
-- MOVIE TABLES (without foreign keys)
-- ============================================
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
    movie_id INTEGER,
    genre_id INTEGER,
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE IF NOT EXISTS production_companies (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS movie_companies (
    movie_id INTEGER,
    company_id INTEGER,
    PRIMARY KEY (movie_id, company_id)
);

-- ============================================
-- AUTHENTICATION AND RATINGS TABLES
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    movie_id INTEGER,
    rating REAL NOT NULL CHECK (rating >= 0 AND rating <= 10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, movie_id)
);

-- ============================================
-- INDEXES
-- ============================================

-- Movie indexes
CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title);
CREATE INDEX IF NOT EXISTS idx_movies_release_date ON movies(release_date);
CREATE INDEX IF NOT EXISTS idx_movies_popularity ON movies(popularity);

-- Genres and companies
CREATE INDEX IF NOT EXISTS idx_genres_name ON genres(name);
CREATE INDEX IF NOT EXISTS idx_companies_name ON production_companies(name);

-- Users and ratings
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_ratings_user_id ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_movie_id ON ratings(movie_id);