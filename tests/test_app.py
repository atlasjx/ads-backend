import pytest
import requests
import json
import time
import os
import logging

# -----------------------------------
# Configuração de Logs
# -----------------------------------
# Configura o logger para mostrar hora, nivel e mensagem
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("API_TESTS")

BASE_URL = os.environ.get("API_HOST", "http://localhost")
API = BASE_URL + "/api"


# -----------------------------------
# Helper de Log (Melhorado)
# -----------------------------------

def log_roundtrip(response, label="API CALL"):
    """
    Loga os detalhes da requisição e da resposta de forma estruturada.
    """
    resp_data = {}  # Inicializa vazio para evitar UnboundLocalError

    try:
        # Tenta formatar o JSON bonitinho
        resp_data = response.json()
        formatted_body = json.dumps(resp_data, indent=4)
    except json.JSONDecodeError:
        # Se não for JSON (ex: erro 404 HTML ou 500 texto), mostra texto puro
        formatted_body = response.text
        # Define resp_data com o texto para não quebrar o return
        resp_data = {"error": "Response was not JSON", "text": response.text}

    separator = "-" * 60
    
    logger.info(f"\n{separator}")
    logger.info(f"🧪 TEST STEP: {label}")
    logger.info(f"📡 REQUEST:  [{response.request.method}] {response.request.url}")
    
    if response.request.body:
        try:
            body_str = response.request.body.decode('utf-8') if isinstance(response.request.body, bytes) else str(response.request.body)
            logger.info(f"📤 PAYLOAD:  {body_str[:200]}..." if len(body_str) > 200 else f"📤 PAYLOAD:  {body_str}")
        except:
            pass

    status_emoji = "✅" if response.status_code < 400 else "❌"
    logger.info(f"📥 RESPONSE: {status_emoji} Status {response.status_code} (Time: {response.elapsed.total_seconds()}s)")
    logger.info(f"📄 BODY:\n{formatted_body}")
    logger.info(separator)

    return resp_data

# -----------------------------------
# Fixtures
# -----------------------------------

@pytest.fixture(scope="session")
def test_user():
    """Gera usuário único."""
    ts = int(time.time())
    return {
        "username": f"pytest_user_{ts}",
        "email": f"pytest_email_{ts}@test.com",
        "password": "Testpassword@123"
    }


@pytest.fixture(scope="session")
def token(test_user):
    """Registra e loga o usuário, retornando o token."""
    
    logger.info("=== PREPARING AUTH FIXTURE ===")

    # Register
    requests.post(f"{API}/auth/register", json=test_user)

    # Login
    res = requests.post(f"{API}/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })

    # Usamos nosso novo logger
    data = log_roundtrip(res, "LOGIN (Fixture)")

    assert "token" in data, "Falha no Login da Fixture"
    return data["token"]


# -----------------------------------
# Testes
# -----------------------------------

def test_register_user(test_user):
    """Test user registration."""
    # A rota na app.py é /api/auth/register (função register_ai)
    res = requests.post(f"{API}/auth/register", json=test_user)
    
    log_roundtrip(res, "REGISTER USER")

    # A app retorna 201 (Sucesso) ou 409 (Conflito/Já existe)
    assert res.status_code in (201, 409)


def test_login_user(test_user):
    """Test login endpoint."""
    res = requests.post(f"{API}/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })

    data = log_roundtrip(res, "LOGIN USER")

    assert res.status_code == 200
    assert "token" in data
    assert "user" in data


def test_get_movies():
    """Test movie browsing (Paginated)."""
    # A função get_movies_ai retorna estrutura com paginação
    res = requests.get(f"{API}/movies?limit=5")
    
    data = log_roundtrip(res, "GET MOVIES LIST")

    assert res.status_code == 200
    assert "movies" in data
    assert isinstance(data["movies"], list)
    # Valida campos da nova estrutura de paginação da API
    assert "total" in data
    assert "page" in data


def test_insert_movie():
    """Test inserting a movie (Requires Admin Auth)."""
    
    # 1. Obter credenciais de Admin (Env vars ou default)
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')

    # 2. Fazer Login como Admin
    logger.info(f"=== AUTHENTICATING AS ADMIN: {admin_username} ===")
    
    login_res = requests.post(f"{API}/auth/login", json={
        "username": admin_username,
        "password": admin_password
    })

    login_data = log_roundtrip(login_res, "LOGIN ADMIN")
    
    # Se falhar aqui, verifique se criou o admin no banco de dados
    if "token" not in login_data:
        pytest.fail("Falha ao logar como Admin. Verifique se o user admin existe na DB.")
    
    admin_token = login_data["token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. Preparar dados do filme
    movie = {
        "imdb_id": f"pytest_tt_{int(time.time())}",
        "title": "Pytest Movie Admin Insert",
        "original_title": "Pytest Movie Original",
        "overview": "Movie inserted during pytest by Admin",
        "release_date": "2025-01-01",
        "adult": False,
        "budget": 100000,
        "revenue": 200000,
        "runtime": 110,
        "popularity": 10,
        "vote_average": 7.1,
        "vote_count": 20,
        "original_language": "en",
        "status": "Released",
        "tagline": "pytest tagline",
        "homepage": None,
        "poster_path": None,
        "raw_genres": [],
        "raw_production_companies": []
    }

    # 4. Tentar inserir o filme
    # CORREÇÃO: URL alterada de /insert/movies para /insert/movie (singular) conforme app.py
    res = requests.post(f"{API}/insert/movie", json=movie, headers=headers)
    
    data = log_roundtrip(res, "INSERT MOVIE (AS ADMIN)")

    assert res.status_code == 201
    assert "movie_id" in data


def test_search_movies():
    """Test search."""
    # A função search_movies na API usa 'q' como query param
    res = requests.get(f"{API}/movies/search?q=Setup")
    
    data = log_roundtrip(res, "SEARCH MOVIES")

    assert res.status_code == 200
    assert "movies" in data
    # Verifica paginação
    assert "total" in data


def test_submit_rating(token, test_movie_id):
    """Test rating submission."""
    headers = {"Authorization": f"Bearer {token}"}

    # Rota: /api/movie/<id>/rating (Singular)
    res = requests.post(
        f"{API}/movie/{test_movie_id}/rating",
        json={"rating": 8},
        headers=headers
    )

    data = log_roundtrip(res, "SUBMIT RATING")

    assert res.status_code in (200, 201)
    assert "rating_id" in data


def test_add_movie_rating_update(token, test_movie_id):
    """Test UPDATING a movie rating (Upsert logic)."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # CORREÇÃO: A URL anterior estava errada (/movies/.../ratings).
    # A URL correta na app.py é POST /api/movie/<id>/rating
    res = requests.post(
        f"{API}/movie/{test_movie_id}/rating",
        json={"rating": 9}, # Mudamos a nota para 9 para testar o UPDATE
        headers=headers
    )

    data = log_roundtrip(res, "UPDATE RATING (UPSERT)")

    assert res.status_code in (200, 201)
    assert data["rating"] == 9 # Verifica se a nota foi atualizada


def test_home_feed(token):
    """Test home feed."""
    res = requests.get(
        f"{API}/home",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    data = log_roundtrip(res, "HOME FEED")

    assert res.status_code == 200
    assert "popular" in data
    assert "recent" in data


def test_home_recommendations(token):
    """Test home recommendations endpoint."""
    # Este endpoint existe na app.py (get_home_recommendations)
    res = requests.get(
        f"{API}/home/recommendations",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    log_roundtrip(res, "HOME RECOMMENDATIONS")
    assert res.status_code == 200


def test_get_my_movies(token):
    """Test get my movies endpoint."""
    # Este endpoint existe na app.py (get_myMovies)
    res = requests.get(
        f"{API}/my-movies",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    data = log_roundtrip(res, "GET MY MOVIES")
    
    assert res.status_code == 200
    assert "movies" in data
    assert "total" in data


def test_get_movie_ratings(test_movie_id):
    """Test getting ratings for a movie."""
    # Rota: /api/movies/<id>/ratings
    res = requests.get(f"{API}/movies/{test_movie_id}/ratings")
    
    data = log_roundtrip(res, "GET MOVIE RATINGS")

    assert res.status_code == 200
    assert "average_rating" in data
    assert "rating_counts" in data # A app.py retorna counts


def test_get_profile_authenticated(token, test_user, test_movie_id):
    """Test profile data."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Garante rating prévio
    requests.post(
        f"{API}/movie/{test_movie_id}/rating",
        json={"rating": 9.5},
        headers=headers
    )
    
    res = requests.get(f"{API}/profile", headers=headers)
    
    data = log_roundtrip(res, "GET PROFILE")

    assert res.status_code == 200
    assert data["user"]["username"] == test_user["username"]
    assert "recent_ratings" in data


def test_delete_rating(token, test_movie_id):
    """Test deleting a rating."""
    headers = {"Authorization": f"Bearer {token}"}

    # Rota: DELETE /api/movie/<id>/rating
    res = requests.delete(
        f"{API}/movie/{test_movie_id}/rating",
        headers=headers
    )
    
    data = log_roundtrip(res, "DELETE RATING")
    
    assert res.status_code == 200
    assert data["message"] == "Rating deleted successfully"


def test_logout_success(token):
    """Test successful logout"""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{API}/auth/logout", headers=headers)
    
    data = log_roundtrip(res, "LOGOUT")
    
    assert res.status_code == 200
    assert "message" in data