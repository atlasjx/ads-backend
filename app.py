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
        user_info = active_tokens[token]
        request.user_id = user_info['id']
        request.user_role = user_info['role']

        return f(*args, **kwargs)

    return decorated_function

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Como este decorator vem DEPOIS do require_auth, 
        # o request.user_role já existe.
        
        role = getattr(request, 'user_role', None)
        
        if role != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403

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
        active_tokens[token] = {
            'id': user['id'],
            'role': user['role']
        }


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
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    genre = request.args.get('genre', None)        # e.g. "Action"
    sort = request.args.get('sort', "popularity") # default sort
    offset = (page - 1) * limit

    # Allowed sort mappings (MANTIDO)
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

        # 1. Base Query CORRIGIDA com ARRAY_AGG e GROUP BY
        base_query = """
            SELECT 
                m.id, m.imdb_id, m.title, m.overview, m.release_date,
                m.popularity, m.vote_average, m.vote_count, m.poster_path,
                -- Agrega todos os nomes de gênero em um array para cada filme
                ARRAY_AGG(g.name) AS genres 
            FROM movies m
            
            JOIN movie_genres mg ON m.id = mg.movie_id
            JOIN genres g ON mg.genre_id = g.id
        """

        where_clauses = []
        params = []
        
        # 2. Lógica de Filtro por Gênero (MANTIDA)
        # Handle genre filtering if provided
        if genre and genre.lower() != "all":
            # Para filtrar por um gênero, precisamos garantir que o filme tenha aquele gênero.
            # Adicionamos a condição WHERE, mas não precisamos repetir os JOINs.
            where_clauses.append("g.name = %s")
            params.append(genre)

        # Build WHERE clause
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
        
        # 3. Adiciona o GROUP BY para que ARRAY_AGG funcione
        final_query = f"""
            {base_query}
            GROUP BY m.id
            ORDER BY {order_clause},  m.id DESC
            LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        cur.execute(final_query, params)
        movies = cur.fetchall()

        # 4. Count Query (REQUER MUDANÇA se o filtro de gênero estiver ativo)
        # Se o filtro de gênero estiver ativo, a contagem deve contar filmes (m.id) distintos
        if genre and genre.lower() != "all":
             count_query = """
                SELECT COUNT(DISTINCT m.id)
                FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE g.name = %s
            """
             cur.execute(count_query, (genre,))
        else:
            # Se não há filtro de gênero, a contagem é simples (MANTIDO)
            count_query = "SELECT COUNT(*) FROM movies"
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
        # Import traceback para debug mais detalhado (opcional)
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route("/api/my-movies", methods=['GET'])
@require_auth
def get_myMovies():

    user_id = request.user_id #Obtém o ID do usuário autenticado para filtrar os filmes avaliados por ele 
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    genre = request.args.get('genre', None)
    sort = request.args.get('sort', "date_new")
    offset = (page - 1) * limit

   
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
        base_query = """
            SELECT 
                m.id, m.imdb_id, m.title, m.overview, m.release_date,
                m.popularity, m.vote_average, m.vote_count, m.poster_path,
                r.rating as user_rating, r.updated_at as rated_at,
                -- Aggregate genres into an array
                ARRAY_AGG(DISTINCT g.name) AS genres 
            FROM movies m
            JOIN ratings r ON m.id = r.movie_id
            JOIN movie_genres mg ON m.id = mg.movie_id
            JOIN genres g ON mg.genre_id = g.id
            WHERE r.user_id = %s
        """

        params = [user_id]
        
       
        if genre and genre.lower() != "all":
            base_query += " AND g.name = %s"
            params.append(genre)

        final_query = f"""
            {base_query}
            GROUP BY m.id, r.id, r.rating, r.updated_at
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        cur.execute(final_query, params)
        movies = cur.fetchall()

        if genre and genre.lower() != "all":
            count_query = """
                SELECT COUNT(DISTINCT m.id)
                FROM movies m
                JOIN ratings r ON m.id = r.movie_id
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE r.user_id = %s AND g.name = %s
            """
            cur.execute(count_query, (user_id, genre))
        else:
            count_query = """
                SELECT COUNT(DISTINCT m.id)
                FROM movies m
                JOIN ratings r ON m.id = r.movie_id
                WHERE r.user_id = %s
            """
            cur.execute(count_query, (user_id,))

        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        return jsonify({
            'movies': movies,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit,
            'sort': sort,
            'genre': genre
        }), 200

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route("/api/movies", methods=['POST'])
@require_auth
def insert_movie():
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

@app.route("/api/admin/movies/<int:movie_id>", methods=['PUT'])
@require_auth   # Garante que está logado
@require_admin  # Garante que é admin
def update_movie(movie_id):
    """
    Atualiza os dados de um filme existente.
    Aceita atualizações parciais (ex: enviar apenas o título).
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # 1. Lista de segurança (Allowlist)
    # Define estritamente quais colunas podem ser alteradas para evitar SQL Injection 
    # ou alteração de campos proibidos (como o ID).
    allowed_fields = [
        'imdb_id', 'title', 'original_title', 'overview', 'release_date',
        'adult', 'budget', 'revenue', 'runtime', 'popularity', 
        'vote_average', 'vote_count', 'original_language', 'status', 
        'tagline', 'homepage', 'poster_path'
    ]
    
    updates = []
    params = []

    # 2. Constrói a query dinamicamente baseada no JSON recebido
    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = %s")
            params.append(data[field])

    # Se o utilizador enviou campos, mas nenhum deles está na lista permitida
    if not updates:
        return jsonify({'error': 'No valid fields provided to update'}), 400

    # Adiciona o ID do filme ao final dos parâmetros para a cláusula WHERE
    params.append(movie_id)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 3. Monta e executa o SQL
        # Ex: "UPDATE movies SET title = %s, overview = %s WHERE id = %s"
        sql_query = f"UPDATE movies SET {', '.join(updates)} WHERE id = %s RETURNING id"
        
        cur.execute(sql_query, params)
        movie = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()

        if not movie:
            return jsonify({'error': 'Movie not found'}), 404

        return jsonify({
            'message': 'Movie updated successfully',
            'movie_id': movie_id,
            'updated_fields': [k for k in data.keys() if k in allowed_fields]
        }), 200

    except Exception as e:
        # Dica: Em produção, use logging em vez de print
        print(f"Update error: {e}")
        return jsonify({'error': 'Failed to update movie', 'details': str(e)}), 500
    
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
           ORDER BY m.id DESC
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
            INSERT INTO ratings (user_id, movie_id, rating, timestamp, updated_at)
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

@app.route("/api/movie/<int:movie_id>/rating", methods=['DELETE'])
@require_auth
def delete_rating(movie_id):
    """
    Remove a avaliação do utilizador autenticado para um filme específico.
    """
    user_id = request.user_id # Obtido do token pelo decorator @require_auth

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Executa a remoção garantindo que o rating pertence ao user logado
        cur.execute(
            "DELETE FROM ratings WHERE user_id = %s AND movie_id = %s",
            (user_id, movie_id)
        )
        
        # cur.rowcount diz quantas linhas foram afetadas
        rows_deleted = cur.rowcount

        conn.commit()
        cur.close()
        conn.close()

        if rows_deleted == 0:
            return jsonify({'message': 'Rating not found or already deleted'}), 404

        return jsonify({'message': 'Rating deleted successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route("/api/home", methods=['GET'])
def get_home():
    """Get main catalog with recommendation system"""
    '''user_id = None

    # Check if user is authenticated
    token = request.headers.get('Authorization')
    if token:
        if token.startswith('Bearer '):
            token = token[7:]
        user_id = active_tokens.get(token)'''

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
        '''if user_id:
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
               ORDER BY m.popularity DESC, m.id DESC
                LIMIT 20
                """,
                (user_id, user_id)
            )
            recommended_movies = cur.fetchall()'''

        cur.close()
        conn.close()

        response = {
            'popular': popular_movies,
            'recent': recent_movies
        }

        '''if recommended_movies:
            response['recommended'] = recommended_movies'''

        return jsonify(response), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/home/recommendations", methods=['GET'])
@require_auth
def get_home_recommendations():
    """Get main catalog with recommendation system"""
    user_id = None

    # Check if user is authenticated (authentication logic remains the same)
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token = token[7:]
    
    # NOTE: The @require_auth decorator already handles authentication and sets request.user_id. 
    # The token extraction logic below is somewhat redundant if @require_auth is active 
    # but is kept for robustness in case @require_auth is temporarily commented out.
    user_id = active_tokens.get(token) if token else request.user_id
    
    # --- FIX: Initialize response dictionary ---
    response = {} 
    
    # --- END FIX ---

    try:
        conn = get_db_connection()
        cur = conn.cursor()

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
            
            # --- IMPROVEMENT: Set user_id from decorator (if not set above)
            # This ensures the decorator's result is prioritized.
            response['user_id'] = user_id
            # --- END IMPROVEMENT

        cur.close()
        conn.close()

        # Add recommended movies to response if the list is not empty
        if recommended_movies:
            response['recommended'] = recommended_movies
        elif user_id:
             # Add a message if user is authenticated but no recommendations are found
             response['message'] = 'No personalized recommendations found based on your high ratings (>= 7).'
        else:
             # Add a message if the user is not authenticated or a generic fallback
             response['message'] = 'User not authenticated. No personalized recommendations available.'


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


@app.route('/api/profile', methods=['GET'])
@require_auth
def get_profile():
    """
    Get authenticated user's profile data (details and recent ratings).
    Requires a valid Authorization Bearer token.
    """
    # user_id is set by the @require_auth decorator
    user_id = request.user_id 
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Fetch User Details
        cur.execute(
            "SELECT id, username, email, role, created_at, profile_picture_path FROM users WHERE id = %s",
            (user_id,)
        )
        user_data = cur.fetchone()

        if not user_data:
            cur.close()
            conn.close()
            # This should ideally not happen if authentication passed
            return jsonify({'error': 'User not found'}), 404

        # 2. Fetch User's Recent Ratings
        cur.execute(
            """
            SELECT r.rating, r.updated_at, m.title, m.poster_path, m.id AS movie_id
            FROM ratings r
            JOIN movies m ON r.movie_id = m.id
            WHERE r.user_id = %s
            ORDER BY r.updated_at DESC
            LIMIT 10
            """,
            (user_id,)
        )
        recent_ratings = cur.fetchall()

        cur.close()
        conn.close()

        # Format the response
        response = {
            'user': {
                'id': user_data['id'],
                'username': user_data['username'],
                'email': user_data['email'],
                'role': user_data['role'],
                'created_at': user_data['created_at'].isoformat(),
                'profile_picture_path': user_data['profile_picture_path']
            },
            'recent_ratings': [
                {
                    'rating': r['rating'],
                    'rated_at': r['updated_at'].isoformat(),
                    'movie_title': r['title'],
                    'movie_id': r['movie_id'],
                    'poster_path': r['poster_path']
                } for r in recent_ratings
            ]
        }
        
        return jsonify(response), 200

    except Exception as e:
        import traceback
        return jsonify({'error': 'Failed to fetch profile data', 'details': str(e), 'trace': traceback.format_exc()}), 500
    
@app.route('/api/profile', methods=['PUT'])
@require_auth
def update_profile():
    """
    Update authenticated user's profile data (username, email) and
    allows editing of recent ratings provided in the request body.
    Requires a valid Authorization Bearer token.
    """
    user_id = request.user_id 
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Missing data in request body'}), 400

    username = data.get('username')
    email = data.get('email')
    profile_picture_path = data.get('profile_picture_path')
    ratings_to_update = data.get('recent_ratings', []) # Lista de {movie_id, rating}
    
    update_clauses = []
    params = []
    updated_ratings_count = 0

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Atualizar Detalhes do Usuário (Username e Email)
        if username or email or profile_picture_path:
            
            # Validação
            if username and username.strip() == "":
                return jsonify({'error': 'Username cannot be empty'}), 400
            if email and not validate_email(email):
                return jsonify({'error': 'Invalid email format'}), 400
            
            # Construção da Query
            if username:
                update_clauses.append("username = %s")
                params.append(username)
            if email:
                update_clauses.append("email = %s")
                params.append(email)
            if profile_picture_path:
                update_clauses.append("profile_picture_path = %s")
                params.append(profile_picture_path)
            

            update_clauses.append("updated_at = NOW()")

            sql_query = f"UPDATE users SET {', '.join(update_clauses)} WHERE id = %s RETURNING id, username, email, role, profile_picture_path"
            params.append(user_id)

            cur.execute(sql_query, params)
            updated_user = cur.fetchone()
        else:
            # Se não houver campos de usuário para atualizar, buscamos os dados atuais para o retorno
            cur.execute("SELECT id, username, email, role, profile_picture_path FROM users WHERE id = %s", (user_id,))
            updated_user = cur.fetchone()
        
        if not updated_user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        # 2. Atualizar Avaliações (Ratings)
        for rating_data in ratings_to_update:
            movie_id = rating_data.get('movie_id')
            rating = rating_data.get('rating')

            if movie_id is not None and rating is not None and (0 <= rating <= 10):
                # Usamos a lógica ON CONFLICT DO UPDATE (upsert) para garantir que a avaliação seja inserida/atualizada
                cur.execute(
                    """
                    INSERT INTO ratings (user_id, movie_id, rating, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (user_id, movie_id) 
                    DO UPDATE SET rating = %s, updated_at = NOW()
                    """,
                    (user_id, movie_id, rating, rating)
                )
                updated_ratings_count += 1
            elif rating is not None and not (0 <= rating <= 10):
                # Se a avaliação estiver fora do intervalo permitido, retornamos um erro específico
                 return jsonify({'error': f'Invalid rating value ({rating}) for movie ID {movie_id}. Rating must be between 0 and 10'}), 400
        
        # 3. Commit e Retorno
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'message': 'Profile and ratings updated successfully',
            'user': updated_user,
            'ratings_updated_count': updated_ratings_count
        }), 200

    except psycopg2.IntegrityError as e:
        conn.rollback()
        # Tratamento de erros de unicidade (username ou email já existem)
        error_msg = str(e)
        if 'users_username_key' in error_msg or 'username' in error_msg.lower():
            return jsonify({'error': 'Username already taken'}), 409
        elif 'users_email_key' in error_msg or 'email' in error_msg.lower():
            return jsonify({'error': 'Email already taken'}), 409
        else:
            return jsonify({'error': 'Integrity constraint violation'}), 409
            
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500





# Ensure the flask app runs only when this script is executed directly
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
    