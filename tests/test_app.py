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

TEST_MOVIE_ID = None  # Variável global para armazenar o ID do filme de teste



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
        except Exception as e:
            logger.debug(f"Failed to log request body: {e}")

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
    res = requests.post(f"{API}/movie", json=movie, headers=headers)
    
    data = log_roundtrip(res, "INSERT MOVIE (AS ADMIN)")

    assert res.status_code == 201
    assert "movie_id" in data


def test_search_movies():
    """Test search and save ID to global variable."""
    global TEST_MOVIE_ID  # <--- Permite escrever na variável global

    # Busca pelo filme específico criado pelo Admin
    res = requests.get(f"{API}/movies/search?q=Pytest Movie Admin Insert")
    
    data = log_roundtrip(res, "SEARCH MOVIES (AND SAVE ID)")

    assert res.status_code == 200
    assert "movies" in data
    assert "total" in data

    # Lógica para guardar o ID
    if len(data["movies"]) > 0:
        # Pega o ID do primeiro filme da lista e salva na global
        TEST_MOVIE_ID = data["movies"][0]["id"]
        logger.info(f"💾 GLOBAL ID SAVED: {TEST_MOVIE_ID}")
    else:
        pytest.fail("O filme 'Pytest Movie Admin Insert' não foi encontrado. O ID não pôde ser salvo.")


def test_submit_rating(token):
    """Test rating submission."""
    # NÃO passamos TEST_MOVIE_ID como argumento. Acedemos à global.
    global TEST_MOVIE_ID 
    
    if TEST_MOVIE_ID is None:
        pytest.skip("Skipping: ID do filme não foi encontrado na busca anterior.")

    headers = {"Authorization": f"Bearer {token}"}

    res = requests.post(
        f"{API}/movie/{TEST_MOVIE_ID}/rating",
        json={"rating": 8},
        headers=headers
    )

    data = log_roundtrip(res, "SUBMIT RATING")

    assert res.status_code in (200, 201)
    assert "rating_id" in data


def test_update_movie_as_admin():
    """Test updating a movie (Requires Admin Permissions)."""
    
    # 1. Verificar se temos um ID de filme para atualizar
    global TEST_MOVIE_ID
    if TEST_MOVIE_ID is None:
        pytest.skip("Skipping: ID do filme não foi encontrado nos testes anteriores.")

    # 2. Obter credenciais de Admin (Env vars ou default)
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')

    # 3. Fazer Login como Admin para obter o token correto
    login_res = requests.post(f"{API}/auth/login", json={
        "username": admin_username,
        "password": admin_password
    })
    
    login_data = log_roundtrip(login_res, "LOGIN ADMIN FOR UPDATE")
    
    if "token" not in login_data:
        pytest.fail("Falha ao logar como Admin. Não é possível testar o update.")

    admin_token = login_data["token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 4. Preparar dados para atualização (Update Parcial)
    # Vamos mudar o título e o overview
    new_title = f"Updated Title {int(time.time())}"
    update_payload = {
        "title": new_title,
        "overview": "This overview was updated automatically by the pytest suite.",
        "vote_average": 9.9 # Testar atualização de número
    }

    # 5. Enviar pedido PUT
    # Rota: /api/admin/movies/<id>
    res = requests.put(
        f"{API}/admin/movies/{TEST_MOVIE_ID}",
        json=update_payload,
        headers=headers
    )
    
    data = log_roundtrip(res, "UPDATE MOVIE (ADMIN)")

    # 6. Asserções
    assert res.status_code == 200
    assert data["message"] == "Movie updated successfully"
    assert int(data["movie_id"]) == int(TEST_MOVIE_ID)
    
    # Verifica se a API confirmou quais campos foram alterados
    assert "title" in data["updated_fields"]
    assert "overview" in data["updated_fields"]
    assert "vote_average" in data["updated_fields"]


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


def test_get_movie_ratings():
    """Test getting ratings for a movie."""
    # Rota: /api/movies/<id>/ratings
    res = requests.get(f"{API}/movies/{TEST_MOVIE_ID}/ratings")
    
    data = log_roundtrip(res, "GET MOVIE RATINGS")

    assert res.status_code == 200
    assert "average_rating" in data
    assert "rating_counts" in data # A app.py retorna counts


def test_delete_rating():
    """Test deleting a rating (Requires Admin because of @require_admin)."""
    
    # 1. Verificar se temos um ID de filme
    global TEST_MOVIE_ID
    if TEST_MOVIE_ID is None:
        pytest.skip("Skipping: ID do filme não foi encontrado.")

    # 2. Obter credenciais e Logar como Admin
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')

    login_res = requests.post(f"{API}/auth/login", json={
        "username": admin_username,
        "password": admin_password
    })
    
    login_data = log_roundtrip(login_res, "LOGIN ADMIN FOR DELETE")
    admin_token = login_data["token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. SETUP: O Admin precisa criar uma avaliação antes de a poder apagar
    # (Caso contrário, o DELETE retornaria 404 porque o rating não existe)
    setup_res = requests.post(
        f"{API}/movie/{TEST_MOVIE_ID}/rating",
        json={"rating": 5},
        headers=headers
    )
    assert setup_res.status_code in (200, 201), "Falha ao criar avaliação de setup para o Admin"

    # 4. TESTE: Apagar a avaliação
    # Rota: DELETE /api/movie/<id>/rating
    res = requests.delete(
        f"{API}/movie/{TEST_MOVIE_ID}/rating",
        headers=headers
    )
    
    data = log_roundtrip(res, "DELETE RATING (AS ADMIN)")
    
    assert res.status_code == 200
    assert data["message"] == "Rating deleted successfully"


def test_get_profile_success(token, test_user):
    """
    Test retrieving the authenticated user's profile.
    Valida estrutura do User e das Ratings.
    """
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Obter Perfil
    res = requests.get(f"{API}/profile", headers=headers)
    
    data = log_roundtrip(res, "GET PROFILE")

    # 2. Asserções
    assert res.status_code == 200
    
    # Valida objeto 'user'
    assert "user" in data
    # Nota: Se outros testes correram antes e mudaram o username, isto pode falhar se compararmos estritamente com test_user fixture.
    # Por segurança, validamos se os campos existem.
    assert "id" in data["user"]
    assert "email" in data["user"]
    assert "role" in data["user"]
    
    # Valida lista 'recent_ratings'
    assert "recent_ratings" in data
    assert isinstance(data["recent_ratings"], list)


def test_update_profile_info(token):
    """
    Test updating user details (Username & Email).
    """
    headers = {"Authorization": f"Bearer {token}"}

    # Gera novos dados únicos para evitar conflitos
    new_username = f"UpdatedUser_{int(time.time())}"
    new_email = f"updated_{int(time.time())}@test.com"

    payload = {
        "username": new_username,
        "email": new_email
    }

    # 1. Enviar pedido de atualização
    res = requests.put(f"{API}/profile", json=payload, headers=headers)
    
    data = log_roundtrip(res, "UPDATE PROFILE INFO")

    # 2. Asserções
    assert res.status_code == 200
    assert data["user"]["username"] == new_username
    assert data["user"]["email"] == new_email
    assert data["message"] == "Profile and ratings updated successfully"


def test_update_profile_ratings(token):
    """
    Test updating ratings via the profile endpoint (Batch Update).
    """
    global TEST_MOVIE_ID
    if TEST_MOVIE_ID is None:
        pytest.skip("Skipping: ID do filme não foi encontrado.")

    headers = {"Authorization": f"Bearer {token}"}

    # Define uma nova nota para o filme guardado na variável global
    new_rating_value = 10
    
    payload = {
        # Não enviamos username/email, apenas ratings
        "recent_ratings": [
            {
                "movie_id": TEST_MOVIE_ID,
                "rating": new_rating_value
            }
        ]
    }

    # 1. Enviar atualização
    res = requests.put(f"{API}/profile", json=payload, headers=headers)
    
    data = log_roundtrip(res, "UPDATE PROFILE RATINGS")

    # 2. Asserções
    assert res.status_code == 200
    # Verifica se a contagem de updates está correta
    assert data["ratings_updated_count"] == 1
    
    # 3. Verificação Dupla (GET)
    # Vamos buscar o perfil novamente para garantir que a nota é 10
    get_res = requests.get(f"{API}/profile", headers=headers)
    get_data = get_res.json()
    
    # Procura a rating do filme específico na lista
    found_rating = None
    for r in get_data["recent_ratings"]:
        if r["movie_id"] == TEST_MOVIE_ID:
            found_rating = r["rating"]
            break
            
    assert found_rating == new_rating_value, f"Rating devia ser {new_rating_value}, mas veio {found_rating}"


def test_logout_success(token):
    """Test successful logout"""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{API}/auth/logout", headers=headers)
    
    data = log_roundtrip(res, "LOGOUT")
    
    assert res.status_code == 200
    assert "message" in data