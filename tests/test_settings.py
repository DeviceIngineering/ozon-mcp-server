"""Тесты модуля настроек (мульти-магазин)."""

import json
import pytest
from ozon_mcp.settings import load_shops, save_shops, get_shop_keys, get_shop_list, get_masked_shop


def test_save_and_load(tmp_path):
    shops = {
        "shop1": {"name": "Альфа", "ozon_client_id": "111", "ozon_api_key": "aaa"},
        "shop2": {"name": "Бета", "ozon_client_id": "222", "ozon_api_key": "bbb"},
    }
    save_shops(tmp_path, shops)
    loaded = load_shops(tmp_path)
    assert loaded["shop1"]["name"] == "Альфа"
    assert loaded["shop1"]["ozon_client_id"] == "111"
    assert loaded["shop2"]["ozon_api_key"] == "bbb"


def test_load_empty(tmp_path):
    loaded = load_shops(tmp_path)
    assert loaded == {}


def test_get_shop_keys(tmp_path):
    save_shops(tmp_path, {"s1": {"name": "S1", "ozon_client_id": "x", "ozon_api_key": "y"}})
    keys = get_shop_keys(tmp_path, "s1")
    assert keys["ozon_client_id"] == "x"


def test_get_shop_keys_not_found(tmp_path):
    save_shops(tmp_path, {"s1": {"name": "S1"}})
    with pytest.raises(ValueError, match="не найден"):
        get_shop_keys(tmp_path, "s999")


def test_get_shop_list(tmp_path):
    save_shops(tmp_path, {
        "a": {"name": "Alpha"},
        "b": {"name": "Beta"},
    })
    lst = get_shop_list(tmp_path)
    ids = [s["id"] for s in lst]
    assert "a" in ids
    assert "b" in ids


def test_masking():
    shop = {"name": "Test", "ozon_client_id": "1234567890", "ozon_api_key": "abc", "ozon_perf_client_id": ""}
    masked = get_masked_shop(shop)
    assert masked["ozon_client_id"] == "123***890"
    assert masked["ozon_api_key"] == "***"
    assert masked["ozon_perf_client_id"] == ""


def test_encryption(tmp_path):
    save_shops(tmp_path, {"s1": {"name": "X", "ozon_api_key": "secret123"}})
    raw = (tmp_path / "shops.json").read_text()
    assert "secret123" not in raw
    loaded = load_shops(tmp_path)
    assert loaded["s1"]["ozon_api_key"] == "secret123"


def test_migration_from_old_settings(tmp_path):
    """Старый settings.json мигрирует в shops.json как 'default'."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    (tmp_path / ".encryption_key").write_bytes(key)
    f = Fernet(key)
    old_data = {
        "ozon_client_id": f.encrypt(b"old_id").decode(),
        "ozon_api_key": f.encrypt(b"old_key").decode(),
        "ozon_perf_client_id": "",
        "ozon_perf_client_secret": "",
    }
    (tmp_path / "settings.json").write_text(json.dumps(old_data))

    loaded = load_shops(tmp_path)
    assert "default" in loaded
    assert loaded["default"]["ozon_client_id"] == "old_id"
