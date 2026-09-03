"""Профили инструментов: сколько из 151 ручки видит клиент.

Claude Code грузит схемы по требованию (tool search), и там профили не нужны.
А Cursor, Cline, Continue и Claude Desktop забирают tools/list целиком — там
весь каталог оплачивается в каждом запросе. Переменная OZON_TOOLSETS оставляет
только те профили, которыми пользуются:

    OZON_TOOLSETS=pricing,ads      # цены и реклама, около 55 инструментов
    OZON_TOOLSETS=                 # (по умолчанию) все

Профили нарезаны по рабочим задачам, а не по разделам документации Ozon: аудит
акций требует одновременно акций, цен и карантина, поэтому они в одном профиле.

Профиль core включён всегда: список магазинов, диагностика, деградации и данные
о токене нужны ровно тогда, когда что-то сломалось, — выключать их нельзя.
"""

from __future__ import annotations

import os
import re

CORE = "core"

# порядок важен: первое совпадение выигрывает
RULES: tuple[tuple[str, str], ...] = (
    (CORE,        r"^ozon_(list_shops|diagnostics|degradations|company|notification|notifications)"),
    ("pricing",   r"^ozon_(get_prices|set_prices|min_price|pricing|actions|seller_action|discount)"),
    ("ads",       r"^ozon_(ad|search_promo)"),
    ("catalog",   r"^ozon_(product|category|brand|certificate)"),
    ("orders",    r"^ozon_(order|orders|supply|warehouse|delivery|cancellation)"),
    ("analytics", r"^ozon_(analytics|stock_on|search_queries|report|rating)"),
    ("feedback",  r"^ozon_(review|question|chat|returns)"),
    ("finance",   r"^ozon_finance"),
)

ALL_PROFILES: tuple[str, ...] = tuple(dict.fromkeys(name for name, _ in RULES))

DESCRIPTIONS = {
    CORE:        "магазины, диагностика, компания, уведомления",
    "pricing":   "цены, минимальная цена, акции Ozon и собственные, ценовые стратегии",
    "ads":       "рекламные кампании, ставки, «оплата за заказ», статистика",
    "catalog":   "товары, атрибуты, категории, сертификаты",
    "orders":    "заказы FBS и FBO, поставки, склады, отмены",
    "analytics": "аналитика, остатки, поисковые запросы, отчёты, рейтинг",
    "feedback":  "отзывы, вопросы, чаты, возвраты",
    "finance":   "финансовые транзакции, отчёты, баланс",
}


def profile_of(name: str) -> str:
    for profile, pattern in RULES:
        if re.match(pattern, name):
            return profile
    return CORE  # неизвестное имя лучше показать, чем спрятать


def enabled_profiles() -> set[str] | None:
    """Профили из OZON_TOOLSETS. None — ограничение не задано, доступно всё."""
    raw = (os.environ.get("OZON_TOOLSETS") or "").strip()
    if not raw:
        return None
    picked = {p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()}
    picked = {p for p in picked if p in ALL_PROFILES}
    return ({CORE} | picked) if picked else None


def is_enabled(name: str) -> bool:
    enabled = enabled_profiles()
    return enabled is None or profile_of(name) in enabled


def disabled_profiles() -> list[str]:
    enabled = enabled_profiles()
    if enabled is None:
        return []
    return [p for p in ALL_PROFILES if p not in enabled]


def availability_note() -> str:
    """Строка для описания ozon_list_shops: что именно выключено и как включить.

    Без неё модель, не найдя инструмента, отвечает «такой возможности нет» —
    хотя возможность есть, её просто отключили в конфиге.
    """
    off = disabled_profiles()
    if not off:
        return ""
    listed = ", ".join(f"{p} ({DESCRIPTIONS[p]})" for p in off)
    return (f" Отключены профили инструментов: {listed}. "
            f"Это ограничение конфигурации (OZON_TOOLSETS), а не отсутствие возможности.")


def unavailable_message(name: str) -> str:
    profile = profile_of(name)
    return (f"Инструмент {name} отключён профилем: он входит в '{profile}' "
            f"({DESCRIPTIONS.get(profile, '')}), а в OZON_TOOLSETS этого профиля нет. "
            f"Добавьте '{profile}' в OZON_TOOLSETS и перезапустите сервер.")
