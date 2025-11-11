# API Testing with cURL Commands

This document contains cURL commands to test all endpoints of the Flask API.

## Prerequisites

- Flask app running on `http://localhost:80`
- PostgreSQL database configured and running
- Replace `YOUR_TOKEN_HERE` with actual token after login

---

## 1. Health Check

```bash
curl -X GET http://localhost:80/
```

**Expected Response:**
```
ads-backend
```

---

## 2. User Registration

### Register a new user

```bash
curl -X POST http://localhost:80/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "testuser@example.com",
    "password": "securepassword123"
  }'
```

**Expected Response:**
```json
{
  "message": "User registered successfully",
  "user_id": 1
}
```

### Try to register duplicate user (should fail)

```bash
curl -X POST http://localhost:80/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "testuser@example.com",
    "password": "anotherpassword"
  }'
```

**Expected Response:**
```json
{
  "error": "Username or email already exists"
}
```

---

## 3. User Login

### Login with correct credentials

```bash
curl -X POST http://localhost:80/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "securepassword123"
  }'
```

**Expected Response:**
```json
{
  "message": "Login successful",
  "token": "XyZ123AbC456...",
  "user": {
    "id": 1,
    "username": "testuser",
    "email": "testuser@example.com"
  }
}
```

**Save the token for subsequent requests!**

### Login with wrong credentials

```bash
curl -X POST http://localhost:80/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "wrongpassword"
  }'
```

**Expected Response:**
```json
{
  "error": "Invalid credentials"
}
```

---

## 4. Browse Movies (No Auth Required)

### Get first page of movies

```bash
curl -X GET "http://localhost:80/api/movies?page=1&limit=10"
```

### Get second page with different limit

```bash
curl -X GET "http://localhost:80/api/movies?page=2&limit=5"
```

**Expected Response:**
```json
{
  "movies": [
    {
      "id": 1,
      "imdb_id": "tt1234567",
      "title": "Example Movie",
      "overview": "An example movie...",
      "release_date": "2023-01-15",
      "popularity": 123.45,
      "vote_average": 7.8,
      "vote_count": 1500,
      "poster_path": "/path/to/poster.jpg"
    }
  ],
  "page": 1,
  "limit": 10,
  "total": 100,
  "total_pages": 10
}
```

---

## 5. Search Movies

### Search by title

```bash
curl -X GET "http://localhost:80/api/movies/search?q=avengers&page=1&limit=10"
```

### Search by keyword in overview

```bash
curl -X GET "http://localhost:80/api/movies/search?q=superhero"
```

**Expected Response:**
```json
{
  "movies": [...],
  "query": "avengers",
  "page": 1,
  "limit": 10,
  "total": 15,
  "total_pages": 2
}
```

---

## 6. Insert New Movie (Requires Auth)

### Without authentication (should fail)

```bash
curl -X POST http://localhost:80/api/movies \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New Test Movie",
    "overview": "A test movie",
    "release_date": "2024-01-01"
  }'
```

**Expected Response:**
```json
{
  "error": "No authorization token provided"
}
```

### With authentication

```bash
curl -X POST http://localhost:80/api/movies \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "imdb_id": "tt9999999",
    "title": "New Test Movie",
    "original_title": "New Test Movie",
    "overview": "This is a test movie created via API",
    "release_date": "2024-01-01",
    "adult": false,
    "budget": 1000000,
    "revenue": 5000000,
    "runtime": 120.0,
    "popularity": 50.5,
    "vote_average": 7.5,
    "vote_count": 100,
    "original_language": "en",
    "status": "Released",
    "tagline": "A test movie",
    "homepage": "http://example.com",
    "poster_path": "/test_poster.jpg",
    "raw_genres": "Action, Drama",
    "raw_production_companies": "Test Studios"
  }'
```

**Expected Response:**
```json
{
  "message": "Movie inserted successfully",
  "movie_id": 101
}
```

---

## 7. Submit Movie Rating (Requires Auth)

### Without authentication (should fail)

```bash
curl -X POST http://localhost:80/api/movie/1/rating \
  -H "Content-Type: application/json" \
  -d '{
    "rating": 8.5
  }'
```

**Expected Response:**
```json
{
  "error": "No authorization token provided"
}
```

### With authentication - Submit rating

```bash
curl -X POST http://localhost:80/api/movie/1/rating \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "rating": 8.5
  }'
```

**Expected Response:**
```json
{
  "message": "Rating submitted successfully",
  "rating_id": 1,
  "movie_id": 1,
  "rating": 8.5
}
```

### Update existing rating

```bash
curl -X POST http://localhost:80/api/movie/1/rating \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "rating": 9.0
  }'
```

### Invalid rating (should fail)

```bash
curl -X POST http://localhost:80/api/movie/1/rating \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "rating": 15.0
  }'
```

**Expected Response:**
```json
{
  "error": "Rating must be between 0 and 10"
}
```

---

## 8. Get Home Page (With Recommendations)

### Without authentication (basic catalog)

```bash
curl -X GET http://localhost:80/api/home
```

**Expected Response:**
```json
{
  "popular": [...],
  "recent": [...]
}
```

### With authentication (includes recommendations)

```bash
curl -X GET http://localhost:80/api/home \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected Response:**
```json
{
  "popular": [...],
  "recent": [...],
  "recommended": [...]
}
```

---

## Testing Workflow Example

Here's a complete testing workflow:

```bash
# 1. Register a user
TOKEN=$(curl -s -X POST http://localhost:80/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@test.com","password":"demo123"}' \
  | grep -o '"user_id":[0-9]*')

echo "User created: $TOKEN"

# 2. Login and save token
TOKEN=$(curl -s -X POST http://localhost:80/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}' \
  | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "Token: $TOKEN"

# 3. Browse movies
curl -X GET "http://localhost:80/api/movies?page=1&limit=5"

# 4. Search for a movie
curl -X GET "http://localhost:80/api/movies/search?q=action"

# 5. Rate a movie
curl -X POST http://localhost:80/api/movie/1/rating \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"rating": 9.0}'

# 6. Get personalized home page
curl -X GET http://localhost:80/api/home \
  -H "Authorization: Bearer $TOKEN"
```

---

## Notes

- Replace `http://localhost:80` with your actual server URL
- Save the token from login response and use it in subsequent authenticated requests
- All POST requests require `Content-Type: application/json` header
- Authenticated requests require `Authorization: Bearer YOUR_TOKEN` header
- Token format can be just the token or prefixed with "Bearer "