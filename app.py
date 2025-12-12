from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import secrets
import os
import re
import logging
from psycopg2.errorcodes import UNIQUE_VIOLATION
import traceback
import json

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


"""TRADITIONAL APPROACH"""

@app.route("/api/auth/register-traditional", methods=['POST'])
def register_traditional():
    data = request.get_json()
    print("Register data received:", data)  # Debugging line

    if not data or 'email' not in data or 'password' not in data or 'username' not in data:
        return jsonify({'error': 'Missing required fields. Email, Password and Username are required'}), 400
    
    email = data['email']
    password = data['password']
    username = data['username']

    # Validações básicas
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400
    
    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    # Vai verificar se já existe um utilizador com o mesmo email ou username
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM users WHERE email = %s OR username = %s", (email, username))
    existing_user = cur.fetchone()

    # Se já existir, retorna erro 409
    if existing_user:
        return jsonify({'error': 'Email or Username already exists'}), 409
    # Se não existir, adiciona o novo utilizador à base de dados
    else:
        password_hash = hash_password(password)
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

@app.route("/api/movies-traditional", methods=['GET'])
def get_movies_traditional():

    data = request.get_json()
    print("Register data received:", data)  # Debugging line

    page = data.get('page', 1)
    sortedBy = data.get('sortedBy', 'popularity')
    offset = (page - 1) * 20

    sorted_options = {
        "title_asc": "title ASC",
        "title_desc": "title DESC",
        "date_new": "release_date DESC",
        "date_old": "release_date ASC",
    }

    sorted_clause = sorted_options.get(sortedBy, "popularity DESC") 

    conn = get_db_connection()
    cur = conn.cursor()

    query = f"""SELECT 
    m.id, 
    m.title, 
    m.release_date, 
    ARRAY_AGG(g.name) AS genres
    FROM movies m
    JOIN movie_genres mg ON m.id = mg.movie_id
    JOIN genres g ON mg.genre_id = g.id
    GROUP BY m.id, m.title, m.release_date
    ORDER BY {sorted_clause}
    LIMIT 20 OFFSET %s"""

    cur.execute(query, (offset,))
    movies = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({'movies': movies}), 200

@app.route('/api//movies/<int:movie_id>/ratings-traditional', methods=['GET'])
def get_movie_ratings_traditional(movie_id):

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, rating, timestamp
        FROM ratings
        WHERE movie_id = %s
    """, (movie_id,))

    ratings = cur.fetchall()
    cur.close()
    conn.close()

    #Calcula a média das avaliações
    if ratings:
        average_rating = sum([r[1] for r in ratings]) / len(ratings)
    else:
        average_rating = None
    
    return jsonify({
        "movie_id": movie_id,
        "average_rating": average_rating,
        "ratings": [{"user_id": r[0], "rating": r[1], "timestamp": r[2].isoformat()} for r in ratings]
    }), 200

"""AI-ASSISTED APPROACH"""

logger = logging.getLogger(__name__)

@app.route("/api/auth/register", methods=['POST'])
def register_ai():
    # 1. Tratamento seguro do JSON
    try:
        data = request.get_json(force=True) # force=True aceita JSON mesmo sem o header correto
    except Exception:
        return jsonify({'error': 'Invalid JSON format'}), 400

    # 2. Validação de campos (Early Return)
    required_fields = ('username', 'email', 'password')
    if not data or not all(k in data and data[k] for k in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    username = data['username'].strip()
    email = data['email'].strip().lower() # Normalizar email
    password = data['password']

    # Validações de formato (Assumindo que estas funções existem)
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    password_hash = hash_password(password)

    try:
        with get_db_connection() as conn:
            # 3. Cursor Factory (se get_db_connection não o fizer por padrão)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role) 
                    VALUES (%s, %s, %s, 'user') 
                    RETURNING id
                    """,
                    (username, email, password_hash)
                )
                
                # Fetch seguro (funciona para tuplo ou dict)
                result = cur.fetchone()
                user_id = result['id'] if isinstance(result, dict) else result[0]
                
                conn.commit()

        return jsonify({'message': 'User created successfully', 'user_id': user_id}), 201

    except psycopg2.IntegrityError as e:
        # Rollback explícito (boa prática, embora o context manager geralmente trate)
        if 'conn' in locals():
            conn.rollback()

        # 4. Verificação robusta via PGCODE
        if e.pgcode == UNIQUE_VIOLATION:
            # Tentar identificar qual campo falhou via constraint name (mais robusto)
            if 'users_username_key' in e.diag.constraint_name:
                return jsonify({'error': 'Username already taken'}), 409
            elif 'users_email_key' in e.diag.constraint_name:
                return jsonify({'error': 'Email already registered'}), 409
            
        return jsonify({'error': 'Account already exists'}), 409

    except Exception:
        # 5. Logging completo com Traceback
        logger.exception(f"Critical error registering user {username}")
        return jsonify({'error': 'An internal error occurred'}), 500

@app.route("/api/movies", methods=['GET'])
def get_movies_ai():
    
    # Parâmetros
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    genre = request.args.get('genre', None)
    sort = request.args.get('sort', "popularity")
    offset = (page - 1) * limit

    # Mapping de Sort
    sort_map = {
        "title_asc": "m.title ASC",
        "title_desc": "m.title DESC",
        "rating_desc": "m.vote_average DESC",
        "rating_asc": "m.vote_average ASC",
        "date_new": "m.release_date DESC",
        "date_old": "m.release_date ASC",
        "popularity": "m.popularity DESC"
    }
    
    order_clause = sort_map.get(sort, "m.popularity DESC")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                
                params = []
                
                # --- PASSO 1: Construir a lógica de filtro (WHERE) ---
                where_sql = ""
                if genre and genre.lower() != "all":
                    where_sql = "WHERE g.name = %s"
                    params.append(genre)

                # --- PASSO 2: Query Principal com CTE ---
                # A CTE 'target_ids' encontra APENAS os IDs e aplica a paginação primeiro (Performance!)
                query = f"""
                    WITH target_ids AS (
                        SELECT m.id
                        FROM movies m
                        JOIN movie_genres mg ON m.id = mg.movie_id
                        JOIN genres g ON mg.genre_id = g.id
                        {where_sql}
                        GROUP BY m.id
                        ORDER BY {order_clause}
                        LIMIT %s OFFSET %s
                    )
                    SELECT 
                        m.id, m.imdb_id, m.title, m.overview, m.release_date,
                        m.popularity, m.vote_average, m.vote_count, m.poster_path,
                        ARRAY_AGG(g_all.name) AS genres
                    FROM target_ids t
                    JOIN movies m ON t.id = m.id
                    JOIN movie_genres mg ON m.id = mg.movie_id
                    JOIN genres g_all ON mg.genre_id = g_all.id
                    GROUP BY m.id, m.title, m.release_date, m.popularity, m.vote_average, m.vote_count, m.poster_path, m.overview, m.imdb_id
                    ORDER BY {order_clause};
                """
                
                # Adiciona limit e offset aos parametros
                params.extend([limit, offset])
                
                cur.execute(query, params)
                movies = cur.fetchall() # Retorna dicts se usares RealDictCursor

                # --- PASSO 3: Contagem Total (Separada) ---
                # Precisamos saber o total para calcular as páginas
                if genre and genre.lower() != "all":
                    count_query = """
                        SELECT COUNT(DISTINCT m.id) as total
                        FROM movies m
                        JOIN movie_genres mg ON m.id = mg.movie_id
                        JOIN genres g ON mg.genre_id = g.id
                        WHERE g.name = %s
                    """
                    cur.execute(count_query, (genre,))
                else:
                    cur.execute("SELECT COUNT(*) as total FROM movies")
                
                total = cur.fetchone()['total']

        # Resposta
        return jsonify({
            'movies': movies,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }), 200

    except Exception as e:
        # Log seguro no servidor, resposta genérica ao cliente
        logger.error(f"Error fetching movies: {e}", exc_info=True)
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/movies/<int:movie_id>/ratings', methods=['GET'])
def get_movie_ratings_ai(movie_id):
    # Paginação interna (para proteger a performance)
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                
                # 1. Calcular estatísticas globais (Média e Contagens)
                # O SQL faz isto instantaneamente para TODAS as reviews do filme
                stats_query = """
                    SELECT 
                        AVG(rating) as avg,
                        SUM(CASE WHEN ROUND(rating) = 1 THEN 1 ELSE 0 END) as c1,
                        SUM(CASE WHEN ROUND(rating) = 2 THEN 1 ELSE 0 END) as c2,
                        SUM(CASE WHEN ROUND(rating) = 3 THEN 1 ELSE 0 END) as c3,
                        SUM(CASE WHEN ROUND(rating) = 4 THEN 1 ELSE 0 END) as c4,
                        SUM(CASE WHEN ROUND(rating) = 5 THEN 1 ELSE 0 END) as c5
                    FROM ratings
                    WHERE movie_id = %s
                """
                cur.execute(stats_query, (movie_id,))
                stats = cur.fetchone()

                # Se a média for None, é porque não há ratings
                if not stats or stats['avg'] is None:
                     return jsonify({
                        "movie_id": movie_id,
                        "average_rating": None,
                        "rating_counts": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                        "ratings": []
                    })

                # 2. Buscar a lista de reviews (Paginada)
                # Buscamos apenas um pedaço pequeno para enviar na lista
                reviews_query = """
                    SELECT user_id, rating, timestamp
                    FROM ratings
                    WHERE movie_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s OFFSET %s
                """
                cur.execute(reviews_query, (movie_id, limit, offset))
                rows = cur.fetchall()

        # Construção da resposta IDENTICA à original
        return jsonify({
            "movie_id": movie_id,
            
            # Média real (calculada pelo SQL)
            "average_rating": stats['avg'], 
            
            # Contagens reais (calculadas pelo SQL)
            # Convertemos para int porque o SUM do SQL pode vir como Decimal/Long
            "rating_counts": {
                1: int(stats['c1'] or 0),
                2: int(stats['c2'] or 0),
                3: int(stats['c3'] or 0),
                4: int(stats['c4'] or 0),
                5: int(stats['c5'] or 0)
            },
            
            # A lista de reviews (agora paginada, mas com o formato de objeto igual)
            "ratings": [
                {
                    "user_id": r["user_id"], 
                    "rating": r["rating"], 
                    "timestamp": r["timestamp"].isoformat()
                } 
                for r in rows
            ]
        })

    except Exception:
        # Log seguro e resposta limpa
        logger.error(f"Error getting ratings for movie {movie_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch ratings"}), 500

"""REST OF THE API ENDPOINTS"""

@app.route("/")
def main():
    return "ads-backend"

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
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route("/api/insert/movie", methods=['POST'])
@require_auth
@require_admin
def insert_movie():
    data = request.get_json()

    # Validação básica
    if not data or 'title' not in data:
        return jsonify({'error': 'Missing required field: title'}), 400

    try:
        # Prepara os dados, garantindo que campos opcionais sejam None se não existirem
        # Também trata listas (como genres) para strings JSON se necessário
        
        raw_genres = data.get('raw_genres', [])
        if isinstance(raw_genres, (list, dict)):
            raw_genres = json.dumps(raw_genres)

        raw_companies = data.get('raw_production_companies', [])
        if isinstance(raw_companies, (list, dict)):
            raw_companies = json.dumps(raw_companies)

        # Tratamento especial para data vazia
        release_date = data.get('release_date')
        if release_date == "":
            release_date = None

        movie_params = {
            'imdb_id': data.get('imdb_id'),
            'title': data['title'], # Obrigatório
            'original_title': data.get('original_title', data['title']),
            'overview': data.get('overview'),
            'release_date': release_date,
            'adult': bool(data.get('adult', False)),
            'budget': int(data.get('budget', 0)),
            'revenue': int(data.get('revenue', 0)),
            'runtime': float(data.get('runtime', 0.0)) if data.get('runtime') else None,
            'popularity': float(data.get('popularity', 0.0)),
            'vote_average': float(data.get('vote_average', 0.0)),
            'vote_count': int(data.get('vote_count', 0)),
            'original_language': data.get('original_language', 'en'),
            'status': data.get('status', 'Released'),
            'tagline': data.get('tagline'),
            'homepage': data.get('homepage'),
            'poster_path': data.get('poster_path'),
            'raw_genres': raw_genres,
            'raw_production_companies': raw_companies
        }

        conn = get_db_connection()
        cur = conn.cursor()

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
            movie_params
        )

        movie_id = cur.fetchone()['id']
        conn.commit()
        
        # Opcional: Se quiseres inserir na tabela de junção movie_genres logo aqui, 
        # terias que processar o array de IDs de géneros.

        cur.close()
        conn.close()

        return jsonify({
            'message': 'Movie inserted successfully',
            'movie_id': movie_id
        }), 201

    except Exception as e:
        # Se usares traceback, não esqueças de importar 'traceback' no topo
        import traceback
        print(traceback.format_exc()) # Log no console do servidor
        return jsonify({'error': str(e)}), 500

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
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    genre = request.args.get('genre', None)
    sort = request.args.get('sort', "popularity")
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
        with get_db_connection() as conn:
            with conn.cursor() as cur: # Idealmente usa cursor_factory=RealDictCursor

                # --- MUDANÇA AQUI ---
                # Adicionei uma subquery (linha 4 a 8 do SQL abaixo)
                # Ela vai buscar todos os géneros associados a este ID de filme
                # e devolve-os como uma lista (ARRAY)
                base_query = """
                    SELECT 
                        m.id, 
                        m.imdb_id, 
                        m.title, 
                        m.overview, 
                        m.release_date,
                        m.popularity, 
                        m.vote_average, 
                        m.vote_count, 
                        m.poster_path,
                        (
                            SELECT ARRAY_AGG(g_sub.name)
                            FROM movie_genres mg_sub
                            JOIN genres g_sub ON mg_sub.genre_id = g_sub.id
                            WHERE mg_sub.movie_id = m.id
                        ) as debug_genres
                    FROM movies m
                """

                # Pesquisa apenas no Título
                where_clauses = ["m.title ILIKE %s"]
                params = [f"%{query}%"]

                # Lógica de Filtro (JOIN apenas se necessário para filtrar)
                if genre and genre.lower() != "all":
                    base_query += """
                        JOIN movie_genres mg ON m.id = mg.movie_id
                        JOIN genres g ON mg.genre_id = g.id
                    """
                    where_clauses.append("g.name = %s")
                    params.append(genre)

                if where_clauses:
                    base_query += " WHERE " + " AND ".join(where_clauses)

                final_query = f"""
                    {base_query}
                    ORDER BY {order_clause}
                    LIMIT %s OFFSET %s
                """
                
                params.extend([limit, offset])

                cur.execute(final_query, params)
                movies = cur.fetchall() 

                # --- Count Query (Mantém-se igual) ---
                count_params = [f"%{query}%"]
                count_query = "SELECT COUNT(*) as count FROM movies m"
                
                if genre and genre.lower() != "all":
                    count_query += """
                        JOIN movie_genres mg ON m.id = mg.movie_id
                        JOIN genres g ON mg.genre_id = g.id
                        WHERE m.title ILIKE %s AND g.name = %s
                    """
                    count_params.append(genre)
                else:
                    count_query += " WHERE m.title ILIKE %s"

                cur.execute(count_query, count_params)
                total_result = cur.fetchone()
                
                if isinstance(total_result, dict):
                    total = total_result['count']
                else:
                    total = total_result[0]

        return jsonify({
            'movies': movies,
            'page': page,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }), 200

    except Exception as e:
        print(f"SQL Error: {str(e)}")
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
    user_id = request.user_id

    try:
        # ✅ FIX: Initialize the empty dictionary first
        response = {} 

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
                    WHERE r.user_id = %s
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
            
            # Now this line works because 'response' exists
            response['user_id'] = user_id

        cur.close()
        conn.close()

        # Add recommended movies to response if the list is not empty
        if recommended_movies:
            response['recommended'] = recommended_movies
        elif user_id:
             # Add a message if user is authenticated but no recommendations are found
             response['message'] = 'No personalized recommendations found based on your high ratings (>= 7).'
        else:
             # Add a message if the user is not authenticated
             response['message'] = 'User not authenticated. No personalized recommendations available.'

        return jsonify(response), 200

    except Exception as e:
        # It is good practice to print the error to your console for debugging
        print(f"Error: {e}") 
        return jsonify({'error': str(e)}), 500
    
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
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route("/api/admin/movies/<int:movie_id>", methods=['DELETE'])
@require_auth
@require_admin
def delete_movie(movie_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("DELETE FROM movie_genres WHERE movie_id = %s", (movie_id,))

        cur.execute("DELETE FROM ratings WHERE movie_id = %s", (movie_id,))

        cur.execute("DELETE FROM movies WHERE id = %s RETURNING id", (movie_id,))
        deleted = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()

        if not deleted:
            return jsonify({'error': 'Movie not found'}), 404

        return jsonify({'message': 'Movie deleted successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# Ensure the flask app runs only when this script is executed directly
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
    