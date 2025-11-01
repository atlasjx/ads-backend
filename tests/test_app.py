def test_app():
    from app import app
    client = app.test_client()
    response = client.get("/")
    assert response.data == b"ads-backend"