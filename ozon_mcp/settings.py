"""Управление магазинами и API-ключами: загрузка, сохранение, шифрование."""

import json
import os
from pathlib import Path
from cryptography.fernet import Fernet

SHOP_KEYS = [
    "ozon_client_id",
    "ozon_api_key",
    "ozon_perf_client_id",
    "ozon_perf_client_secret",
]

ENV_MAP = {
    "ozon_client_id": "OZON_CLIENT_ID",
    "ozon_api_key": "OZON_API_KEY",
    "ozon_perf_client_id": "OZON_PERF_CLIENT_ID",
    "ozon_perf_client_secret": "OZON_PERF_CLIENT_SECRET",
}


def _get_fernet(data_dir: Path) -> Fernet:
    key_file = data_dir / ".encryption_key"
    if key_file.exists():
        key = key_file.read_bytes()
    else:
        key = Fernet.generate_key()
        data_dir.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(key)
    return Fernet(key)


def _migrate_old_settings(data_dir: Path):
    """Мигрировать старый settings.json (1 магазин) → shops.json."""
    old_file = data_dir / "settings.json"
    new_file = data_dir / "shops.json"
    if old_file.exists() and not new_file.exists():
        try:
            f = _get_fernet(data_dir)
            encrypted = json.loads(old_file.read_text())
            keys = {}
            for key in SHOP_KEYS:
                if key in encrypted and encrypted[key]:
                    keys[key] = f.decrypt(encrypted[key].encode()).decode()
            if any(keys.values()):
                shops = {"default": {"name": "Default", **keys}}
                save_shops(data_dir, shops)
        except Exception:
            pass


def load_shops(data_dir: Path) -> dict[str, dict]:
    """Загрузить все магазины. Возвращает {shop_id: {name, ozon_client_id, ...}}."""
    _migrate_old_settings(data_dir)

    shops: dict[str, dict] = {}

    # Env-переменные как fallback → магазин "default"
    env_keys = {}
    for key, env_name in ENV_MAP.items():
        val = os.environ.get(env_name, "")
        if val:
            env_keys[key] = val
    if any(env_keys.values()):
        shops["default"] = {"name": "Default", **env_keys}

    # Файл перезаписывает
    shops_file = data_dir / "shops.json"
    if shops_file.exists():
        try:
            f = _get_fernet(data_dir)
            data = json.loads(shops_file.read_text())
            for shop_id, encrypted_shop in data.items():
                shop = {"name": encrypted_shop.get("name", shop_id)}
                for key in SHOP_KEYS:
                    val = encrypted_shop.get(key, "")
                    if val:
                        shop[key] = f.decrypt(val.encode()).decode()
                shops[shop_id] = shop
        except Exception:
            pass

    return shops


def save_shops(data_dir: Path, shops: dict[str, dict]):
    """Зашифровать и сохранить все магазины."""
    data_dir.mkdir(parents=True, exist_ok=True)
    f = _get_fernet(data_dir)
    data = {}
    for shop_id, shop in shops.items():
        encrypted = {"name": shop.get("name", shop_id)}
        for key in SHOP_KEYS:
            val = shop.get(key, "")
            encrypted[key] = f.encrypt(val.encode()).decode() if val else ""
        data[shop_id] = encrypted
    (data_dir / "shops.json").write_text(json.dumps(data, indent=2))


def get_shop_keys(data_dir: Path, shop_id: str) -> dict[str, str]:
    """Получить ключи конкретного магазина."""
    shops = load_shops(data_dir)
    if shop_id not in shops:
        raise ValueError(f"Магазин '{shop_id}' не найден. Доступные: {list(shops.keys())}")
    return shops[shop_id]


def get_shop_list(data_dir: Path) -> list[dict]:
    """Список магазинов для отображения (без ключей)."""
    shops = load_shops(data_dir)
    return [{"id": sid, "name": s.get("name", sid)} for sid, s in shops.items()]


def get_masked_shop(shop: dict) -> dict:
    """Замаскировать ключи магазина для UI."""
    masked = {"name": shop.get("name", "")}
    for key in SHOP_KEYS:
        val = shop.get(key, "")
        if val and len(val) > 6:
            masked[key] = val[:3] + "***" + val[-3:]
        elif val:
            masked[key] = "***"
        else:
            masked[key] = ""
    return masked
