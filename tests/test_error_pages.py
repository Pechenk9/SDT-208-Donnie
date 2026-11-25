"""Browsers get a Donnie error page; API clients keep FastAPI's JSON errors."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HTML = {"accept": "text/html,application/xhtml+xml"}


def test_browser_gets_html_404_in_its_language():
    en = client.get("/en/no-such-page", headers=HTML)
    assert en.status_code == 404
    assert "text/html" in en.headers["content-type"]
    assert "Page not found" in en.text

    ua = client.get("/ua/no-such-page", headers=HTML)
    assert ua.status_code == 404
    assert "Сторінку не знайдено" in ua.text


def test_bad_path_parameter_is_a_404_page_for_browsers():
    response = client.get("/en/product/abc", headers=HTML)
    assert response.status_code == 404
    assert "Page not found" in response.text


def test_api_clients_still_get_json():
    response = client.get("/en/no-such-page")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}

    api = client.get("/api/no-such-endpoint", headers=HTML)
    assert api.status_code == 404
    assert api.json() == {"detail": "Not Found"}


def test_redirects_are_untouched():
    response = client.get("/en/owner", headers=HTML, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/en/login")
