"""Тесты веб-эндпоинтов."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    import ozon_mcp.app as app_module
    import ozon_mcp.server as server_module
    app_module.DATA_DIR = tmp_path
    server_module.DATA_DIR = tmp_path
    from ozon_mcp.app import fastapi_app
    with TestClient(fastapi_app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_shops_page(client):
    r = client.get("/shops")
    assert r.status_code == 200
    assert "Магазины" in r.text


def test_add_shop(client):
    r = client.post("/api/shops", json={
        "shop_id": "test1",
        "name": "Test Shop",
        "ozon_client_id": "111",
        "ozon_api_key": "222",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Проверим что появился
    r2 = client.get("/shops")
    assert "Test Shop" in r2.text


def test_add_shop_no_id(client):
    r = client.post("/api/shops", json={"name": "No ID"})
    assert r.status_code == 400


def test_delete_shop(client):
    client.post("/api/shops", json={"shop_id": "del1", "name": "To Delete"})
    r = client.delete("/api/shops/del1")
    assert r.status_code == 200

    r2 = client.delete("/api/shops/del1")
    assert r2.status_code == 404


def test_stats_api(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "shops" in data


def test_stats_api_with_shop_filter(client):
    r = client.get("/api/stats?shop=test")
    assert r.status_code == 200
