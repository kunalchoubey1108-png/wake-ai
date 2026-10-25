from flask_blog import create_app


def test_health():
    client = create_app().test_client()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_create_and_list_posts():
    app = create_app()
    client = app.test_client()
    r = client.post("/posts", json={"title": "Hello", "body": "World"})
    assert r.status_code == 201
    listed = client.get("/posts").get_json()
    assert any(p["title"] == "Hello" for p in listed)


def test_title_required():
    client = create_app().test_client()
    r = client.post("/posts", json={"body": "no title"})
    assert r.status_code == 400
