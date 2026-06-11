"""Ozon MCP Server — инструменты для управления бизнесом на Ozon.

Разделы: Магазины, Акции, Цены, Финансы, Рейтинг, Отзывы, Реклама, Аналитика, Товары,
Ценовые стратегии, Импорт товаров, Заказы FBS, Возвраты, Вопросы, Чаты, Отмены,
Склады, Отчёты, Бренды, Категории, Уведомления, Скидки, Компания, Сертификаты.

Поддержка нескольких магазинов через параметр shop_id.
"""

import json
import os
import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ozon_mcp.client import OzonSellerClient, OzonPerformanceClient

# ─── Инициализация ────────────────────────────────────────

app = Server("ozon-mcp-server")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

# Пул клиентов: {shop_id: {"seller": ..., "perf": ...}}
_pool: dict[str, dict] = {}


def _get_seller(shop_id: str) -> OzonSellerClient:
    if shop_id in _pool and "seller" in _pool[shop_id]:
        return _pool[shop_id]["seller"]

    from ozon_mcp.settings import get_shop_keys
    keys = get_shop_keys(DATA_DIR, shop_id)
    client_id = keys.get("ozon_client_id", "")
    api_key = keys.get("ozon_api_key", "")
    if not client_id or not api_key:
        raise ValueError(f"Магазин '{shop_id}': не заданы OZON_CLIENT_ID / OZON_API_KEY")
    client = OzonSellerClient(client_id, api_key)
    _pool.setdefault(shop_id, {})["seller"] = client
    return client


def _get_perf(shop_id: str) -> OzonPerformanceClient:
    if shop_id in _pool and "perf" in _pool[shop_id]:
        return _pool[shop_id]["perf"]

    from ozon_mcp.settings import get_shop_keys
    keys = get_shop_keys(DATA_DIR, shop_id)
    client_id = keys.get("ozon_perf_client_id", "")
    client_secret = keys.get("ozon_perf_client_secret", "")
    if not client_id or not client_secret:
        raise ValueError(f"Магазин '{shop_id}': не заданы OZON_PERF_CLIENT_ID / OZON_PERF_CLIENT_SECRET")
    client = OzonPerformanceClient(client_id, client_secret)
    _pool.setdefault(shop_id, {})["perf"] = client
    return client


# Публичный доступ к клиентам (для app.py / диагностики)
def get_seller_for_shop(shop_id: str) -> OzonSellerClient:
    return _get_seller(shop_id)


async def reset_shop(shop_id: str):
    """Закрыть и удалить клиентов конкретного магазина."""
    if shop_id in _pool:
        for client in _pool[shop_id].values():
            await client.close()
        del _pool[shop_id]


async def reset_all_clients():
    """Закрыть всех клиентов."""
    for shop_id in list(_pool.keys()):
        await reset_shop(shop_id)


def get_mcp_app() -> Server:
    """Вернуть MCP Server instance для SSE-транспорта."""
    return app


def _json(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]


# Callback для записи статистики (устанавливается из app.py)
_stats_callback: Callable[..., Awaitable[None]] | None = None


def set_stats_callback(cb: Callable[..., Awaitable[None]]):
    global _stats_callback
    _stats_callback = cb


# ─── Общий фрагмент shop_id для inputSchema ─────────────────

SHOP_ID_PROP = {"type": "string", "description": "ID магазина (из ozon_list_shops)"}


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> Tool:
    """Создать Tool с обязательным shop_id."""
    props = {"shop_id": SHOP_ID_PROP}
    if properties:
        props.update(properties)
    req = ["shop_id"]
    if required:
        req.extend(required)
    return Tool(name=name, description=description, inputSchema={"type": "object", "properties": props, "required": req})


# ─── Определение инструментов ─────────────────────────────

TOOLS = [
    # === МАГАЗИНЫ ===
    Tool(
        name="ozon_list_shops",
        description="Список зарегистрированных магазинов Ozon. Возвращает shop_id и название каждого магазина. Используй shop_id из этого списка для всех остальных инструментов.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),

    # === P0: АКЦИИ ===
    _tool("ozon_actions_list",
          "[P0] Список всех доступных акций Ozon. Показывает какие акции сейчас активны и какие товары могут быть затянуты. КРИТИЧНО: товары в акциях могут продаваться ниже себестоимости."),
    _tool("ozon_actions_candidates",
          "[P0] Товары-кандидаты в акцию — какие товары Ozon ПЛАНИРУЕТ затянуть в акцию. Упреждающий мониторинг для защиты от продажи в минус.",
          {"action_id": {"type": "integer", "description": "ID акции из ozon_actions_list"}},
          ["action_id"]),
    _tool("ozon_actions_products",
          "[P0] Товары уже УЧАСТВУЮЩИЕ в акции. Показывает какие товары сейчас продаются по акционной цене.",
          {"action_id": {"type": "integer", "description": "ID акции"}},
          ["action_id"]),
    _tool("ozon_actions_activate",
          "[P0] Добавить или УБРАТЬ товары из акции. Используй для вывода убыточных товаров из акции.",
          {"action_id": {"type": "integer"},
           "products": {"type": "array", "items": {"type": "object", "properties": {"product_id": {"type": "integer"}, "action_price": {"type": "number", "description": "Цена в акции (0 = вывести)"}}}}},
          ["action_id", "products"]),

    # === ЦЕНОВЫЕ СТРАТЕГИИ ===
    _tool("ozon_pricing_strategy_list",
          "Список стратегий ценообразования.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_pricing_strategy_create",
          "Создать стратегию ценообразования.",
          {"strategy": {"type": "object", "description": "Параметры стратегии"}},
          ["strategy"]),
    _tool("ozon_pricing_strategy_update",
          "Обновить стратегию ценообразования.",
          {"strategy": {"type": "object"}},
          ["strategy"]),
    _tool("ozon_pricing_strategy_delete",
          "Удалить стратегию ценообразования.",
          {"strategy_id": {"type": "integer"}},
          ["strategy_id"]),
    _tool("ozon_pricing_currency_convert",
          "Конвертация валют.",
          {"currency_from": {"type": "string"}, "currency_to": {"type": "string"}, "amount": {"type": "number"}},
          ["currency_from", "currency_to", "amount"]),
    _tool("ozon_pricing_competitor_prices",
          "Цены конкурентов.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === P0: ЦЕНЫ ===
    _tool("ozon_set_prices",
          "[P0] Установить/обновить цены на товары. КРИТИЧНО: используй min_price для защиты от акций ниже себестоимости.",
          {"prices": {"type": "array", "description": "Массив: offer_id, price, old_price, min_price, auto_action_enabled", "items": {"type": "object"}}},
          ["prices"]),
    _tool("ozon_get_prices",
          "[P0] Получить текущие цены, скидки, мин. цену и индекс цен. price_index > 1.15 = риск карантина.",
          {"offer_id": {"type": "array", "items": {"type": "string"}, "description": "Фильтр по артикулам (опц.)"},
           "product_id": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр по product_id (опц.)"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_get_prices_v4",
          "[P1] Получить цены через v4 API (включает purchase_price/себестоимость).",
          {"offer_id": {"type": "array", "items": {"type": "string"}, "description": "Фильтр по артикулам"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_min_price_timer_status",
          "[P0] Статус таймера минимальной цены (30 дней). Если истёк — товар уязвим для акций ниже себестоимости!",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_min_price_timer_renew",
          "[P0] Продлить таймер минимальной цены на 30 дней.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === P0: ФИНАНСЫ ===
    _tool("ozon_finance_transactions",
          "[P0] Финансовые транзакции: комиссии, логистика, хранение, возвраты — ВСЕ расходы по каждой продаже.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DDT00:00:00Z"},
           "date_to": {"type": "string"},
           "page": {"type": "integer", "default": 1},
           "page_size": {"type": "integer", "default": 50},
           "operation_type": {"type": "array", "items": {"type": "string"}, "description": "Фильтр по типу (опц.)"}},
          ["date_from", "date_to"]),
    _tool("ozon_finance_totals",
          "[P0] Итоги финансов за период: суммарные комиссии, логистика, хранение.",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("ozon_finance_realization",
          "[P1] Отчёт о реализации за месяц.",
          {"date": {"type": "string", "description": "YYYY-MM"}},
          ["date"]),
    _tool("ozon_finance_cash_flow",
          "[P1] Движение денежных средств.",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P0: РЕЙТИНГ ===
    _tool("ozon_rating_summary",
          "[P0] Рейтинг продавца. Влияет на позиции в выдаче, доступ к акциям, стоимость хранения."),
    _tool("ozon_rating_history",
          "[P1] История изменения рейтинга.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P0: ОТЗЫВЫ ===
    _tool("ozon_reviews",
          "[P0] Список отзывов на товары. Негатив снижает конверсию.",
          {"sku": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр по SKU (опц.)"},
           "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_review_reply",
          "Ответить на отзыв.",
          {"review_id": {"type": "string"}, "text": {"type": "string"}},
          ["review_id", "text"]),
    _tool("ozon_review_reply_update",
          "Обновить ответ на отзыв.",
          {"review_id": {"type": "string"}, "comment_id": {"type": "string"}, "text": {"type": "string"}},
          ["review_id", "comment_id", "text"]),
    _tool("ozon_review_reply_delete",
          "Удалить ответ на отзыв.",
          {"review_id": {"type": "string"}, "comment_id": {"type": "string"}},
          ["review_id", "comment_id"]),

    # === P0: РЕКЛАМА ===
    _tool("ozon_ad_campaigns",
          "[P0] Список рекламных кампаний: бюджеты, ставки, статусы."),
    _tool("ozon_ad_statistics",
          "[P0] Статистика по рекламным кампаниям: расходы, показы, клики, заказы, ДРР.",
          {"campaigns": {"type": "array", "items": {"type": "integer"}, "description": "ID кампаний"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "date_to": {"type": "string"},
           "group_by": {"type": "string", "default": "DATE"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_campaign_stop",
          "[P0] Экстренная остановка рекламной кампании.",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_objects",
          "[P1] Товары и ставки внутри рекламной кампании.",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_create",
          "Создать рекламную кампанию.",
          {"title": {"type": "string"}, "campaign_type": {"type": "string"}, "products": {"type": "array", "items": {"type": "object"}}, "daily_budget": {"type": "number"}},
          ["title", "campaign_type", "products"]),
    _tool("ozon_ad_campaign_activate",
          "Запустить рекламную кампанию.",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_bids",
          "Обновить ставки рекламной кампании.",
          {"campaign_id": {"type": "integer"}, "bids": {"type": "array", "items": {"type": "object"}}},
          ["campaign_id", "bids"]),
    _tool("ozon_ad_campaign_budget",
          "Бюджет рекламной кампании.",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_budget_update",
          "Обновить бюджет кампании.",
          {"campaign_id": {"type": "integer"}, "daily_budget": {"type": "number"}, "total_budget": {"type": "number"}},
          ["campaign_id", "daily_budget"]),
    _tool("ozon_ad_statistics_daily",
          "Ежедневная статистика рекламы.",
          {"campaigns": {"type": "array", "items": {"type": "integer"}}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_statistics_expenses",
          "Расходы по рекламным кампаниям.",
          {"campaigns": {"type": "array", "items": {"type": "integer"}}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_campaign_objects_update",
          "Обновить товары в рекламной кампании.",
          {"campaign_id": {"type": "integer"}, "objects": {"type": "array", "items": {"type": "object"}}},
          ["campaign_id", "objects"]),
    _tool("ozon_ad_balance",
          "Баланс рекламного кабинета."),

    # === P1: АНАЛИТИКА ===
    _tool("ozon_analytics",
          "[P1] Аналитика: выручка, заказы, возвраты, конверсия по SKU.",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "metrics": {"type": "array", "items": {"type": "string"}, "description": "revenue, ordered_units, returns_count, session_view, etc."},
           "dimensions": {"type": "array", "items": {"type": "string"}, "description": "sku, day, week, month, etc."},
           "limit": {"type": "integer", "default": 1000}},
          ["date_from", "date_to", "metrics", "dimensions"]),
    _tool("ozon_stock_on_warehouses",
          "[P1] Остатки и оборачиваемость товаров на складах Ozon (через turnover/stocks — старый эндпоинт удалён Ozon).",
          {"limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}),
    _tool("ozon_analytics_stocks",
          "[P1] Аналитика по остаткам конкретных товаров: доступность, дефицитность, ликвидность (1-100 SKU).",
          {"skus": {"type": "array", "items": {"type": "integer"}, "description": "SKU товаров (1-100)"}},
          ["skus"]),

    # === P1: ТОВАРЫ ===
    _tool("ozon_product_list",
          "[P1] Список всех товаров. visibility: ALL, VISIBLE, QUARANTINE, ARCHIVED и др.",
          {"visibility": {"type": "string", "default": "ALL", "description": "ALL, VISIBLE, QUARANTINE, ARCHIVED..."},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_product_info",
          "[P1] Расширенная информация по товарам.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_product_attributes",
          "[P1] Атрибуты товаров включая БРЕНД.",
          {"offer_id": {"type": "array", "items": {"type": "string"}, "description": "Фильтр по артикулам (опц.)"},
           "product_id": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр по ID (опц.)"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_product_stocks",
          "[P1] Остатки товаров на складах FBO/FBS.",
          {"offer_id": {"type": "array", "items": {"type": "string"}},
           "product_id": {"type": "array", "items": {"type": "integer"}},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_product_certificates",
          "[P1] Сертификаты товаров. Просроченный = блокировка.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === ИМПОРТ И ОБНОВЛЕНИЕ ТОВАРОВ ===
    _tool("ozon_product_import",
          "Создать/обновить товары (массовый импорт).",
          {"items": {"type": "array", "items": {"type": "object"}, "description": "Массив товаров для импорта"}},
          ["items"]),
    _tool("ozon_product_import_info",
          "Статус задачи импорта товаров.",
          {"task_id": {"type": "integer"}},
          ["task_id"]),
    _tool("ozon_product_update_offer_id",
          "Обновить артикулы товаров.",
          {"update_offer_id": {"type": "array", "items": {"type": "object"}}},
          ["update_offer_id"]),
    _tool("ozon_product_update_images",
          "Обновить изображения товара.",
          {"product_id": {"type": "integer"}, "images": {"type": "array", "items": {"type": "string"}}},
          ["product_id", "images"]),
    _tool("ozon_product_description",
          "Описание товара по артикулу.",
          {"offer_id": {"type": "string"}},
          ["offer_id"]),
    _tool("ozon_product_update_stocks",
          "Обновить остатки FBS.",
          {"stocks": {"type": "array", "items": {"type": "object"}, "description": "offer_id/product_id, stock, warehouse_id"}},
          ["stocks"]),
    _tool("ozon_product_geo_restrictions",
          "Установить географические ограничения.",
          {"product_id": {"type": "integer"}, "restrictions": {"type": "array", "items": {"type": "object"}}},
          ["product_id", "restrictions"]),
    _tool("ozon_product_unarchive",
          "Вернуть товары из архива.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_product_delete",
          "Удалить товары без продаж.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_product_limits",
          "Лимиты на создание товаров."),
    _tool("ozon_product_rating_by_sku",
          "Рейтинг контента товаров.",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_product_discounted",
          "Уценённые товары.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === ЗАКАЗЫ FBS ===
    _tool("ozon_orders_fbs",
          "Заказы FBS с финансовыми данными.",
          {"since": {"type": "string"}, "to": {"type": "string"}, "limit": {"type": "integer", "default": 50}, "status": {"type": "string", "description": "awaiting_packaging, awaiting_deliver, delivering, etc."}},
          ["since", "to"]),
    _tool("ozon_order_fbs_get",
          "Детали отправления FBS.",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),
    _tool("ozon_order_fbs_ship",
          "Отгрузить отправление FBS.",
          {"posting_number": {"type": "string"}, "packages": {"type": "array", "items": {"type": "object"}}},
          ["posting_number", "packages"]),
    _tool("ozon_order_fbs_cancel",
          "Отменить отправление FBS.",
          {"posting_number": {"type": "string"}, "cancel_reason_id": {"type": "integer"}, "cancel_reason_message": {"type": "string"}},
          ["posting_number", "cancel_reason_id"]),
    _tool("ozon_order_fbs_cancel_reasons",
          "Список причин отмены FBS."),
    _tool("ozon_order_fbs_act_create",
          "Создать акт приёма-передачи FBS.",
          {"containers_count": {"type": "integer", "default": 1}}),
    _tool("ozon_order_fbs_act_status",
          "Статус формирования акта.",
          {"id": {"type": "integer"}},
          ["id"]),
    _tool("ozon_order_fbs_act_pdf",
          "Скачать PDF акта приёма-передачи.",
          {"id": {"type": "integer"}},
          ["id"]),
    _tool("ozon_order_fbs_digital_act",
          "Создать электронный акт.",
          {"id": {"type": "integer"}},
          ["id"]),
    _tool("ozon_order_fbs_country_list",
          "Страны для отправления FBS.",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),
    _tool("ozon_order_fbs_country_set",
          "Указать страну товара в отправлении.",
          {"posting_number": {"type": "string"}, "product_id": {"type": "integer"}, "country_iso": {"type": "string"}},
          ["posting_number", "product_id", "country_iso"]),
    _tool("ozon_order_fbs_restrictions",
          "Ограничения отправлений FBS.",
          {"posting_number": {"type": "array", "items": {"type": "string"}}},
          ["posting_number"]),
    _tool("ozon_order_fbs_timeslot",
          "Изменить тайм-слот отправления.",
          {"posting_number": {"type": "string"}, "new_timeslot_id": {"type": "integer"}},
          ["posting_number", "new_timeslot_id"]),
    _tool("ozon_order_fbo_get",
          "Детали отправления FBO.",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),

    # === P1: ЗАКАЗЫ FBO ===
    _tool("ozon_orders_fbo",
          "[P1] Заказы FBO.",
          {"since": {"type": "string", "description": "YYYY-MM-DDT00:00:00Z"},
           "to": {"type": "string"},
           "limit": {"type": "integer", "default": 50}},
          ["since", "to"]),

    # === ВОЗВРАТЫ ===
    _tool("ozon_returns_fbo",
          "Возвраты FBO.",
          {"filter": {"type": "object"}, "limit": {"type": "integer", "default": 50}},
          ["filter"]),
    _tool("ozon_returns_fbs",
          "Возвраты FBS.",
          {"filter": {"type": "object"}, "limit": {"type": "integer", "default": 50}},
          ["filter"]),
    _tool("ozon_returns_fbs_approve",
          "Одобрить возврат FBS.",
          {"return_id": {"type": "integer"}},
          ["return_id"]),
    _tool("ozon_returns_fbs_reject",
          "Отклонить возврат FBS.",
          {"return_id": {"type": "integer"}, "reason": {"type": "string"}},
          ["return_id", "reason"]),
    _tool("ozon_returns_fbs_get",
          "Детали возврата FBS.",
          {"return_id": {"type": "integer"}},
          ["return_id"]),

    # === P1: ВОЗВРАТЫ (LEGACY) ===
    _tool("ozon_returns_report",
          "[P1] Создать отчёт по возвратам.",
          {"filter": {"type": "object", "description": "date_from, date_to и др."}},
          ["filter"]),

    # === ВОПРОСЫ ===
    _tool("ozon_questions",
          "Список вопросов покупателей.",
          {"limit": {"type": "integer", "default": 50}, "last_id": {"type": "string"}}),
    _tool("ozon_question_reply",
          "Ответить на вопрос покупателя.",
          {"question_id": {"type": "string"}, "text": {"type": "string"}},
          ["question_id", "text"]),

    # === ЧАТЫ ===
    _tool("ozon_chat_list",
          "Список чатов с покупателями (v3). unread_only=true — только с непрочитанными.",
          {"unread_only": {"type": "boolean", "default": False},
           "page_size": {"type": "integer", "default": 100}}),
    _tool("ozon_chat_history",
          "История сообщений чата.",
          {"chat_id": {"type": "string"}, "limit": {"type": "integer", "default": 50}},
          ["chat_id"]),
    _tool("ozon_chat_send",
          "Отправить сообщение в чат.",
          {"chat_id": {"type": "string"}, "text": {"type": "string"}},
          ["chat_id", "text"]),
    _tool("ozon_chat_send_file",
          "Отправить файл в чат.",
          {"chat_id": {"type": "string"}, "file_url": {"type": "string"}, "file_name": {"type": "string"}},
          ["chat_id", "file_url", "file_name"]),
    _tool("ozon_chat_updates",
          "Обновления чатов.",
          {"limit": {"type": "integer", "default": 50}}),
    _tool("ozon_chat_start",
          "Начать чат по отправлению.",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),
    _tool("ozon_chat_read",
          "Пометить чат как прочитанный.",
          {"chat_id": {"type": "string"}},
          ["chat_id"]),

    # === ОТМЕНЫ ===
    _tool("ozon_cancellation_list",
          "Заявки на отмену от покупателей.",
          {"posting_number": {"type": "string", "description": "Фильтр по номеру отправления (опц.)"},
           "status": {"type": "string", "default": "ON_APPROVAL", "description": "ON_APPROVAL, APPROVED, REJECTED"},
           "page": {"type": "integer", "default": 1},
           "page_size": {"type": "integer", "default": 50}}),
    _tool("ozon_cancellation_approve",
          "Одобрить заявку на отмену.",
          {"cancellation_id": {"type": "integer"}, "comment": {"type": "string"}},
          ["cancellation_id"]),
    _tool("ozon_cancellation_reject",
          "Отклонить заявку на отмену.",
          {"cancellation_id": {"type": "integer"}, "comment": {"type": "string"}},
          ["cancellation_id"]),

    # === СКЛАДЫ ===
    _tool("ozon_warehouse_list",
          "Список складов FBS продавца."),
    _tool("ozon_delivery_methods",
          "Методы доставки.",
          {"limit": {"type": "integer", "default": 50}}),

    # === ОТЧЁТЫ ===
    _tool("ozon_report_list",
          "Список сформированных отчётов.",
          {"report_type": {"type": "string"}, "page": {"type": "integer", "default": 1}}),
    _tool("ozon_report_info",
          "Статус и ссылка на отчёт.",
          {"code": {"type": "string"}},
          ["code"]),
    _tool("ozon_report_products_create",
          "Создать отчёт по товарам.",
          {"visibility": {"type": "string", "default": "ALL"}}),
    _tool("ozon_report_stocks_create",
          "Создать отчёт по остаткам."),
    _tool("ozon_report_finance_create",
          "Создать финансовый отчёт.",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("ozon_report_discounted_create",
          "Отчёт по уценённым товарам."),

    # === БРЕНДЫ ===
    _tool("ozon_brand_certificates",
          "Сертификаты бренда."),

    # === КАТЕГОРИИ ===
    _tool("ozon_category_tree",
          "Дерево категорий Ozon."),
    _tool("ozon_category_attributes",
          "Атрибуты категории.",
          {"description_category_id": {"type": "integer"}, "type_id": {"type": "integer", "default": 0}},
          ["description_category_id"]),
    _tool("ozon_category_attribute_values",
          "Значения атрибута категории.",
          {"description_category_id": {"type": "integer"}, "attribute_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["description_category_id", "attribute_id"]),
    _tool("ozon_category_attribute_search",
          "Поиск значений атрибута.",
          {"description_category_id": {"type": "integer"}, "attribute_id": {"type": "integer"}, "value": {"type": "string"}},
          ["description_category_id", "attribute_id", "value"]),

    # === УВЕДОМЛЕНИЯ ===
    _tool("ozon_notifications",
          "Список уведомлений.",
          {"limit": {"type": "integer", "default": 50}}),
    _tool("ozon_notification_read",
          "Пометить уведомления как прочитанные.",
          {"notification_ids": {"type": "array", "items": {"type": "string"}}},
          ["notification_ids"]),

    # === СКИДКИ ===
    _tool("ozon_discount_tasks",
          "Заявки покупателей 'Хочу скидку'.",
          {"limit": {"type": "integer", "default": 50}}),
    _tool("ozon_discount_approve",
          "Одобрить заявку на скидку.",
          {"task_id": {"type": "integer"}, "price": {"type": "number"}},
          ["task_id", "price"]),
    _tool("ozon_discount_decline",
          "Отклонить заявку на скидку.",
          {"task_id": {"type": "integer"}},
          ["task_id"]),

    # === КОМПАНИЯ ===
    _tool("ozon_company_info",
          "Информация о компании продавца."),
    _tool("ozon_company_tariffs",
          "Тарифы компании."),

    # === СЕРТИФИКАТЫ ===
    _tool("ozon_certificate_list",
          "Список всех сертификатов.",
          {"status": {"type": "string"}}),
    _tool("ozon_certificate_info",
          "Детали сертификата.",
          {"certificate_id": {"type": "integer"}},
          ["certificate_id"]),

    # === P2: АРХИВ ===
    _tool("ozon_product_archive",
          "[P2] Отправить товары в архив.",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === ДИАГНОСТИКА ===
    _tool("ozon_diagnostics",
          "[P0] ПОЛНАЯ САМОДИАГНОСТИКА: доступность хостов Ozon + лёгкие реальные запросы по 12 категориям Seller API + проверка ключей Performance API. Используй ПЕРВЫМ ДЕЛОМ если какой-то инструмент не работает — покажет, проблема в ключах, в конкретной категории API или в изменении API со стороны Ozon."),
    Tool(
        name="ozon_degradations",
        description="[P0] Деградации инструментов: какие MCP-инструменты раньше работали, а теперь стабильно падают (сигнал изменения Ozon API). Без параметров.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


# ─── Регистрация ──────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    start = time.monotonic()
    success = True
    error_text = None
    shop_id = arguments.get("shop_id", "")
    try:
        result = await _call_tool_impl(name, arguments)
        return result
    except Exception as e:
        success = False
        error_text = f"{type(e).__name__}: {e}"
        return [TextContent(type="text", text=f"Ошибка: {error_text}")]
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        if _stats_callback:
            try:
                await _stats_callback(name, duration_ms, success, error_text, shop_id)
            except Exception:
                pass


async def _call_tool_impl(name: str, arguments: dict) -> list[TextContent]:
    # Магазины (без shop_id)
    if name == "ozon_list_shops":
        from ozon_mcp.settings import get_shop_list
        return _json(get_shop_list(DATA_DIR))

    # Деградации (без shop_id)
    if name == "ozon_degradations":
        from ozon_mcp import stats
        degraded = await stats.get_tool_degradations()
        if not degraded:
            return _json({"status": "ok", "message": "Деградаций нет — все инструменты работают штатно"})
        return _json({"status": "degraded", "tools": degraded,
                      "hint": "Эти инструменты стабильно падают после периода успешной работы. Запусти ozon_diagnostics — возможно, Ozon изменил API."})

    shop_id = arguments.get("shop_id", "")
    if not shop_id:
        # Попробовать default
        from ozon_mcp.settings import load_shops
        shops = load_shops(DATA_DIR)
        if len(shops) == 1:
            shop_id = next(iter(shops))
        else:
            return [TextContent(type="text", text=f"Укажите shop_id. Доступные магазины: {list(shops.keys())}")]

    s = _get_seller(shop_id)

    # === ДИАГНОСТИКА ===
    if name == "ozon_diagnostics":
        from ozon_mcp import diagnostics as diag
        from ozon_mcp.settings import get_shop_keys
        keys = get_shop_keys(DATA_DIR, shop_id)
        return _json(await diag.full_diagnostics(shop_id, keys.get("name", shop_id), keys, s))

    # === АКЦИИ ===
    if name == "ozon_actions_list":
        return _json(await s.actions_list())
    if name == "ozon_actions_candidates":
        return _json(await s.actions_candidates(arguments["action_id"]))
    if name == "ozon_actions_products":
        return _json(await s.actions_products(arguments["action_id"]))
    if name == "ozon_actions_activate":
        return _json(await s.actions_products_activate(arguments["action_id"], arguments["products"]))

    # === ЦЕНОВЫЕ СТРАТЕГИИ ===
    if name == "ozon_pricing_strategy_list":
        return _json(await s.pricing_strategy_list(arguments["product_id"]))
    if name == "ozon_pricing_strategy_create":
        return _json(await s.pricing_strategy_create(arguments["strategy"]))
    if name == "ozon_pricing_strategy_update":
        return _json(await s.pricing_strategy_update(arguments["strategy"]))
    if name == "ozon_pricing_strategy_delete":
        return _json(await s.pricing_strategy_delete(arguments["strategy_id"]))
    if name == "ozon_pricing_currency_convert":
        return _json(await s.pricing_currency_convert(arguments["currency_from"], arguments["currency_to"], arguments["amount"]))
    if name == "ozon_pricing_competitor_prices":
        return _json(await s.pricing_competitor_prices(arguments["product_id"]))

    # === ЦЕНЫ ===
    if name == "ozon_set_prices":
        return _json(await s.product_import_prices(arguments["prices"]))
    if name == "ozon_get_prices":
        return _json(await s.product_info_prices(
            offer_id=arguments.get("offer_id"),
            product_id=arguments.get("product_id"),
            limit=arguments.get("limit", 100),
        ))
    if name == "ozon_get_prices_v4":
        return _json(await s.product_info_prices_v4(
            offer_id=arguments.get("offer_id"),
            limit=arguments.get("limit", 100),
        ))
    if name == "ozon_min_price_timer_status":
        return _json(await s.action_timer_status(arguments["product_id"]))
    if name == "ozon_min_price_timer_renew":
        return _json(await s.action_timer_update(arguments["product_id"]))

    # === ФИНАНСЫ ===
    if name == "ozon_finance_transactions":
        return _json(await s.finance_transaction_list(
            arguments["date_from"], arguments["date_to"],
            arguments.get("page", 1), arguments.get("page_size", 50),
            arguments.get("operation_type"),
        ))
    if name == "ozon_finance_totals":
        return _json(await s.finance_transaction_totals(arguments["date_from"], arguments["date_to"]))
    if name == "ozon_finance_realization":
        return _json(await s.finance_realization(arguments["date"]))
    if name == "ozon_finance_cash_flow":
        return _json(await s.finance_cash_flow(arguments["date_from"], arguments["date_to"]))

    # === РЕЙТИНГ ===
    if name == "ozon_rating_summary":
        return _json(await s.rating_summary())
    if name == "ozon_rating_history":
        return _json(await s.rating_history(arguments["date_from"], arguments["date_to"]))

    # === ОТЗЫВЫ ===
    if name == "ozon_reviews":
        return _json(await s.review_list(
            sku=arguments.get("sku"),
            limit=arguments.get("limit", 50),
        ))
    if name == "ozon_review_reply":
        return _json(await s.review_comment_create(arguments["review_id"], arguments["text"]))
    if name == "ozon_review_reply_update":
        return _json(await s.review_comment_update(arguments["review_id"], arguments["comment_id"], arguments["text"]))
    if name == "ozon_review_reply_delete":
        return _json(await s.review_comment_delete(arguments["review_id"], arguments["comment_id"]))

    # === РЕКЛАМА ===
    if name == "ozon_ad_campaigns":
        p = _get_perf(shop_id)
        return _json(await p.campaigns_list())
    if name == "ozon_ad_statistics":
        p = _get_perf(shop_id)
        return _json(await p.statistics(
            arguments["campaigns"], arguments["date_from"], arguments["date_to"],
            arguments.get("group_by", "DATE"),
        ))
    if name == "ozon_ad_campaign_stop":
        p = _get_perf(shop_id)
        return _json(await p.campaign_deactivate(arguments["campaign_id"]))
    if name == "ozon_ad_campaign_objects":
        p = _get_perf(shop_id)
        return _json(await p.campaign_objects(arguments["campaign_id"]))
    if name == "ozon_ad_campaign_create":
        p = _get_perf(shop_id)
        return _json(await p.campaign_create(arguments["title"], arguments["campaign_type"], arguments["products"], arguments.get("daily_budget", 0)))
    if name == "ozon_ad_campaign_activate":
        p = _get_perf(shop_id)
        return _json(await p.campaign_activate(arguments["campaign_id"]))
    if name == "ozon_ad_campaign_bids":
        p = _get_perf(shop_id)
        return _json(await p.campaign_update_bids(arguments["campaign_id"], arguments["bids"]))
    if name == "ozon_ad_campaign_budget":
        p = _get_perf(shop_id)
        return _json(await p.campaign_budget(arguments["campaign_id"]))
    if name == "ozon_ad_campaign_budget_update":
        p = _get_perf(shop_id)
        return _json(await p.campaign_update_budget(arguments["campaign_id"], arguments["daily_budget"], arguments.get("total_budget", 0)))
    if name == "ozon_ad_statistics_daily":
        p = _get_perf(shop_id)
        return _json(await p.statistics_daily(arguments["campaigns"], arguments["date_from"], arguments["date_to"]))
    if name == "ozon_ad_statistics_expenses":
        p = _get_perf(shop_id)
        return _json(await p.statistics_expenses(arguments["campaigns"], arguments["date_from"], arguments["date_to"]))
    if name == "ozon_ad_campaign_objects_update":
        p = _get_perf(shop_id)
        return _json(await p.campaign_objects_update(arguments["campaign_id"], arguments["objects"]))
    if name == "ozon_ad_balance":
        p = _get_perf(shop_id)
        return _json(await p.balance())

    # === АНАЛИТИКА ===
    if name == "ozon_analytics":
        return _json(await s.analytics_data(
            arguments["date_from"], arguments["date_to"],
            arguments["metrics"], arguments["dimensions"],
            limit=arguments.get("limit", 1000),
        ))
    if name == "ozon_stock_on_warehouses":
        return _json(await s.analytics_stock_on_warehouses(
            limit=arguments.get("limit", 100),
            offset=arguments.get("offset", 0),
        ))
    if name == "ozon_analytics_stocks":
        return _json(await s.analytics_stocks(arguments["skus"]))

    # === ТОВАРЫ ===
    if name == "ozon_product_list":
        return _json(await s.product_list(
            limit=arguments.get("limit", 100),
            visibility=arguments.get("visibility", "ALL"),
        ))
    if name == "ozon_product_info":
        return _json(await s.product_info_list(arguments["product_id"]))
    if name == "ozon_product_attributes":
        return _json(await s.product_info_attributes(
            offer_id=arguments.get("offer_id"),
            product_id=arguments.get("product_id"),
            limit=arguments.get("limit", 100),
        ))
    if name == "ozon_product_stocks":
        return _json(await s.product_info_stocks(
            offer_id=arguments.get("offer_id"),
            product_id=arguments.get("product_id"),
            limit=arguments.get("limit", 100),
        ))
    if name == "ozon_product_certificates":
        return _json(await s.product_certificate_list(arguments["product_id"]))

    # === ИМПОРТ И ОБНОВЛЕНИЕ ТОВАРОВ ===
    if name == "ozon_product_import":
        return _json(await s.product_import(arguments["items"]))
    if name == "ozon_product_import_info":
        return _json(await s.product_import_info(arguments["task_id"]))
    if name == "ozon_product_update_offer_id":
        return _json(await s.product_update_offer_id(arguments["update_offer_id"]))
    if name == "ozon_product_update_images":
        return _json(await s.product_update_images(arguments["product_id"], arguments["images"]))
    if name == "ozon_product_description":
        return _json(await s.product_info_description(arguments["offer_id"]))
    if name == "ozon_product_update_stocks":
        return _json(await s.product_update_stocks(arguments["stocks"]))
    if name == "ozon_product_geo_restrictions":
        return _json(await s.product_geo_restrictions_set(arguments["product_id"], arguments["restrictions"]))
    if name == "ozon_product_unarchive":
        return _json(await s.product_unarchive(arguments["product_id"]))
    if name == "ozon_product_delete":
        return _json(await s.product_delete(arguments["product_id"]))
    if name == "ozon_product_limits":
        return _json(await s.product_info_limit())
    if name == "ozon_product_rating_by_sku":
        return _json(await s.product_rating_by_sku(arguments["skus"]))
    if name == "ozon_product_discounted":
        return _json(await s.product_info_discounted(arguments["product_id"]))

    # === ЗАКАЗЫ FBS ===
    if name == "ozon_orders_fbs":
        return _json(await s.posting_fbs_list(
            arguments["since"], arguments["to"],
            limit=arguments.get("limit", 50),
            status=arguments.get("status", ""),
        ))
    if name == "ozon_order_fbs_get":
        return _json(await s.posting_fbs_get(arguments["posting_number"]))
    if name == "ozon_order_fbs_ship":
        return _json(await s.posting_fbs_ship(arguments["posting_number"], arguments["packages"]))
    if name == "ozon_order_fbs_cancel":
        return _json(await s.posting_fbs_cancel(arguments["posting_number"], arguments["cancel_reason_id"], arguments.get("cancel_reason_message", "")))
    if name == "ozon_order_fbs_cancel_reasons":
        return _json(await s.posting_fbs_cancel_reasons())
    if name == "ozon_order_fbs_act_create":
        return _json(await s.posting_fbs_act_create(arguments.get("containers_count", 1)))
    if name == "ozon_order_fbs_act_status":
        return _json(await s.posting_fbs_act_check_status(arguments["id"]))
    if name == "ozon_order_fbs_act_pdf":
        return _json(await s.posting_fbs_act_get_pdf(arguments["id"]))
    if name == "ozon_order_fbs_digital_act":
        return _json(await s.posting_fbs_digital_act_create(arguments["id"]))
    if name == "ozon_order_fbs_country_list":
        return _json(await s.posting_fbs_product_country_list(arguments["posting_number"]))
    if name == "ozon_order_fbs_country_set":
        return _json(await s.posting_fbs_product_country_set(arguments["posting_number"], arguments["product_id"], arguments["country_iso"]))
    if name == "ozon_order_fbs_restrictions":
        return _json(await s.posting_fbs_restrictions(arguments["posting_number"]))
    if name == "ozon_order_fbs_timeslot":
        return _json(await s.posting_fbs_timeslot_change(arguments["posting_number"], arguments["new_timeslot_id"]))
    if name == "ozon_order_fbo_get":
        return _json(await s.posting_fbo_get(arguments["posting_number"]))

    # === ЗАКАЗЫ FBO ===
    if name == "ozon_orders_fbo":
        return _json(await s.posting_fbo_list(
            arguments["since"], arguments["to"],
            limit=arguments.get("limit", 50),
        ))

    # === ВОЗВРАТЫ ===
    if name == "ozon_returns_fbo":
        return _json(await s.returns_fbo_list(arguments["filter"], limit=arguments.get("limit", 50)))
    if name == "ozon_returns_fbs":
        return _json(await s.returns_fbs_list(arguments["filter"], limit=arguments.get("limit", 50)))
    if name == "ozon_returns_fbs_approve":
        return _json(await s.returns_fbs_approve(arguments["return_id"]))
    if name == "ozon_returns_fbs_reject":
        return _json(await s.returns_fbs_reject(arguments["return_id"], arguments["reason"]))
    if name == "ozon_returns_fbs_get":
        return _json(await s.returns_fbs_get(arguments["return_id"]))
    if name == "ozon_returns_report":
        return _json(await s.report_returns_create(arguments["filter"]))

    # === ВОПРОСЫ ===
    if name == "ozon_questions":
        return _json(await s.question_list(limit=arguments.get("limit", 50), last_id=arguments.get("last_id", "")))
    if name == "ozon_question_reply":
        return _json(await s.question_reply(arguments["question_id"], arguments["text"]))

    # === ЧАТЫ ===
    if name == "ozon_chat_list":
        return _json(await s.chat_list(
            page_size=arguments.get("page_size", 100),
            unread_only=arguments.get("unread_only", False),
        ))
    if name == "ozon_chat_history":
        return _json(await s.chat_history(arguments["chat_id"], limit=arguments.get("limit", 50)))
    if name == "ozon_chat_send":
        return _json(await s.chat_send_message(arguments["chat_id"], arguments["text"]))
    if name == "ozon_chat_send_file":
        return _json(await s.chat_send_file(arguments["chat_id"], arguments["file_url"], arguments["file_name"]))
    if name == "ozon_chat_updates":
        return _json(await s.chat_updates(limit=arguments.get("limit", 50)))
    if name == "ozon_chat_start":
        return _json(await s.chat_start(arguments["posting_number"]))
    if name == "ozon_chat_read":
        return _json(await s.chat_read(arguments["chat_id"]))

    # === ОТМЕНЫ ===
    if name == "ozon_cancellation_list":
        return _json(await s.conditional_cancellation_list(
            posting_number=arguments.get("posting_number", ""),
            status=arguments.get("status", "ON_APPROVAL"),
            page=arguments.get("page", 1),
            page_size=arguments.get("page_size", 50),
        ))
    if name == "ozon_cancellation_approve":
        return _json(await s.conditional_cancellation_approve(arguments["cancellation_id"], arguments.get("comment", "")))
    if name == "ozon_cancellation_reject":
        return _json(await s.conditional_cancellation_reject(arguments["cancellation_id"], arguments.get("comment", "")))

    # === СКЛАДЫ ===
    if name == "ozon_warehouse_list":
        return _json(await s.warehouse_list())
    if name == "ozon_delivery_methods":
        return _json(await s.delivery_method_list(limit=arguments.get("limit", 50)))

    # === ОТЧЁТЫ ===
    if name == "ozon_report_list":
        return _json(await s.report_list(page=arguments.get("page", 1), report_type=arguments.get("report_type", "")))
    if name == "ozon_report_info":
        return _json(await s.report_info(arguments["code"]))
    if name == "ozon_report_products_create":
        return _json(await s.report_products_create(visibility=arguments.get("visibility", "ALL")))
    if name == "ozon_report_stocks_create":
        return _json(await s.report_stocks_create())
    if name == "ozon_report_finance_create":
        return _json(await s.report_finance_create(arguments["date_from"], arguments["date_to"]))
    if name == "ozon_report_discounted_create":
        return _json(await s.report_discounted_create())

    # === БРЕНДЫ ===
    if name == "ozon_brand_certificates":
        return _json(await s.brand_company_certification_list())

    # === КАТЕГОРИИ ===
    if name == "ozon_category_tree":
        return _json(await s.description_category_tree())
    if name == "ozon_category_attributes":
        return _json(await s.description_category_attribute(arguments["description_category_id"], arguments.get("type_id", 0)))
    if name == "ozon_category_attribute_values":
        return _json(await s.description_category_attribute_values(arguments["description_category_id"], arguments["attribute_id"], limit=arguments.get("limit", 100)))
    if name == "ozon_category_attribute_search":
        return _json(await s.description_category_attribute_values_search(arguments["description_category_id"], arguments["attribute_id"], arguments["value"]))

    # === УВЕДОМЛЕНИЯ ===
    if name == "ozon_notifications":
        return _json(await s.notification_list(limit=arguments.get("limit", 50)))
    if name == "ozon_notification_read":
        return _json(await s.notification_mark_read(arguments["notification_ids"]))

    # === СКИДКИ ===
    if name == "ozon_discount_tasks":
        return _json(await s.discount_task_list(limit=arguments.get("limit", 50)))
    if name == "ozon_discount_approve":
        return _json(await s.discount_task_approve(arguments["task_id"], arguments["price"]))
    if name == "ozon_discount_decline":
        return _json(await s.discount_task_decline(arguments["task_id"]))

    # === КОМПАНИЯ ===
    if name == "ozon_company_info":
        return _json(await s.company_info())
    if name == "ozon_company_tariffs":
        return _json(await s.company_tariffs())

    # === СЕРТИФИКАТЫ ===
    if name == "ozon_certificate_list":
        return _json(await s.certificate_list(status=arguments.get("status", "")))
    if name == "ozon_certificate_info":
        return _json(await s.certificate_info(arguments["certificate_id"]))

    # === АРХИВ ===
    if name == "ozon_product_archive":
        return _json(await s.product_archive(arguments["product_id"]))

    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


# ─── Точка входа ──────────────────────────────────────────

def main():
    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
