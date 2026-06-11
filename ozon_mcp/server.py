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
          "[P0] Добавить товары в акцию с указанной акционной ценой.",
          {"action_id": {"type": "integer"},
           "products": {"type": "array", "items": {"type": "object", "properties": {"product_id": {"type": "integer"}, "action_price": {"type": "number"}}}}},
          ["action_id", "products"]),
    _tool("ozon_actions_deactivate",
          "[P0] УБРАТЬ товары из акции. Используй для вывода убыточных товаров из акции.",
          {"action_id": {"type": "integer"},
           "product_ids": {"type": "array", "items": {"type": "integer"}}},
          ["action_id", "product_ids"]),

    # === СОБСТВЕННЫЕ АКЦИИ ПРОДАВЦА ===
    _tool("ozon_seller_actions",
          "[P1] Список СОБСТВЕННЫХ акций продавца (создаются продавцом, в отличие от акций Ozon).",
          {"status": {"type": "string", "description": "Фильтр по статусу (опц.)"},
           "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_seller_action_create",
          "[P1] Создать собственную акцию-скидку.",
          {"title": {"type": "string"}, "date_start": {"type": "string", "description": "RFC3339"},
           "date_end": {"type": "string"}, "min_action_percent": {"type": "integer", "description": "Мин. процент скидки"}},
          ["title", "date_start", "date_end", "min_action_percent"]),
    _tool("ozon_seller_action_toggle",
          "[P1] Включить/выключить собственную акцию.",
          {"action_id": {"type": "integer"}, "is_turn_on": {"type": "boolean"}},
          ["action_id", "is_turn_on"]),
    _tool("ozon_seller_action_products",
          "[P1] Товары собственной акции.",
          {"action_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["action_id"]),
    _tool("ozon_seller_action_products_add",
          "[P1] Добавить товары в собственную акцию.",
          {"action_id": {"type": "integer"},
           "products": {"type": "array", "items": {"type": "object"}, "description": "[{product_id, action_price}, ...]"}},
          ["action_id", "products"]),
    _tool("ozon_seller_action_products_delete",
          "[P1] Убрать товары из собственной акции.",
          {"action_id": {"type": "integer"}, "product_ids": {"type": "array", "items": {"type": "integer"}}},
          ["action_id", "product_ids"]),

    # === ЦЕНОВЫЕ СТРАТЕГИИ ===
    _tool("ozon_pricing_strategy_list",
          "[P1] Список ценовых стратегий (автоуправление ценами по конкурентам).",
          {"page": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_pricing_strategy_create",
          "[P1] Создать ценовую стратегию. competitors: [{competitor_id, coefficient}] (коэффициент 0.5-1.2 от цены конкурента).",
          {"name": {"type": "string"},
           "competitors": {"type": "array", "items": {"type": "object"}}},
          ["name", "competitors"]),
    _tool("ozon_pricing_strategy_info",
          "[P2] Детали ценовой стратегии.",
          {"strategy_id": {"type": "string"}},
          ["strategy_id"]),
    _tool("ozon_pricing_strategy_update",
          "[P1] Обновить ценовую стратегию.",
          {"strategy_id": {"type": "string"}, "name": {"type": "string"},
           "competitors": {"type": "array", "items": {"type": "object"}}},
          ["strategy_id", "name", "competitors"]),
    _tool("ozon_pricing_strategy_delete",
          "[P2] Удалить ценовую стратегию.",
          {"strategy_id": {"type": "string"}},
          ["strategy_id"]),
    _tool("ozon_pricing_strategy_status",
          "[P1] Включить/выключить ценовую стратегию.",
          {"strategy_id": {"type": "string"}, "enabled": {"type": "boolean"}},
          ["strategy_id", "enabled"]),
    _tool("ozon_pricing_strategy_products",
          "[P1] Товары стратегии: action=list | add | delete.",
          {"action": {"type": "string", "description": "list | add | delete"},
           "strategy_id": {"type": "string", "description": "Для list/add"},
           "product_ids": {"type": "array", "items": {"type": "integer"}, "description": "Для add/delete"}},
          ["action"]),
    _tool("ozon_pricing_competitors",
          "[P1] Список конкурентов (товары с других площадок) для ценовых стратегий.",
          {"page": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_pricing_competitor_prices",
          "[P1] Цена товара у конкурента (для товаров в стратегиях).",
          {"product_id": {"type": "integer"}},
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
          "[P1] Отчёт о реализации за месяц (v2).",
          {"month": {"type": "integer", "description": "1-12"}, "year": {"type": "integer"}},
          ["month", "year"]),
    _tool("ozon_finance_mutual_settlement",
          "[P1] Отчёт о взаиморасчётах за месяц.",
          {"date": {"type": "string", "description": "YYYY-MM"}},
          ["date"]),
    _tool("ozon_finance_accruals",
          "[P1] Начисления по дням.",
          {"date": {"type": "string", "description": "YYYY-MM-DD"}},
          ["date"]),
    _tool("ozon_finance_balance",
          "[P0] Баланс продавца за период: входящий/исходящий остаток, начисления, выплаты (Beta). Без дат — последние 30 дней.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD (опц.)"},
           "date_to": {"type": "string", "description": "YYYY-MM-DD (опц.)"}}),
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
    _tool("ozon_review_comments",
          "Комментарии к отзыву (метода «обновить ответ» в Ozon API нет — удалите и создайте заново).",
          {"review_id": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
          ["review_id"]),
    _tool("ozon_review_reply_delete",
          "Удалить ответ на отзыв.",
          {"review_id": {"type": "string"}, "comment_id": {"type": "string"}},
          ["review_id", "comment_id"]),

    # === P0: РЕКЛАМА ===
    _tool("ozon_ad_campaigns",
          "[P0] Список рекламных кампаний: бюджеты (микрорубли: 1000000=1₽), статусы. adv_object_type: SKU (трафареты) | SEARCH_PROMO (оплата за заказ) | BANNER. state: CAMPAIGN_STATE_RUNNING | _STOPPED | _INACTIVE.",
          {"campaign_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"},
           "adv_object_type": {"type": "string", "description": "Фильтр по типу (опц.)"},
           "state": {"type": "string", "description": "Фильтр по статусу (опц.)"}}),
    _tool("ozon_ad_statistics",
          "[P0] Статистика по кампаниям (асинхронный отчёт Ozon, ожидание до ~2 мин). ЛИМИТ: ≤10 кампаний, период ≤62 дня, 1 отчёт одновременно.",
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
          "[P1] Создать CPC-кампанию «Трафареты» (единственный тип, создаваемый через API). placement: PLACEMENT_SEARCH_AND_CATEGORY | PLACEMENT_TOP_PROMOTION. strategy: MAX_CLICKS | TOP_MAX_CLICKS | TARGET_BIDS | TOP_PROMOTION | NO_AUTO_STRATEGY. Мин. бюджет: 2000₽ × SKU. Товары добавляются отдельно через ozon_ad_products_add.",
          {"title": {"type": "string"},
           "placement": {"type": "string", "default": "PLACEMENT_SEARCH_AND_CATEGORY"},
           "strategy": {"type": "string", "default": "MAX_CLICKS"},
           "daily_budget_rub": {"type": "number", "description": "Дневной бюджет в рублях"},
           "weekly_budget_rub": {"type": "number", "description": "Недельный бюджет в рублях (опц.)"}},
          ["title"]),
    _tool("ozon_ad_campaign_activate",
          "Запустить рекламную кампанию.",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_bids",
          "[P0] Обновить ставки товаров в кампании. bids: [{sku, bid}] — ставка в МИКРОРУБЛЯХ строкой (10000000 = 10₽).",
          {"campaign_id": {"type": "integer"}, "bids": {"type": "array", "items": {"type": "object"}}},
          ["campaign_id", "bids"]),
    _tool("ozon_ad_campaign_budget",
          "[P1] Бюджет кампании (из списка кампаний; отдельного эндпоинта у Ozon нет).",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_budget_update",
          "[P1] Изменить бюджет/период кампании (PATCH). Бюджеты в РУБЛЯХ.",
          {"campaign_id": {"type": "integer"},
           "daily_budget_rub": {"type": "number"},
           "weekly_budget_rub": {"type": "number"},
           "from_date": {"type": "string", "description": "YYYY-MM-DD (опц.)"},
           "to_date": {"type": "string", "description": "YYYY-MM-DD (опц.)"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_products",
          "[P1] Товары и ставки в кампании.",
          {"campaign_id": {"type": "integer"}, "page": {"type": "integer", "default": 1}},
          ["campaign_id"]),
    _tool("ozon_ad_products_add",
          "[P1] Добавить товары в CPC-кампанию (≤500). bids: [{sku, bid}] в микрорублях; без bid — конкурентная ставка.",
          {"campaign_id": {"type": "integer"}, "bids": {"type": "array", "items": {"type": "object"}}},
          ["campaign_id", "bids"]),
    _tool("ozon_ad_products_delete",
          "[P1] Убрать товары из кампании.",
          {"campaign_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "integer"}}},
          ["campaign_id", "skus"]),
    _tool("ozon_ad_bids_competitive",
          "[P1] Конкурентные ставки по SKU в кампании (≤200).",
          {"campaign_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "integer"}}},
          ["campaign_id", "skus"]),
    _tool("ozon_ad_min_bids",
          "[P1] Минимальные ставки по SKU. payment_type: CPC | CPO | CPC_TOP.",
          {"skus": {"type": "array", "items": {"type": "integer"}},
           "payment_type": {"type": "string", "default": "CPC"}},
          ["skus"]),
    _tool("ozon_search_promo_products",
          "[P0] Товары в «Оплате за заказ» (вывод в топ, CPO): ставки %, видимость. КРИТИЧНО: ставки фиксированные с 02.2025.",
          {"page": {"type": "integer", "default": 1}}),
    _tool("ozon_search_promo_enable",
          "[P1] ВКЛЮЧИТЬ продвижение «Оплата за заказ» для товаров (≤1000 SKU).",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_search_promo_disable",
          "[P0] ОТКЛЮЧИТЬ продвижение «Оплата за заказ» (≤1000 SKU). Используй при высоком ДРР.",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_search_promo_bids",
          "[P1] Фиксированные ставки CPO по SKU (≤200).",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_ad_statistics_daily",
          "Ежедневная статистика рекламы.",
          {"campaigns": {"type": "array", "items": {"type": "integer"}}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_statistics_expenses",
          "Расходы по рекламным кампаниям.",
          {"campaigns": {"type": "array", "items": {"type": "integer"}}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_statistics_products",
          "[P0] Статистика CPC-кампаний по товарам: расход, CTR, CPC, заказы, ДРР (синхронно).",
          {"campaigns": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_balance",
          "Баланс рекламного кабинета (официального метода нет — см. расходы в ozon_ad_statistics_expenses)."),

    # === P1: АНАЛИТИКА ===
    _tool("ozon_analytics",
          "[P1] Аналитика по SKU. ВНИМАНИЕ: метрики воронки (session_view, hits_view, position_category) Ozon пометил deprecated — работают торговые: revenue, ordered_units, delivered_units, returns, cancellations. Для позиций в поиске — ozon_product_queries.",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "metrics": {"type": "array", "items": {"type": "string"}, "description": "revenue, ordered_units, delivered_units, returns, cancellations"},
           "dimensions": {"type": "array", "items": {"type": "string"}, "description": "sku, day, week, month"},
           "limit": {"type": "integer", "default": 1000}},
          ["date_from", "date_to", "metrics", "dimensions"]),
    _tool("ozon_stock_on_warehouses",
          "[P1] Остатки и оборачиваемость товаров на складах Ozon (через turnover/stocks — старый эндпоинт удалён Ozon).",
          {"limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}),
    _tool("ozon_analytics_stocks",
          "[P1] Аналитика по остаткам конкретных товаров: доступность, дефицитность, ликвидность (1-100 SKU).",
          {"skus": {"type": "array", "items": {"type": "integer"}, "description": "SKU товаров (1-100)"}},
          ["skus"]),
    _tool("ozon_product_queries",
          "[P0] Поисковые запросы и позиции моих товаров в поиске Ozon (Premium). КРИТИЧНО: видимость в поиске = продажи.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "skus": {"type": "array", "items": {"type": "integer"}},
           "details": {"type": "boolean", "default": False, "description": "true = детализация по запросам"}},
          ["date_from", "skus"]),
    _tool("ozon_search_queries_top",
          "[P1] Популярные поисковые запросы на Ozon (для SEO карточек).",
          {"limit": {"type": "integer", "default": 50}}),

    # === ПОСТАВКИ FBO ===
    _tool("ozon_supply_orders",
          "[P1] Заявки на поставку FBO (v3, возвращает order_ids — детали через ozon_supply_order_get).",
          {"states": {"type": "array", "items": {"type": "integer"}, "description": "Целочисленные коды статусов 1-8 (опц., по умолчанию все)"},
           "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_supply_order_get",
          "[P2] Детали заявок на поставку FBO (1-50).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}},
          ["order_ids"]),
    _tool("ozon_supply_order_counters",
          "[P2] Счётчики заявок на поставку по статусам."),
    _tool("ozon_supply_order_timeslots",
          "[P2] Доступные таймслоты для поставки FBO.",
          {"supply_order_id": {"type": "integer"}},
          ["supply_order_id"]),

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
          "Удалить товары без SKU из архива (по артикулам).",
          {"offer_ids": {"type": "array", "items": {"type": "string"}}},
          ["offer_ids"]),
    _tool("ozon_product_limits",
          "Лимиты на создание товаров."),
    _tool("ozon_product_rating_by_sku",
          "Рейтинг контента товаров.",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_product_discounted",
          "Информация об уценке по SKU уценённых товаров.",
          {"discounted_skus": {"type": "array", "items": {"type": "integer"}}},
          ["discounted_skus"]),
    _tool("ozon_product_attributes_update",
          "[P1] Обновить характеристики товаров (без полной перезаливки карточки).",
          {"items": {"type": "array", "items": {"type": "object"},
                     "description": "[{offer_id, attributes: [{id, values}]}]"}},
          ["items"]),
    _tool("ozon_product_import_by_sku",
          "[P2] Создать товар-копию по SKU существующего товара Ozon.",
          {"items": {"type": "array", "items": {"type": "object"},
                     "description": "[{sku, name, offer_id, price, old_price, vat, currency_code}]"}},
          ["items"]),
    _tool("ozon_product_stocks_by_warehouse",
          "[P1] Остатки товаров по складам FBS (v2; v1 отключается 07.04.2026).",
          {"skus": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"},
           "limit": {"type": "integer", "default": 100}}),

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
          "Собрать заказ FBS (v4). packages: [{products: [{product_id, quantity}]}].",
          {"posting_number": {"type": "string"}, "packages": {"type": "array", "items": {"type": "object"}}},
          ["posting_number", "packages"]),
    _tool("ozon_orders_fbs_unfulfilled",
          "[P1] Несобранные заказы FBS (ожидают сборки).",
          {"limit": {"type": "integer", "default": 100}}),
    _tool("ozon_order_fbs_label",
          "[P1] Этикетки отправлений FBS (PDF base64).",
          {"posting_numbers": {"type": "array", "items": {"type": "string"}}},
          ["posting_numbers"]),
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
          "Статус акта (цифровые акты удалены Ozon 22.03.2026 — используется обычный акт).",
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
          "[P1] ЕДИНЫЙ список возвратов FBO+FBS (/v1/returns/list; старые returns/company/* отключены Ozon).",
          {"filter": {"type": "object", "description": "Фильтр (опц.)"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_returns_fbs",
          "[P1] Заявки покупателей на возврат rFBS (требуют решения продавца!).",
          {"limit": {"type": "integer", "default": 100}}),
    _tool("ozon_returns_fbs_get",
          "[P1] Детали заявки на возврат rFBS.",
          {"return_id": {"type": "integer"}},
          ["return_id"]),
    _tool("ozon_returns_fbs_approve",
          "[P1] Одобрить заявку rFBS (verify — согласовать возврат).",
          {"return_id": {"type": "integer"}},
          ["return_id"]),
    _tool("ozon_returns_fbs_reject",
          "[P1] Отклонить заявку rFBS (комментарий обязателен).",
          {"return_id": {"type": "integer"}, "reason": {"type": "string"}},
          ["return_id", "reason"]),
    _tool("ozon_returns_rfbs_action",
          "[P1] Действие по заявке rFBS: receive-return (подтвердить получение товара), return-money (вернуть деньги), compensate (компенсация без возврата).",
          {"action": {"type": "string", "description": "receive-return | return-money | compensate"},
           "return_id": {"type": "integer"}, "comment": {"type": "string"}},
          ["action", "return_id"]),

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
          "Ответить на вопрос покупателя (нужен sku товара).",
          {"question_id": {"type": "string"}, "sku": {"type": "integer"}, "text": {"type": "string"}},
          ["question_id", "sku", "text"]),

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
          "[P1] Заявки покупателей на отмену (v2). state: ALL | ON_APPROVAL | APPROVED | REJECTED.",
          {"posting_number": {"type": "string", "description": "Фильтр (опц.)"},
           "state": {"type": "string", "default": "ON_APPROVAL"},
           "limit": {"type": "integer", "default": 100}}),
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
          "Подписки на push-уведомления (вебхуки). Старого «списка уведомлений» в Ozon API нет."),
    _tool("ozon_notification_push_types",
          "Справочник типов push-событий (новые сообщения, статусы отправлений и т.д.)."),

    # === СКИДКИ ===
    _tool("ozon_discount_tasks",
          "[P1] Заявки покупателей «Хочу скидку». status: NEW | SEEN | APPROVED | PARTLY_APPROVED | DECLINED | AUTO_DECLINED.",
          {"status": {"type": "string", "default": "NEW"},
           "limit": {"type": "integer", "default": 50, "description": "5/10/15/20/30/50"}}),
    _tool("ozon_discount_approve",
          "[P1] Одобрить заявки на скидку.",
          {"tasks": {"type": "array", "items": {"type": "object"},
                     "description": "[{id, approved_price, seller_comment, approved_quantity_min, approved_quantity_max}]"}},
          ["tasks"]),
    _tool("ozon_discount_decline",
          "[P1] Отклонить заявки на скидку.",
          {"tasks": {"type": "array", "items": {"type": "object"}, "description": "[{id, seller_comment}]"}},
          ["tasks"]),

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
        return _json(await s.actions_candidates(arguments["action_id"], limit=arguments.get("limit", 100)))
    if name == "ozon_actions_products":
        return _json(await s.actions_products(arguments["action_id"], limit=arguments.get("limit", 100)))
    if name == "ozon_actions_activate":
        return _json(await s.actions_products_activate(arguments["action_id"], arguments["products"]))
    if name == "ozon_actions_deactivate":
        return _json(await s.actions_products_deactivate(arguments["action_id"], arguments["product_ids"]))

    # === СОБСТВЕННЫЕ АКЦИИ ПРОДАВЦА ===
    if name == "ozon_seller_actions":
        return _json(await s.seller_actions_list(status=arguments.get("status"), limit=arguments.get("limit", 50)))
    if name == "ozon_seller_action_create":
        return _json(await s.seller_action_create_discount(
            arguments["title"], arguments["date_start"], arguments["date_end"],
            arguments["min_action_percent"]))
    if name == "ozon_seller_action_toggle":
        return _json(await s.seller_action_toggle(arguments["action_id"], arguments["is_turn_on"]))
    if name == "ozon_seller_action_products":
        return _json(await s.seller_action_products(arguments["action_id"], limit=arguments.get("limit", 100)))
    if name == "ozon_seller_action_products_add":
        return _json(await s.seller_action_products_add(arguments["action_id"], arguments["products"]))
    if name == "ozon_seller_action_products_delete":
        return _json(await s.seller_action_products_delete(arguments["action_id"], arguments["product_ids"]))

    # === ЦЕНОВЫЕ СТРАТЕГИИ ===
    if name == "ozon_pricing_strategy_list":
        return _json(await s.pricing_strategy_list(page=arguments.get("page", 1), limit=arguments.get("limit", 50)))
    if name == "ozon_pricing_strategy_create":
        return _json(await s.pricing_strategy_create(arguments["name"], arguments["competitors"]))
    if name == "ozon_pricing_strategy_info":
        return _json(await s.pricing_strategy_info(arguments["strategy_id"]))
    if name == "ozon_pricing_strategy_update":
        return _json(await s.pricing_strategy_update(arguments["strategy_id"], arguments["name"], arguments["competitors"]))
    if name == "ozon_pricing_strategy_delete":
        return _json(await s.pricing_strategy_delete(arguments["strategy_id"]))
    if name == "ozon_pricing_strategy_status":
        return _json(await s.pricing_strategy_status(arguments["strategy_id"], arguments["enabled"]))
    if name == "ozon_pricing_strategy_products":
        action = arguments["action"]
        if action == "add":
            return _json(await s.pricing_strategy_products_add(arguments["strategy_id"], arguments["product_ids"]))
        if action == "delete":
            return _json(await s.pricing_strategy_products_delete(arguments["product_ids"]))
        return _json(await s.pricing_strategy_products_list(arguments["strategy_id"]))
    if name == "ozon_pricing_competitors":
        return _json(await s.pricing_competitors_list(page=arguments.get("page", 1), limit=arguments.get("limit", 50)))
    if name == "ozon_pricing_competitor_prices":
        return _json(await s.pricing_competitor_price(arguments["product_id"]))

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
        return _json(await s.finance_realization(arguments["month"], arguments["year"]))
    if name == "ozon_finance_mutual_settlement":
        return _json(await s.finance_mutual_settlement(arguments["date"]))
    if name == "ozon_finance_accruals":
        return _json(await s.finance_accrual_by_day(arguments["date"]))
    if name == "ozon_finance_balance":
        return _json(await s.finance_balance(date_from=arguments.get("date_from", ""),
                                             date_to=arguments.get("date_to", "")))
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
    if name == "ozon_review_comments":
        return _json(await s.review_comment_list(arguments["review_id"], limit=arguments.get("limit", 20)))
    if name == "ozon_review_reply_delete":
        return _json(await s.review_comment_delete(arguments["review_id"], arguments["comment_id"]))

    # === РЕКЛАМА ===
    if name == "ozon_ad_campaigns":
        p = _get_perf(shop_id)
        return _json(await p.campaigns_list(
            campaign_ids=arguments.get("campaign_ids"),
            adv_object_type=arguments.get("adv_object_type"),
            state=arguments.get("state"),
        ))
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
        return _json(await p.campaign_create(
            arguments["title"],
            placement=arguments.get("placement", "PLACEMENT_SEARCH_AND_CATEGORY"),
            autopilot_strategy=arguments.get("strategy", "MAX_CLICKS"),
            daily_budget_rub=arguments.get("daily_budget_rub", 0),
            weekly_budget_rub=arguments.get("weekly_budget_rub", 0),
        ))
    if name == "ozon_ad_campaign_activate":
        p = _get_perf(shop_id)
        return _json(await p.campaign_activate(arguments["campaign_id"]))
    if name == "ozon_ad_campaign_bids":
        p = _get_perf(shop_id)
        return _json(await p.campaign_products_update(arguments["campaign_id"], arguments["bids"]))
    if name == "ozon_ad_campaign_budget":
        p = _get_perf(shop_id)
        return _json(await p.campaigns_list(campaign_ids=[arguments["campaign_id"]]))
    if name == "ozon_ad_campaign_budget_update":
        p = _get_perf(shop_id)
        return _json(await p.campaign_update(
            arguments["campaign_id"],
            daily_budget_rub=arguments.get("daily_budget_rub"),
            weekly_budget_rub=arguments.get("weekly_budget_rub"),
            from_date=arguments.get("from_date", ""),
            to_date=arguments.get("to_date", ""),
        ))
    if name == "ozon_ad_campaign_products":
        p = _get_perf(shop_id)
        return _json(await p.campaign_products_list(arguments["campaign_id"], page=arguments.get("page", 1)))
    if name == "ozon_ad_products_add":
        p = _get_perf(shop_id)
        return _json(await p.campaign_products_add(arguments["campaign_id"], arguments["bids"]))
    if name == "ozon_ad_products_delete":
        p = _get_perf(shop_id)
        return _json(await p.campaign_products_delete(arguments["campaign_id"], arguments["skus"]))
    if name == "ozon_ad_bids_competitive":
        p = _get_perf(shop_id)
        return _json(await p.bids_competitive(arguments["campaign_id"], arguments["skus"]))
    if name == "ozon_ad_min_bids":
        p = _get_perf(shop_id)
        return _json(await p.min_sku_bids(arguments["skus"], payment_type=arguments.get("payment_type", "CPC")))
    if name == "ozon_search_promo_products":
        p = _get_perf(shop_id)
        return _json(await p.search_promo_products(page=arguments.get("page", 1)))
    if name == "ozon_search_promo_enable":
        p = _get_perf(shop_id)
        return _json(await p.search_promo_enable(arguments["skus"]))
    if name == "ozon_search_promo_disable":
        p = _get_perf(shop_id)
        return _json(await p.search_promo_disable(arguments["skus"]))
    if name == "ozon_search_promo_bids":
        p = _get_perf(shop_id)
        return _json(await p.search_promo_cpo_bids(arguments["skus"]))
    if name == "ozon_ad_statistics_products":
        p = _get_perf(shop_id)
        return _json(await p.statistics_products(arguments["campaigns"], arguments["date_from"], arguments["date_to"]))
    if name == "ozon_ad_statistics_daily":
        p = _get_perf(shop_id)
        return _json(await p.statistics_daily(arguments["campaigns"], arguments["date_from"], arguments["date_to"]))
    if name == "ozon_ad_statistics_expenses":
        p = _get_perf(shop_id)
        return _json(await p.statistics_expenses(arguments["campaigns"], arguments["date_from"], arguments["date_to"]))
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
        return _json(await s.product_delete(arguments["offer_ids"]))
    if name == "ozon_product_attributes_update":
        return _json(await s.product_attributes_update(arguments["items"]))
    if name == "ozon_product_import_by_sku":
        return _json(await s.product_import_by_sku(arguments["items"]))
    if name == "ozon_product_stocks_by_warehouse":
        return _json(await s.product_stocks_by_warehouse(
            skus=arguments.get("skus"), limit=arguments.get("limit", 100)))
    if name == "ozon_product_limits":
        return _json(await s.product_info_limit())
    if name == "ozon_product_rating_by_sku":
        return _json(await s.product_rating_by_sku(arguments["skus"]))
    if name == "ozon_product_discounted":
        return _json(await s.product_info_discounted(arguments["discounted_skus"]))

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
    if name == "ozon_orders_fbs_unfulfilled":
        return _json(await s.posting_fbs_unfulfilled(limit=arguments.get("limit", 100)))
    if name == "ozon_order_fbs_label":
        return _json(await s.posting_fbs_package_label(arguments["posting_numbers"]))
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
        return _json(await s.returns_list(arguments.get("filter"), limit=arguments.get("limit", 100)))
    if name == "ozon_returns_fbs":
        return _json(await s.returns_rfbs_list(limit=arguments.get("limit", 100)))
    if name == "ozon_returns_fbs_approve":
        return _json(await s.returns_rfbs_action("verify", arguments["return_id"]))
    if name == "ozon_returns_fbs_reject":
        return _json(await s.returns_rfbs_action("reject", arguments["return_id"], comment=arguments["reason"]))
    if name == "ozon_returns_fbs_get":
        return _json(await s.returns_rfbs_get(arguments["return_id"]))
    if name == "ozon_returns_rfbs_action":
        return _json(await s.returns_rfbs_action(arguments["action"], arguments["return_id"],
                                                 comment=arguments.get("comment", "")))
    if name == "ozon_returns_report":
        return _json(await s.report_returns_create(arguments["filter"]))

    # === ВОПРОСЫ ===
    if name == "ozon_questions":
        return _json(await s.question_list(limit=arguments.get("limit", 50), last_id=arguments.get("last_id", "")))
    if name == "ozon_question_reply":
        return _json(await s.question_reply(arguments["question_id"], arguments["sku"], arguments["text"]))

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
            state=arguments.get("state", "ON_APPROVAL"),
            limit=arguments.get("limit", 100),
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
        return _json(await s.notification_list())
    if name == "ozon_notification_push_types":
        return _json(await s.notification_push_types())

    # === АНАЛИТИКА ПОИСКА И ПОСТАВКИ FBO ===
    if name == "ozon_product_queries":
        if arguments.get("details"):
            return _json(await s.product_queries_details(arguments["date_from"], arguments["skus"]))
        return _json(await s.product_queries(arguments["date_from"], arguments["skus"]))
    if name == "ozon_search_queries_top":
        return _json(await s.search_queries_top(limit=arguments.get("limit", 50)))
    if name == "ozon_supply_orders":
        return _json(await s.supply_orders_list(states=arguments.get("states"), limit=arguments.get("limit", 50)))
    if name == "ozon_supply_order_get":
        return _json(await s.supply_orders_get(arguments["order_ids"]))
    if name == "ozon_supply_order_counters":
        return _json(await s.supply_order_status_counter())
    if name == "ozon_supply_order_timeslots":
        return _json(await s.supply_order_timeslots(arguments["supply_order_id"]))

    # === СКИДКИ ===
    if name == "ozon_discount_tasks":
        return _json(await s.discount_task_list(
            status=arguments.get("status", "NEW"), limit=arguments.get("limit", 50)))
    if name == "ozon_discount_approve":
        return _json(await s.discount_task_approve(arguments["tasks"]))
    if name == "ozon_discount_decline":
        return _json(await s.discount_task_decline(arguments["tasks"]))

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
