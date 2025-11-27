from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import secrets
import os
import re

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DATABASE_HOST', 'db'),
    'database': os.getenv('DATABASE_NAME', 'movies_db'),
    'user': os.getenv('DATABASE_USER', 'postgres'),
    'password': os.getenv('DATABASE_PASSWORD', 'postgres'),
    'port': os.getenv('DATABASE_PORT', 5432)
}

# Simple token storage (in production, use Redis or database)
active_tokens = {}


def get_db_connection():
    """Create and return a database connection"""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    else:
        # fallback local
        DB_CONFIG = {
            'host': os.getenv('DATABASE_HOST', 'localhost'),
            'database': os.getenv('DATABASE_NAME', 'movies_db'),
            'user': os.getenv('DATABASE_USER', 'postgres'),
            'password': os.getenv('DATABASE_PASSWORD', 'postgres'),
            'port': os.getenv('DATABASE_PORT', 5432)
        }
        return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def hash_password(password):
    """Hash password with SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token():
    """Generate a secure random token"""
    return secrets.token_urlsafe(32)


def validate_email(email):
    """Validate email format using regex"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Validate password meets security requirements"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, None


def require_auth(f):
    """Decorator to check authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'error': 'No authorization token provided'}), 401

        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]

        # Check if token is valid
        if token not in active_tokens:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # Add user_id to request context
        request.user_id = active_tokens[token]
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def main():
    return "ads-backend"


@app.route("/api/auth/register", methods=['POST'])
def register():
    """User registration endpoint"""
    data = request.get_json()

    # Validate input
    if not data or not all(k in data for k in ('username', 'email', 'password')):
        return jsonify({'error': 'Missing required fields'}), 400

    username = data['username']
    email = data['email']
    password = data['password']

    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    is_valid, error_message = validate_password(password)
    if not is_valid:
        return jsonify({'error': error_message}), 400

    # Hash password
    password_hash = hash_password(password)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Insert new user (role defaults to 'user' in database)
        cur.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'user') RETURNING id",
            (username, email, password_hash)
        )
        user_id = cur.fetchone()['id']

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'message': 'User registered successfully',
            'user_id': user_id
        }), 201

    except psycopg2.IntegrityError as e:
        error_msg = str(e)
        if 'users_username_key' in error_msg or 'username' in error_msg.lower():
            return jsonify({'error': 'Username already exists'}), 409
        elif 'users_email_key' in error_msg or 'email' in error_msg.lower():
            return jsonify({'error': 'Email already exists'}), 409
        else:
            return jsonify({'error': 'Username or email already exists'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/auth/login", methods=['POST'])
def login():
    """User authentication endpoint"""
    data = request.get_json()

    # Validate input
    if not data or not all(k in data for k in ('username', 'password')):
        return jsonify({'error': 'Missing username or password'}), 400

    username = data['username']
    password = data['password']
    password_hash = hash_password(password)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check credentials
        cur.execute(
            "SELECT id, username, email, role FROM users WHERE username = %s AND password_hash = %s",
            (username, password_hash)
        )
        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401

        # Generate token
        token = generate_token()
        active_tokens[token] = user['id']

        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role']
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/auth/logout", methods=['POST'])
@require_auth
def logout():
    """User logout endpoint"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if token in active_tokens:
        del active_tokens[token]
        return jsonify({'message': 'Logout successful'}), 200
    else:
        return jsonify({'message': 'Logout successful'}), 200


@app.route("/api/movies", methods=['GET'])
def get_movies():
    """Browse catalog with pagination, genre filter, and sorting"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    genre = request.args.get('genre', None)        # e.g. "Action"
    sort = request.args.get('sort', "popularity") # default sort
    offset = (page - 1) * limit

    # Allowed sort mappings
    sort_map = {
        "title_asc": "title ASC",
        "title_desc": "title DESC",
        "rating_desc": "vote_average DESC",
        "rating_asc": "vote_average ASC",
        "date_new": "release_date DESC",
        "date_old": "release_date ASC",
        "popularity": "popularity DESC"
    }

    order_clause = sort_map.get(sort, "popularity DESC")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Base query
        base_query = """
            SELECT m.id, m.imdb_id, m.title, m.overview, m.release_date,
                   m.popularity, m.vote_average, m.vote_count, m.poster_path
            FROM movies m
        """

        where_clauses = []
        params = []

        # Handle genre filtering if provided
        if genre and genre.lower() != "all":
            base_query += """
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
            """
            where_clauses.append("g.name = %s")
            params.append(genre)

        # Build WHERE clause
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        # Final SQL with sorting + pagination
        final_query = f"""
            {base_query}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        cur.execute(final_query, params)
        movies = cur.fetchall()

        # Count for pagination
        count_query = "SELECT COUNT(*) FROM movies"
        if genre and genre.lower() != "all":
            count_query = """
                SELECT COUNT(*)
                FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE g.name = %s
            """
            cur.execute(count_query, (genre,))
        else:
            cur.execute(count_query)

        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        return jsonify({
            'movies': movies,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/movies", methods=['POST'])
@require_auth
def insert_movie():
    """Insert new movie (authenticated) with auto-generated ID"""
    data = request.get_json()

    if not data or 'title' not in data:
        return jsonify({'error': 'Missing required field: title'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Insert movie without specifying ID (auto-generated)
        cur.execute(
            """
            INSERT INTO movies (
                imdb_id, title, original_title, overview, release_date,
                adult, budget, revenue, runtime, popularity, vote_average,
                vote_count, original_language, status, tagline, homepage,
                poster_path, raw_genres, raw_production_companies
            ) VALUES (
                %(imdb_id)s, %(title)s, %(original_title)s, %(overview)s, %(release_date)s,
                %(adult)s, %(budget)s, %(revenue)s, %(runtime)s, %(popularity)s, %(vote_average)s,
                %(vote_count)s, %(original_language)s, %(status)s, %(tagline)s, %(homepage)s,
                %(poster_path)s, %(raw_genres)s, %(raw_production_companies)s
            ) RETURNING id;
            """,
            data
        )

        movie_id = cur.fetchone()['id']

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'message': 'Movie inserted successfully',
            'movie_id': movie_id
        }), 201

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route("/api/movies/search", methods=['GET'])
def search_movies():
    """Search functionality with genre filter and sorting"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    genre = request.args.get('genre', None)
    sort = request.args.get('sort', "popularity")
    offset = (page - 1) * limit

    # Allowed sort mappings
    sort_map = {
        "title_asc": "title ASC",
        "title_desc": "title DESC",
        "rating_desc": "vote_average DESC",
        "rating_asc": "vote_average ASC",
        "date_new": "release_date DESC",
        "date_old": "release_date ASC",
        "popularity": "popularity DESC"
    }
    order_clause = sort_map.get(sort, "popularity DESC")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Base query
        base_query = """
            SELECT m.id, m.imdb_id, m.title, m.overview, m.release_date,
                   m.popularity, m.vote_average, m.vote_count, m.poster_path
            FROM movies m
        """

        where_clauses = ["(m.title ILIKE %s OR m.overview ILIKE %s)"]
        params = [f"%{query}%", f"%{query}%"]

        # Handle genre filtering if provided
        if genre and genre.lower() != "all":
            base_query += """
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
            """
            where_clauses.append("g.name = %s")
            params.append(genre)

        # Build WHERE clause
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        # Final SQL with sorting + pagination
        final_query = f"""
            {base_query}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        cur.execute(final_query, params)
        movies = cur.fetchall()

        # Count for pagination
        count_query = "SELECT COUNT(*) FROM movies m"
        count_params = []

        if genre and genre.lower() != "all":
            count_query += """
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE (m.title ILIKE %s OR m.overview ILIKE %s) AND g.name = %s
            """
            count_params = [f"%{query}%", f"%{query}%", genre]
        else:
            count_query += " WHERE m.title ILIKE %s OR m.overview ILIKE %s"
            count_params = [f"%{query}%", f"%{query}%"]

        cur.execute(count_query, count_params)
        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        return jsonify({
            'movies': movies,
            'query': query,
            'genre': genre,
            'sort': sort,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/movie/<int:movie_id>/rating", methods=['POST'])
@require_auth
def submit_rating(movie_id):
    """Submit rating for a movie (authenticated)"""
    data = request.get_json()

    if not data or 'rating' not in data:
        return jsonify({'error': 'Missing rating value'}), 400

    rating = data['rating']

    if not (0 <= rating <= 10):
        return jsonify({'error': 'Rating must be between 0 and 10'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Insert or update rating
        cur.execute(
            """
            INSERT INTO ratings (user_id, movie_id, rating, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (user_id, movie_id) 
            DO UPDATE SET rating = %s, updated_at = NOW()
            RETURNING id
            """,
            (request.user_id, movie_id, rating, rating)
        )
        rating_id = cur.fetchone()['id']

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'message': 'Rating submitted successfully',
            'rating_id': rating_id,
            'movie_id': movie_id,
            'rating': rating
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/home", methods=['GET'])
def get_home():
    """Get main catalog with recommendation system"""
    user_id = None

    # Check if user is authenticated
    token = request.headers.get('Authorization')
    if token:
        if token.startswith('Bearer '):
            token = token[7:]
        user_id = active_tokens.get(token)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get popular movies
        cur.execute(
            """
            SELECT id, imdb_id, title, overview, release_date,
                   popularity, vote_average, vote_count, poster_path
            FROM movies
            ORDER BY popularity DESC
            LIMIT 20
            """
        )
        popular_movies = cur.fetchall()

        # Get recent movies
        cur.execute(
            """
            SELECT id, imdb_id, title, overview, release_date,
                   popularity, vote_average, vote_count, poster_path
            FROM movies
            WHERE release_date IS NOT NULL
            ORDER BY release_date DESC
            LIMIT 20
            """
        )
        recent_movies = cur.fetchall()

        recommended_movies = []

        # If user is authenticated, get personalized recommendations
        if user_id:
            # Simple recommendation: movies from genres user has rated highly
            cur.execute(
                """
                SELECT DISTINCT m.id, m.imdb_id, m.title, m.overview, m.release_date,
                       m.popularity, m.vote_average, m.vote_count, m.poster_path
                FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                WHERE mg.genre_id IN (
                    SELECT DISTINCT mg2.genre_id
                    FROM ratings r
                    JOIN movie_genres mg2 ON r.movie_id = mg2.movie_id
                    WHERE r.user_id = %s AND r.rating >= 7
                )
                AND m.id NOT IN (
                    SELECT movie_id FROM ratings WHERE user_id = %s
                )
                ORDER BY m.popularity DESC
                LIMIT 20
                """,
                (user_id, user_id)
            )
            recommended_movies = cur.fetchall()

        cur.close()
        conn.close()

        response = {
            'popular': popular_movies,
            'recent': recent_movies
        }

        if recommended_movies:
            response['recommended'] = recommended_movies

        return jsonify(response), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api//movies/<int:movie_id>/ratings', methods=['GET'])
def get_movie_ratings(movie_id):
    """List all ratings for a movie, with average and per-rating counts."""
    import traceback
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT user_id, rating, timestamp
            FROM ratings
            WHERE movie_id = %s
            ORDER BY timestamp DESC
        """, (movie_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return jsonify({
                "movie_id": movie_id,
                "average_rating": None,
                "rating_counts": {},
                "ratings": []
            })

        # Compute average rating
        ratings_list = [row["rating"] for row in rows]
        avg_rating = sum(ratings_list) / len(ratings_list)

        # Count number of ratings per rounded rating (1-5)
        rounded_ratings = [round(r) for r in ratings_list]
        rating_counts = {i: rounded_ratings.count(i) for i in range(1, 6)}

        # Prepare rating details using dict access
        ratings = [
            {"user_id": row["user_id"], "rating": row["rating"], "timestamp": row["timestamp"].isoformat()}
            for row in rows
        ]

        return jsonify({
            "movie_id": movie_id,
            "average_rating": avg_rating,
            "rating_counts": rating_counts,
            "ratings": ratings
        })

    except Exception:
        import traceback
        return jsonify({"error": "Failed to fetch ratings", "trace": traceback.format_exc()}), 500

@app.route('/api//movies/<int:movie_id>/ratings', methods=['POST'])
@require_auth
def add_movie_rating(movie_id):
    """Add or update a rating for a movie"""
    data = request.json
    if not data or  'rating' not in data:
        return jsonify({"error": "user_id and rating are required"}), 400

    # get user id from token in headers
    user_id = request.user_id
    rating = data['rating']

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ratings(user_id, movie_id, rating, timestamp)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id, movie_id) DO UPDATE
            SET rating = EXCLUDED.rating, timestamp = now()
        """, (user_id, movie_id, rating))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Rating added/updated successfully"}), 201
    except Exception as e:
        import traceback
        return jsonify({"error": "Failed to fetch ratings", "trace": traceback.format_exc()}), 500


# Ensure the flask app runs only when this script is executed directly
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
    