import pytest
import requests
import json
import time
import os

BASE_URL = os.environ.get("API_HOST", "http://localhost")
API = BASE_URL + "/api"


# -----------------------------------
# Helpers
# -----------------------------------

def pretty(label, data):
    print(f"\n===== {label} =====")
    print(json.dumps(data, indent=4))


# -----------------------------------
# Fixtures
# -----------------------------------

@pytest.fixture(scope="session")
def test_user():
    """Generate a unique user for API tests."""
    ts = int(time.time())
    return {
        "username": f"pytest_user_{ts}",
        "email": f"pytest_email_{ts}@test.com",
        "password": "Testpassword@123"
    }


@pytest.fixture(scope="session")
def token(test_user):
    """Register and login user, return token."""

    # Register (ignore if already exists)
    requests.post(f"{API}/auth/register", json=test_user)

    # Login
    res = requests.post(f"{API}/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })

    data = res.json()
    pretty("LOGIN RESPONSE", data)

    assert "token" in data, "Login failed, no token returned"

    return data["token"]


# -----------------------------------
# Tests (endpoint-only)
# -----------------------------------

def test_register_user(test_user):
    """Test user registration endpoint."""
    res = requests.post(f"{API}/auth/register", json=test_user)
    data = res.json()
    print("Register user -->", data)
    pretty("REGISTER RESPONSE", data)

   

    # Accept 201 (success) or 409 (already exists)
    assert res.status_code in (201, 409)


def test_login_user(test_user):
    """Test login endpoint."""
    res = requests.post(f"{API}/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })

    data = res.json()
    pretty("LOGIN AGAIN RESPONSE", data)

    assert "token" in data

def test_logout_success(token):
    """Test successful logout"""
    headers = {"Authorization": f"Bearer {token}"}
    
    res = requests.post(f"{API}/auth/logout", headers=headers)
    
    assert res.status_code == 200
    assert res.json()["message"] == "Logout successful"

def test_get_movies():
    """Test movie browsing endpoint."""
    res = requests.get(f"{API}/movies?limit=5")
    data = res.json()

    pretty("MOVIES LIST", data)

    assert "movies" in data
    assert isinstance(data["movies"], list)


def test_insert_movie(token):
    """Test inserting a movie (auth required)."""
    headers = {"Authorization": f"Bearer {token}"}

    movie = {
        "imdb_id": f"pytest_tt_{int(time.time())}",
        "title": "Pytest Movie",
        "original_title": "Pytest Movie Original",
        "overview": "Movie inserted during pytest",
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

    res = requests.post(f"{API}/movies", json=movie, headers=headers)
    data = res.json()

    pretty("INSERT MOVIE RESPONSE", data)

    assert res.status_code == 201
    assert "movie_id" in data


def test_search_movies():
    """Test movie search endpoint."""
    res = requests.get(f"{API}/movies/search?q=Test")
    data = res.json()

    pretty("SEARCH RESULTS", data)

    assert "movies" in data
    assert isinstance(data["movies"], list)


def test_submit_rating(token):
    """Test rating submission endpoint."""
    headers = {"Authorization": f"Bearer {token}"}

    # Use movie ID 1 (should exist in your DB)
    movie_id = 1

    res = requests.post(
        f"{API}/movie/{movie_id}/rating",
        json={"rating": 8},
        headers=headers
    )

    data = res.json()

    pretty("SUBMIT RATING RESPONSE", data)

    assert res.status_code in (200, 201)
    assert "rating" in data


def test_home_feed(token):
    """Test home feed endpoint."""
    res = requests.get(
        f"{API}/home",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = res.json()

    pretty("HOME FEED", data)

    assert "popular" in data
    assert "recent" in data

def test_get_movie_ratings(test_movie_id):
    """Test getting ratings for a movie endpoint."""
    
    res = requests.get(f"{API}//movies/{test_movie_id}/ratings")
    data = res.json()

    pretty("GET MOVIE RATINGS RESPONSE", data)

    assert res.status_code == 200
    assert "movie_id" in data
    assert "average_rating" in data
    assert "rating_counts" in data
    assert "ratings" in data

def test_add_movie_rating(token, test_movie_id):
    """Test adding or updating a movie rating endpoint."""
    headers = {"Authorization": f"Bearer {token}"}

    res = requests.post(
        f"{API}//movies/{test_movie_id}/ratings",
        json={"rating": 8},
        headers=headers
    )

    data = res.json()

    pretty("ADD MOVIE RATING RESPONSE", data)

    assert res.status_code == 201
    assert "message" in data

def test_home_feed_unauthenticated():
    """Ensure unauthenticated home feed still works."""
    res = requests.get(f"{API}/home")
    data = res.json()

    pretty("HOME FEED (NO AUTH)", data)

    assert "popular" in data
    assert "recent" in data


# -----------------------------------
# Profile Tests
# -----------------------------------

def test_get_profile_authenticated(token, test_user, test_movie_id):
    """
    Test retrieving authenticated user profile data.
    Requires:
    1. A valid 'token' from the login fixture.
    2. The 'test_user' data to verify returned username/email.
    3. The 'test_movie_id' to ensure a rating exists for the 'recent_ratings' list.
    """
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Ensure the test user has a rating (if not already done by other tests)
    # This guarantees the 'recent_ratings' list is not empty for assertion.
    rating_res = requests.post(
        f"{API}/movie/{test_movie_id}/rating",
        json={"rating": 9.5},
        headers=headers
    )
    # Assert successful rating insert/update
    assert rating_res.status_code in (200, 201), "Precondition failed: Could not submit test rating."
    
    # 2. Get the profile
    res = requests.get(f"{API}/profile", headers=headers)
    data = res.json()

    pretty("GET PROFILE RESPONSE", data)

    # Assert successful request
    assert res.status_code == 200
    
    # Assert top-level structure
    assert "user" in data
    assert "recent_ratings" in data
    
    # Assert user data integrity
    assert data["user"]["username"] == test_user["username"]
    assert data["user"]["email"] == test_user["email"]
    
    # Assert recent ratings contain the rating we just submitted
    assert len(data["recent_ratings"]) >= 1
    
    # Check if the rating submitted is in the list
    rated_movie_ids = [r["movie_id"] for r in data["recent_ratings"]]
    assert test_movie_id in rated_movie_ids
    
    # Check the format of a recent rating entry
    if data["recent_ratings"]:
        first_rating = data["recent_ratings"][0]
        assert "rating" in first_rating
        assert "movie_title" in first_rating
        assert "rated_at" in first_rating
        assert "poster_path" in first_rating