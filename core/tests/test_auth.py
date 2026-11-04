from conftest import TEST_PASSWORD


def test_wrong_password_fails_and_correct_password_sets_session(client, create_user):
    create_user("tester")

    bad = client.post("/login", data={"username": "tester", "password": "wrong"})
    assert bad.status_code == 401
    assert "session" not in client.cookies
    assert client.get("/").status_code == 303

    good = client.post("/login", data={"username": "tester", "password": TEST_PASSWORD})
    assert good.status_code == 303
    assert good.headers["location"] == "/"
    assert "session" in client.cookies
    home = client.get("/")
    assert home.status_code == 200
    assert "tester" in home.text


def test_unauthenticated_request_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_logout_clears_session(client, login_as):
    login_as("tester")
    assert client.get("/").status_code == 200
    client.post("/logout")
    assert client.get("/").status_code == 303


def test_no_unauthenticated_docs_routes(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
