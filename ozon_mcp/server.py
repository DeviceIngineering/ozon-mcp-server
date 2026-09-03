"""Ozon MCP Server — инструменты для управления бизнесом на Ozon.

Разделы: Магазины, Акции, Цены, Финансы, Рейтинг, Отзывы, Реклама, Аналитика, Товары,
Ценовые стратегии, Импорт товаров, Заказы FBS, Возвраты, Вопросы, Чаты, Отмены,
Склады, Отчёты, Бренды, Категории, Уведомления, Скидки, Компания, Сертификаты.

Поддержка нескольких магазинов через параметр shop_id: он передаётся явно,
а при единственном магазине подставляется сервером и в схемы не попадает.

v2.2.0 — оптимизация контекста: компактный JSON в ответах, сжатые описания
         инструментов, shop_id скрывается при единственном магазине
         (определения: 18 386 → 12 344 токенов).

v2.2.1 — default в JSON-схемах limit приведён к фактическому дефолту.

v2.3.0 — формирование ответа (ozon_mcp/shaping.py): пресеты view=compact|full,
         сигнал усечения, предохранитель размера, поиск и глубина в дереве
         категорий. Корпус живых ответов: 476 158 → 63 845 токенов.
"""

import contextvars
import json
import os
import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ozon_mcp import shaping
from ozon_mcp.client import OzonSellerClient, OzonPerformanceClient

# ─── Инициализация ────────────────────────────────────────

app = Server("ozon-mcp-server", version="2.3.0")

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


# Имя и аргументы текущего вызова: диспетчер Ozon — длинная if-цепочка со 150
# вызовами _json, прокидывать их параметром пришлось бы в каждую ветку.
_CALL_CONTEXT: contextvars.ContextVar[tuple[str, dict] | None] = contextvars.ContextVar(
    "ozon_call_context", default=None)


def _json(data: Any) -> list[TextContent]:
    """Ответ инструмента: данные плюс заметки о пресете, усечении и размере.

    Заметки идут отдельными блоками, а не полем внутри JSON: у части ручек Ozon
    верхний уровень ответа — массив, и обёртка сломала бы привычные пути к данным.
    """
    notes: list[str] = []
    context = _CALL_CONTEXT.get()
    if context is not None:
        name, arguments = context
        data, notes = shaping.shape(name, arguments, data)
    blocks = [TextContent(type="text", text=json.dumps(
        data, ensure_ascii=False, separators=(",", ":"), default=str))]
    blocks.extend(TextContent(type="text", text=note) for note in notes)
    return blocks


# Callback для записи статистики (устанавливается из app.py)
_stats_callback: Callable[..., Awaitable[None]] | None = None


def set_stats_callback(cb: Callable[..., Awaitable[None]]):
    global _stats_callback
    _stats_callback = cb


# ─── Общий фрагмент shop_id для inputSchema ─────────────────

SHOP_ID_PROP = {"type": "string"}


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> Tool:
    """Создать Tool с необязательным shop_id.

    shop_id не в required: при единственном магазине сервер подставляет его сам
    (см. _call_tool_impl), а при нескольких — возвращает список доступных.
    Пустой required в схему не пишется — это ~7 токенов на инструмент.
    """
    props = {"shop_id": SHOP_ID_PROP}
    if properties:
        props.update(properties)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = list(required)
    return Tool(name=name, description=description, inputSchema=schema)


# ─── Определение инструментов ─────────────────────────────

TOOLS = [
    # === МАГАЗИНЫ ===
    Tool(
        name="ozon_list_shops",
        description="Registered Ozon shops (магазины): shop_id + name. Use shop_id in all other tools.",
        inputSchema={"type": "object", "properties": {}},
    ),

    # === P0: АКЦИИ ===
    _tool("ozon_actions_list",
          "[P0] Ozon promotions available now and which goods may be pulled in (акции). Goods in promos can sell below cost."),
    _tool("ozon_actions_candidates",
          "[P0] Candidate goods Ozon PLANS to pull into a promotion; pre-emptive check against selling at a loss (кандидаты в акцию).",
          {"action_id": {"type": "integer", "description": "action id from ozon_actions_list"}},
          ["action_id"]),
    _tool("ozon_actions_products",
          "[P0] Goods already participating in a promotion, sold at the promo price (товары в акции).",
          {"action_id": {"type": "integer", "description": "action id"}},
          ["action_id"]),
    _tool("ozon_actions_activate",
          "[P0] Add goods to a promotion at a given promo price (вступить в акцию).",
          {"action_id": {"type": "integer"},
           "products": {"type": "array", "items": {"type": "object", "properties": {"product_id": {"type": "integer"}, "action_price": {"type": "number"}}}}},
          ["action_id", "products"]),
    _tool("ozon_actions_deactivate",
          "[P0] Remove goods from a promotion, e.g. loss-making ones (выйти из акции).",
          {"action_id": {"type": "integer"},
           "product_ids": {"type": "array", "items": {"type": "integer"}}},
          ["action_id", "product_ids"]),

    # === СОБСТВЕННЫЕ АКЦИИ ПРОДАВЦА ===
    _tool("ozon_seller_actions",
          "Seller's own promotions, as opposed to Ozon's (собственные акции).",
          {"status": {"type": "string", "description": "status filter"},
           "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_seller_action_create",
          "Create the seller's own discount promotion (создать акцию).",
          {"title": {"type": "string"}, "date_start": {"type": "string", "description": "RFC3339"},
           "date_end": {"type": "string"}, "min_action_percent": {"type": "integer", "description": "min discount %"}},
          ["title", "date_start", "date_end", "min_action_percent"]),
    _tool("ozon_seller_action_toggle",
          "Enable/disable the seller's own promotion (включить акцию).",
          {"action_id": {"type": "integer"}, "is_turn_on": {"type": "boolean"}},
          ["action_id", "is_turn_on"]),
    _tool("ozon_seller_action_products",
          "Goods in the seller's own promotion (товары акции).",
          {"action_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["action_id"]),
    _tool("ozon_seller_action_products_add",
          "Add goods to the seller's own promotion (добавить товары).",
          {"action_id": {"type": "integer"},
           "products": {"type": "array", "items": {"type": "object"}, "description": "[{product_id, action_price}, ...]"}},
          ["action_id", "products"]),
    _tool("ozon_seller_action_products_delete",
          "Remove goods from the seller's own promotion (убрать товары).",
          {"action_id": {"type": "integer"}, "product_ids": {"type": "array", "items": {"type": "integer"}}},
          ["action_id", "product_ids"]),

    # === ЦЕНОВЫЕ СТРАТЕГИИ ===
    _tool("ozon_pricing_strategy_list",
          "Pricing strategies: auto price management against competitors (ценовые стратегии).",
          {"page": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_pricing_strategy_create",
          "Create a pricing strategy. competitors: [{competitor_id, coefficient}], coefficient 0.5-1.2 of the competitor price (создать стратегию).",
          {"name": {"type": "string"},
           "competitors": {"type": "array", "items": {"type": "object"}}},
          ["name", "competitors"]),
    _tool("ozon_pricing_strategy_info",
          "Pricing strategy details (детали стратегии).",
          {"strategy_id": {"type": "string"}},
          ["strategy_id"]),
    _tool("ozon_pricing_strategy_update",
          "Update a pricing strategy (обновить стратегию).",
          {"strategy_id": {"type": "string"}, "name": {"type": "string"},
           "competitors": {"type": "array", "items": {"type": "object"}}},
          ["strategy_id", "name", "competitors"]),
    _tool("ozon_pricing_strategy_delete",
          "Delete a pricing strategy (удалить стратегию).",
          {"strategy_id": {"type": "string"}},
          ["strategy_id"]),
    _tool("ozon_pricing_strategy_status",
          "Enable/disable a pricing strategy (статус стратегии).",
          {"strategy_id": {"type": "string"}, "enabled": {"type": "boolean"}},
          ["strategy_id", "enabled"]),
    _tool("ozon_pricing_strategy_products",
          "Strategy goods: action=list | add | delete (товары стратегии).",
          {"action": {"type": "string", "description": "list | add | delete"},
           "strategy_id": {"type": "string", "description": "for list/add"},
           "product_ids": {"type": "array", "items": {"type": "integer"}, "description": "for add/delete"}},
          ["action"]),
    _tool("ozon_pricing_competitors",
          "Competitors from other marketplaces, input for pricing strategies (конкуренты).",
          {"page": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_pricing_competitor_prices",
          "Competitor price for goods in strategies (цены конкурентов).",
          {"product_id": {"type": "integer"}},
          ["product_id"]),

    # === P0: ЦЕНЫ ===
    _tool("ozon_set_prices",
          "[P0] Set prices. Use min_price to block promos below cost (установить цены).",
          {"prices": {"type": "array", "description": "[{offer_id, price, old_price, min_price, auto_action_enabled}]", "items": {"type": "object"}}},
          ["prices"]),
    _tool("ozon_get_prices",
          "[P0] Current prices, discounts, min price and price index. price_index over 1.15 risks quarantine (цены, индекс цен).",
          {"offer_id": {"type": "array", "items": {"type": "string"}, "description": "offer_id filter"},
           "product_id": {"type": "array", "items": {"type": "integer"}, "description": "product_id filter"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_get_prices_v4",
          "Prices via v4 API, includes purchase_price/cost (цены v4, себестоимость).",
          {"offer_id": {"type": "array", "items": {"type": "string"}, "description": "offer_id filter"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_min_price_timer_status",
          "[P0] Min price timer status, 30 days. Expired means goods are exposed to promos below cost (таймер минимальной цены).",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_min_price_timer_renew",
          "[P0] Renew the min price timer for 30 days (продлить таймер).",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === P0: ФИНАНСЫ ===
    _tool("ozon_finance_transactions",
          "[P0] Financial transactions: commissions, logistics, storage, returns — every cost per sale (транзакции, расходы).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DDT00:00:00Z"},
           "date_to": {"type": "string"},
           "page": {"type": "integer", "default": 1},
           "page_size": {"type": "integer", "default": 50},
           "operation_type": {"type": "array", "items": {"type": "string"}, "description": "type filter"}},
          ["date_from", "date_to"]),
    _tool("ozon_finance_totals",
          "[P0] Period totals: commissions, logistics, storage (итоги финансов).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("ozon_finance_realization",
          "Monthly realization report, v2 (отчёт о реализации).",
          {"month": {"type": "integer", "description": "1-12"}, "year": {"type": "integer"}},
          ["month", "year"]),
    _tool("ozon_finance_mutual_settlement",
          "Monthly mutual settlement report (взаиморасчёты).",
          {"date": {"type": "string", "description": "YYYY-MM"}},
          ["date"]),
    _tool("ozon_finance_accruals",
          "Daily accruals (начисления).",
          {"date": {"type": "string", "description": "YYYY-MM-DD"}},
          ["date"]),
    _tool("ozon_finance_balance",
          "[P0] Seller balance for a period: opening/closing, accruals, payouts (Beta). No dates = last 30 days (баланс).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "date_to": {"type": "string", "description": "YYYY-MM-DD"}}),
    _tool("ozon_finance_cash_flow",
          "Cash flow (движение средств).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P0: РЕЙТИНГ ===
    _tool("ozon_rating_summary",
          "[P0] Seller rating; drives search position, promo access and storage cost (рейтинг продавца)."),
    _tool("ozon_rating_history",
          "Seller rating history (история рейтинга).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P0: ОТЗЫВЫ ===
    _tool("ozon_reviews",
          "[P0] Product reviews; negatives cut conversion (отзывы).",
          {"sku": {"type": "array", "items": {"type": "integer"}, "description": "SKU filter"},
           "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_review_reply",
          "Reply to a review (ответить на отзыв).",
          {"review_id": {"type": "string"}, "text": {"type": "string"}},
          ["review_id", "text"]),
    _tool("ozon_review_comments",
          "Review comments. Ozon has no edit-reply method: delete and create again (комментарии к отзыву).",
          {"review_id": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
          ["review_id"]),
    _tool("ozon_review_reply_delete",
          "Delete a review reply (удалить ответ).",
          {"review_id": {"type": "string"}, "comment_id": {"type": "string"}},
          ["review_id", "comment_id"]),

    # === P0: РЕКЛАМА ===
    _tool("ozon_ad_campaigns",
          "[P0] Ad campaigns: budgets in micro-rubles (1000000 = 1₽), statuses. adv_object_type: SKU | SEARCH_PROMO | BANNER. state: CAMPAIGN_STATE_RUNNING | _STOPPED | _INACTIVE (реклама, кампании).",
          {"campaign_ids": {"type": "array", "items": {"type": "integer"}, "description": "filter"},
           "adv_object_type": {"type": "string", "description": "type filter"},
           "state": {"type": "string", "description": "status filter"}}),
    _tool("ozon_ad_statistics",
          "[P0] Campaign statistics, async Ozon report, up to ~2 min. Limits: ≤10 campaigns, ≤62 days, one report at a time (статистика рекламы).",
          {"campaigns": {"type": "array", "items": {"type": "integer"}, "description": "campaign ids"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "date_to": {"type": "string"},
           "group_by": {"type": "string", "default": "DATE"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_campaign_stop",
          "[P0] Emergency stop of an ad campaign (остановить рекламу).",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_objects",
          "Goods and bids inside an ad campaign (товары и ставки).",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_create",
          "Create a CPC Trafarety campaign, the only type creatable via API. placement: PLACEMENT_SEARCH_AND_CATEGORY | PLACEMENT_TOP_PROMOTION. strategy: MAX_CLICKS | TOP_MAX_CLICKS | TARGET_BIDS | TOP_PROMOTION | NO_AUTO_STRATEGY. Min budget 2000₽ per SKU; add goods via ozon_ad_products_add (создать кампанию).",
          {"title": {"type": "string"},
           "placement": {"type": "string", "default": "PLACEMENT_SEARCH_AND_CATEGORY"},
           "strategy": {"type": "string", "default": "MAX_CLICKS"},
           "daily_budget_rub": {"type": "number", "description": "daily budget, RUB"},
           "weekly_budget_rub": {"type": "number", "description": "weekly budget, RUB"}},
          ["title"]),
    _tool("ozon_ad_campaign_activate",
          "Start an ad campaign (запустить кампанию).",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_bids",
          "[P0] Update goods bids in a campaign. bids: [{sku, bid}], bid in MICRO-RUBLES as a string (10000000 = 10₽) (ставки).",
          {"campaign_id": {"type": "integer"}, "bids": {"type": "array", "items": {"type": "object"}}},
          ["campaign_id", "bids"]),
    _tool("ozon_ad_campaign_budget",
          "Campaign budget, taken from the campaign list; Ozon has no separate endpoint (бюджет кампании).",
          {"campaign_id": {"type": "integer"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_budget_update",
          "Change campaign budget or period (PATCH). Budgets in RUBLES (изменить бюджет).",
          {"campaign_id": {"type": "integer"},
           "daily_budget_rub": {"type": "number"},
           "weekly_budget_rub": {"type": "number"},
           "from_date": {"type": "string", "description": "YYYY-MM-DD"},
           "to_date": {"type": "string", "description": "YYYY-MM-DD"}},
          ["campaign_id"]),
    _tool("ozon_ad_campaign_products",
          "Goods and bids in a campaign (товары кампании).",
          {"campaign_id": {"type": "integer"}, "page": {"type": "integer", "default": 1}},
          ["campaign_id"]),
    _tool("ozon_ad_products_add",
          "Add goods to a CPC campaign, max 500. bids: [{sku, bid}] in micro-rubles; without bid the competitive bid applies (добавить товары).",
          {"campaign_id": {"type": "integer"}, "bids": {"type": "array", "items": {"type": "object"}}},
          ["campaign_id", "bids"]),
    _tool("ozon_ad_products_delete",
          "Remove goods from a campaign (убрать товары).",
          {"campaign_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "integer"}}},
          ["campaign_id", "skus"]),
    _tool("ozon_ad_bids_competitive",
          "Competitive bids by SKU in a campaign, max 200 (конкурентные ставки).",
          {"campaign_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "integer"}}},
          ["campaign_id", "skus"]),
    _tool("ozon_ad_min_bids",
          "Minimum bids by SKU. payment_type: CPC | CPO | CPC_TOP (минимальные ставки).",
          {"skus": {"type": "array", "items": {"type": "integer"}},
           "payment_type": {"type": "string", "default": "CPC"}},
          ["skus"]),
    _tool("ozon_search_promo_products",
          "[P0] Goods in pay-per-order top promotion (CPO): bid %, visibility. Bids fixed since 02.2025 (оплата за заказ).",
          {"page": {"type": "integer", "default": 1}}),
    _tool("ozon_search_promo_enable",
          "Enable pay-per-order promotion for goods, max 1000 SKU (включить продвижение).",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_search_promo_disable",
          "[P0] Disable pay-per-order promotion, max 1000 SKU; use when ДРР is high (отключить продвижение).",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_search_promo_bids",
          "Fixed CPO bids by SKU, max 200 (ставки CPO).",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_ad_statistics_daily",
          "Daily ad statistics (ежедневная статистика).",
          {"campaigns": {"type": "array", "items": {"type": "integer"}}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_statistics_expenses",
          "Ad campaign spend (расходы на рекламу).",
          {"campaigns": {"type": "array", "items": {"type": "integer"}}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_statistics_products",
          "[P0] CPC campaign stats per product: spend, CTR, CPC, orders, ДРР. Synchronous (статистика по товарам).",
          {"campaigns": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["campaigns", "date_from", "date_to"]),
    _tool("ozon_ad_balance",
          "Ad account balance; no official method, see spend in ozon_ad_statistics_expenses (баланс рекламы)."),

    # === P1: АНАЛИТИКА ===
    _tool("ozon_analytics",
          "Analytics by SKU. Funnel metrics (session_view, hits_view, position_category) are deprecated by Ozon; trade metrics work: revenue, ordered_units, delivered_units, returns, cancellations. For search positions use ozon_product_queries (аналитика).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "metrics": {"type": "array", "items": {"type": "string"}, "description": "revenue, ordered_units, delivered_units, returns, cancellations"},
           "dimensions": {"type": "array", "items": {"type": "string"}, "description": "sku, day, week, month"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from", "date_to", "metrics", "dimensions"]),
    _tool("ozon_stock_on_warehouses",
          "Stock and turnover at Ozon warehouses, via turnover/stocks — the old endpoint was removed (остатки на складах).",
          {"limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}),
    _tool("ozon_analytics_stocks",
          "Stock analytics for specific goods: availability, scarcity, liquidity, 1-100 SKU (аналитика остатков).",
          {"skus": {"type": "array", "items": {"type": "integer"}, "description": "SKUs, 1-100"}},
          ["skus"]),
    _tool("ozon_product_queries",
          "[P0] Search queries and positions of my goods in Ozon search (Premium). Visibility drives sales (поисковые запросы, позиции).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "skus": {"type": "array", "items": {"type": "integer"}},
           "details": {"type": "boolean", "default": False, "description": "true = per-query detail"}},
          ["date_from", "skus"]),
    _tool("ozon_search_queries_top",
          "Popular Ozon search queries, input for card SEO (топ запросов).",
          {"limit": {"type": "integer", "default": 50}}),

    # === ПОСТАВКИ FBO ===
    _tool("ozon_supply_orders",
          "FBO supply orders (v3), returns order_ids; details via ozon_supply_order_get (заявки на поставку).",
          {"states": {"type": "array", "items": {"type": "integer"}, "description": "status codes 1-8, default all"},
           "limit": {"type": "integer", "default": 50}}),
    _tool("ozon_supply_order_get",
          "FBO supply order details, 1-50 (детали поставки).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}},
          ["order_ids"]),
    _tool("ozon_supply_order_counters",
          "Supply order counters by status (счётчики поставок)."),
    _tool("ozon_supply_order_timeslots",
          "Available FBO supply timeslots (таймслоты).",
          {"supply_order_id": {"type": "integer"}},
          ["supply_order_id"]),

    # === P1: ТОВАРЫ ===
    _tool("ozon_product_list",
          "All goods. visibility: ALL, VISIBLE, QUARANTINE, ARCHIVED and others (список товаров).",
          {"visibility": {"type": "string", "default": "ALL", "description": "ALL, VISIBLE, QUARANTINE, ARCHIVED..."},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_product_info",
          "Extended product info (информация о товарах).",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_product_attributes",
          "Product attributes including BRAND (атрибуты, бренд).",
          {"offer_id": {"type": "array", "items": {"type": "string"}, "description": "offer_id filter"},
           "product_id": {"type": "array", "items": {"type": "integer"}, "description": "id filter"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_product_stocks",
          "Product stock at FBO/FBS warehouses (остатки товаров).",
          {"offer_id": {"type": "array", "items": {"type": "string"}},
           "product_id": {"type": "array", "items": {"type": "integer"}},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_product_certificates",
          "Product certificates; an expired one blocks the card (сертификаты).",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === ИМПОРТ И ОБНОВЛЕНИЕ ТОВАРОВ ===
    _tool("ozon_product_import",
          "Create/update goods, bulk import (импорт товаров).",
          {"items": {"type": "array", "items": {"type": "object"}, "description": "goods to import"}},
          ["items"]),
    _tool("ozon_product_import_info",
          "Product import task status (статус импорта).",
          {"task_id": {"type": "integer"}},
          ["task_id"]),
    _tool("ozon_product_update_offer_id",
          "Update product offer IDs (артикулы).",
          {"update_offer_id": {"type": "array", "items": {"type": "object"}}},
          ["update_offer_id"]),
    _tool("ozon_product_update_images",
          "Update product images (изображения).",
          {"product_id": {"type": "integer"}, "images": {"type": "array", "items": {"type": "string"}}},
          ["product_id", "images"]),
    _tool("ozon_product_description",
          "Product description by offer_id (описание товара).",
          {"offer_id": {"type": "string"}},
          ["offer_id"]),
    _tool("ozon_product_update_stocks",
          "Update FBS stock (обновить остатки).",
          {"stocks": {"type": "array", "items": {"type": "object"}, "description": "offer_id/product_id, stock, warehouse_id"}},
          ["stocks"]),
    _tool("ozon_product_geo_restrictions",
          "Set geo restrictions (гео-ограничения).",
          {"product_id": {"type": "integer"}, "restrictions": {"type": "array", "items": {"type": "object"}}},
          ["product_id", "restrictions"]),
    _tool("ozon_product_unarchive",
          "Restore goods from archive (вернуть из архива).",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),
    _tool("ozon_product_delete",
          "Delete goods without SKU from archive, by offer_id (удалить товары).",
          {"offer_ids": {"type": "array", "items": {"type": "string"}}},
          ["offer_ids"]),
    _tool("ozon_product_limits",
          "Product creation limits (лимиты товаров)."),
    _tool("ozon_product_rating_by_sku",
          "Content rating of goods (рейтинг контента).",
          {"skus": {"type": "array", "items": {"type": "integer"}}},
          ["skus"]),
    _tool("ozon_product_discounted",
          "Markdown info for discounted SKUs (уценённые товары).",
          {"discounted_skus": {"type": "array", "items": {"type": "integer"}}},
          ["discounted_skus"]),
    _tool("ozon_product_attributes_update",
          "Update product characteristics without a full card re-upload (обновить характеристики).",
          {"items": {"type": "array", "items": {"type": "object"},
                     "description": "[{offer_id, attributes: [{id, values}]}]"}},
          ["items"]),
    _tool("ozon_product_import_by_sku",
          "Create a copy product from an existing Ozon SKU (копия товара).",
          {"items": {"type": "array", "items": {"type": "object"},
                     "description": "[{sku, name, offer_id, price, old_price, vat, currency_code}]"}},
          ["items"]),
    _tool("ozon_product_stocks_by_warehouse",
          "FBS stock per warehouse (v2; v1 is switched off 2026-04-07) (остатки по складам).",
          {"skus": {"type": "array", "items": {"type": "integer"}, "description": "filter"},
           "limit": {"type": "integer", "default": 100}}),

    # === ЗАКАЗЫ FBS ===
    _tool("ozon_orders_fbs",
          "FBS orders with financial data. Cursor pagination: if has_next=true, repeat with cursor from the response (заказы FBS).",
          {"since": {"type": "string"}, "to": {"type": "string"}, "limit": {"type": "integer", "default": 50},
           "status": {"type": "string", "description": "awaiting_packaging, awaiting_deliver, delivering, etc."},
           "cursor": {"type": "string", "description": "next-page cursor from previous response"}},
          ["since", "to"]),
    _tool("ozon_order_fbs_get",
          "FBS posting details (детали отправления).",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),
    _tool("ozon_order_fbs_ship",
          "Assemble an FBS order (v4). packages: [{products: [{product_id, quantity}]}] (собрать заказ).",
          {"posting_number": {"type": "string"}, "packages": {"type": "array", "items": {"type": "object"}}},
          ["posting_number", "packages"]),
    _tool("ozon_orders_fbs_unfulfilled",
          "Unfulfilled FBS orders awaiting packaging: statuses awaiting_packaging and awaiting_deliver, last 30 days. Cursor pagination when has_next=true (несобранные заказы).",
          {"limit": {"type": "integer", "default": 100},
           "cursor": {"type": "string", "description": "next-page cursor from previous response"}}),
    _tool("ozon_order_fbs_label",
          "FBS posting labels, PDF base64 (этикетки).",
          {"posting_numbers": {"type": "array", "items": {"type": "string"}}},
          ["posting_numbers"]),
    _tool("ozon_order_fbs_cancel",
          "Cancel an FBS posting (отменить отправление).",
          {"posting_number": {"type": "string"}, "cancel_reason_id": {"type": "integer"}, "cancel_reason_message": {"type": "string"}},
          ["posting_number", "cancel_reason_id"]),
    _tool("ozon_order_fbs_cancel_reasons",
          "FBS cancellation reasons (причины отмены)."),
    _tool("ozon_order_fbs_act_create",
          "Create an FBS handover act (акт приёма-передачи).",
          {"containers_count": {"type": "integer", "default": 1}}),
    _tool("ozon_order_fbs_act_status",
          "Handover act generation status (статус акта).",
          {"id": {"type": "integer"}},
          ["id"]),
    _tool("ozon_order_fbs_act_pdf",
          "Download the handover act PDF (PDF акта).",
          {"id": {"type": "integer"}},
          ["id"]),
    _tool("ozon_order_fbs_digital_act",
          "Act status; digital acts were removed by Ozon 2026-03-22, the regular act is used (цифровой акт).",
          {"id": {"type": "integer"}},
          ["id"]),
    _tool("ozon_order_fbs_country_list",
          "Countries for an FBS posting (страны).",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),
    _tool("ozon_order_fbs_country_set",
          "Set the product country in a posting (указать страну).",
          {"posting_number": {"type": "string"}, "product_id": {"type": "integer"}, "country_iso": {"type": "string"}},
          ["posting_number", "product_id", "country_iso"]),
    _tool("ozon_order_fbs_restrictions",
          "FBS posting restrictions (ограничения отправлений).",
          {"posting_number": {"type": "array", "items": {"type": "string"}}},
          ["posting_number"]),
    _tool("ozon_order_fbs_timeslot",
          "Change the posting timeslot (тайм-слот).",
          {"posting_number": {"type": "string"}, "new_timeslot_id": {"type": "integer"}},
          ["posting_number", "new_timeslot_id"]),
    _tool("ozon_order_fbo_get",
          "FBO posting details (детали FBO).",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),

    # === P1: ЗАКАЗЫ FBO ===
    _tool("ozon_orders_fbo",
          "FBO orders (заказы FBO).",
          {"since": {"type": "string", "description": "YYYY-MM-DDT00:00:00Z"},
           "to": {"type": "string"},
           "limit": {"type": "integer", "default": 50}},
          ["since", "to"]),

    # === ВОЗВРАТЫ ===
    _tool("ozon_returns_fbo",
          "Unified FBO+FBS returns list (/v1/returns/list; old returns/company/* switched off) (возвраты).",
          {"filter": {"type": "object", "description": "filter"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_returns_fbs",
          "rFBS buyer return claims that need a seller decision (заявки на возврат).",
          {"limit": {"type": "integer", "default": 100}}),
    _tool("ozon_returns_fbs_get",
          "rFBS return claim details (детали заявки).",
          {"return_id": {"type": "integer"}},
          ["return_id"]),
    _tool("ozon_returns_fbs_approve",
          "Approve an rFBS claim (verify) (одобрить возврат).",
          {"return_id": {"type": "integer"}},
          ["return_id"]),
    _tool("ozon_returns_fbs_reject",
          "Reject an rFBS claim; comment required (отклонить возврат).",
          {"return_id": {"type": "integer"}, "reason": {"type": "string"}},
          ["return_id", "reason"]),
    _tool("ozon_returns_rfbs_action",
          "rFBS claim action: receive-return (confirm goods received), return-money (refund), compensate (compensation without return) (действие по возврату).",
          {"action": {"type": "string", "description": "receive-return | return-money | compensate"},
           "return_id": {"type": "integer"}, "comment": {"type": "string"}},
          ["action", "return_id"]),

    # === P1: ВОЗВРАТЫ (LEGACY) ===
    _tool("ozon_returns_report",
          "Create a returns report (отчёт по возвратам).",
          {"filter": {"type": "object", "description": "date_from, date_to etc."}},
          ["filter"]),

    # === ВОПРОСЫ ===
    _tool("ozon_questions",
          "Buyer questions (вопросы покупателей).",
          {"limit": {"type": "integer", "default": 50}, "last_id": {"type": "string"}}),
    _tool("ozon_question_reply",
          "Reply to a buyer question; needs the product sku (ответить на вопрос).",
          {"question_id": {"type": "string"}, "sku": {"type": "integer"}, "text": {"type": "string"}},
          ["question_id", "sku", "text"]),

    # === ЧАТЫ ===
    _tool("ozon_chat_list",
          "Buyer chats (v3). unread_only=true for unread ones (чаты).",
          {"unread_only": {"type": "boolean", "default": False},
           "page_size": {"type": "integer", "default": 100}}),
    _tool("ozon_chat_history",
          "Chat message history (история чата).",
          {"chat_id": {"type": "string"}, "limit": {"type": "integer", "default": 50}},
          ["chat_id"]),
    _tool("ozon_chat_send",
          "Send a chat message (написать в чат).",
          {"chat_id": {"type": "string"}, "text": {"type": "string"}},
          ["chat_id", "text"]),
    _tool("ozon_chat_send_file",
          "Send a file to a chat (отправить файл).",
          {"chat_id": {"type": "string"}, "file_url": {"type": "string"}, "file_name": {"type": "string"}},
          ["chat_id", "file_url", "file_name"]),
    _tool("ozon_chat_updates",
          "Chat updates (обновления чатов).",
          {"limit": {"type": "integer", "default": 50}}),
    _tool("ozon_chat_start",
          "Start a chat about a posting (начать чат).",
          {"posting_number": {"type": "string"}},
          ["posting_number"]),
    _tool("ozon_chat_read",
          "Mark a chat as read (пометить прочитанным).",
          {"chat_id": {"type": "string"}},
          ["chat_id"]),

    # === ОТМЕНЫ ===
    _tool("ozon_cancellation_list",
          "Buyer cancellation claims (v2). state: ALL | ON_APPROVAL | APPROVED | REJECTED (заявки на отмену).",
          {"posting_number": {"type": "string", "description": "filter"},
           "state": {"type": "string", "default": "ON_APPROVAL"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("ozon_cancellation_approve",
          "Approve a cancellation claim (одобрить отмену).",
          {"cancellation_id": {"type": "integer"}, "comment": {"type": "string"}},
          ["cancellation_id"]),
    _tool("ozon_cancellation_reject",
          "Reject a cancellation claim (отклонить отмену).",
          {"cancellation_id": {"type": "integer"}, "comment": {"type": "string"}},
          ["cancellation_id"]),

    # === СКЛАДЫ ===
    _tool("ozon_warehouse_list",
          "Seller FBS warehouses (склады)."),
    _tool("ozon_delivery_methods",
          "Delivery methods (методы доставки).",
          {"limit": {"type": "integer", "default": 50}}),

    # === ОТЧЁТЫ ===
    _tool("ozon_report_list",
          "Generated reports (список отчётов).",
          {"report_type": {"type": "string"}, "page": {"type": "integer", "default": 1}}),
    _tool("ozon_report_info",
          "Report status and download link (статус отчёта).",
          {"code": {"type": "string"}},
          ["code"]),
    _tool("ozon_report_products_create",
          "Create a products report (отчёт по товарам).",
          {"visibility": {"type": "string", "default": "ALL"}}),
    _tool("ozon_report_stocks_create",
          "Create a stock report (отчёт по остаткам)."),
    _tool("ozon_report_finance_create",
          "Create a financial report (финансовый отчёт).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("ozon_report_discounted_create",
          "Report on discounted goods (отчёт по уценке)."),

    # === БРЕНДЫ ===
    _tool("ozon_brand_certificates",
          "Brand certificates (сертификаты бренда)."),

    # === КАТЕГОРИИ ===
    _tool("ozon_category_tree",
          "Ozon category tree (дерево категорий). Whole tree is 9 800 nodes: pass search "
          "to find a category, or depth to go deeper than top level.",
          {"search": {"type": "string",
                      "description": "category name substring, case-insensitive (название категории)"},
           "depth": {"type": "integer", "default": 1,
                     "description": "1 = top level only, 3 = whole tree"}}),
    _tool("ozon_category_attributes",
          "Category attributes (атрибуты категории).",
          {"description_category_id": {"type": "integer"}, "type_id": {"type": "integer", "default": 0}},
          ["description_category_id"]),
    _tool("ozon_category_attribute_values",
          "Category attribute values (значения атрибута).",
          {"description_category_id": {"type": "integer"}, "attribute_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["description_category_id", "attribute_id"]),
    _tool("ozon_category_attribute_search",
          "Search attribute values (поиск значений).",
          {"description_category_id": {"type": "integer"}, "attribute_id": {"type": "integer"}, "value": {"type": "string"}},
          ["description_category_id", "attribute_id", "value"]),

    # === УВЕДОМЛЕНИЯ ===
    _tool("ozon_notifications",
          "Push notification subscriptions (webhooks). Ozon has no notification list endpoint (уведомления, вебхуки)."),
    _tool("ozon_notification_push_types",
          "Push event types reference: new messages, posting statuses (типы событий)."),

    # === СКИДКИ ===
    _tool("ozon_discount_tasks",
          "Buyer 'want a discount' requests. status: NEW | SEEN | APPROVED | PARTLY_APPROVED | DECLINED | AUTO_DECLINED (заявки на скидку).",
          {"status": {"type": "string", "default": "NEW"},
           "limit": {"type": "integer", "default": 50, "description": "5/10/15/20/30/50"}}),
    _tool("ozon_discount_approve",
          "Approve discount requests (одобрить скидку).",
          {"tasks": {"type": "array", "items": {"type": "object"},
                     "description": "[{id, approved_price, seller_comment, approved_quantity_min, approved_quantity_max}]"}},
          ["tasks"]),
    _tool("ozon_discount_decline",
          "Decline discount requests (отклонить скидку).",
          {"tasks": {"type": "array", "items": {"type": "object"}, "description": "[{id, seller_comment}]"}},
          ["tasks"]),

    # === КОМПАНИЯ ===
    _tool("ozon_company_info",
          "Seller company info (информация о компании)."),
    _tool("ozon_company_tariffs",
          "Company tariffs (тарифы)."),

    # === СЕРТИФИКАТЫ ===
    _tool("ozon_certificate_list",
          "All certificates (сертификаты).",
          {"status": {"type": "string"}}),
    _tool("ozon_certificate_info",
          "Certificate details (детали сертификата).",
          {"certificate_id": {"type": "integer"}},
          ["certificate_id"]),

    # === P2: АРХИВ ===
    _tool("ozon_product_archive",
          "Move goods to archive (архивировать товары).",
          {"product_id": {"type": "array", "items": {"type": "integer"}}},
          ["product_id"]),

    # === ДИАГНОСТИКА ===
    _tool("ozon_diagnostics",
          "[P0] Full self-diagnostics: Ozon host availability, light real requests across 12 Seller API categories, Performance API key check. Run FIRST when a tool misbehaves — separates a key problem from a category or Ozon API change (диагностика)."),
    Tool(
        name="ozon_degradations",
        description="[P0] Tool degradations: which MCP tools used to work and now fail steadily, signalling an Ozon API change. No parameters (деградации).",
        inputSchema={"type": "object", "properties": {}},
    ),
]


# ─── Регистрация ──────────────────────────────────────────
#
# TODO(mcp 2.x): декораторного low-level API (@app.list_tools / @app.call_tool)
# в mcp>=2.0.0 больше нет — обработчики передаются в Server(...) как
# on_list_tools / on_call_tool и возвращают ListToolsResult / CallToolResult.
# Пока зависимость закреплена как mcp[cli]<2 (см. pyproject.toml); переход на 2.x
# — отдельная задача, вместе с миграцией с устаревшего SSE-транспорта на
# Streamable HTTP.

def _visible_tools() -> list[Tool]:
    """Инструменты для list_tools.

    При одном магазине shop_id убирается из схем: сервер подставит его сам
    (см. _call_tool_impl), а 149 повторов параметра стоят ~2500 токенов
    контекста в каждой сессии. Как только магазинов становится больше одного,
    параметр возвращается в схемы.
    """
    try:
        from ozon_mcp.settings import load_shops
        if len(load_shops(DATA_DIR)) > 1:
            return TOOLS
    except Exception:
        return TOOLS

    visible: list[Tool] = []
    for t in TOOLS:
        props = t.inputSchema.get("properties") or {}
        if "shop_id" not in props:
            visible.append(t)
            continue
        schema = dict(t.inputSchema)
        schema["properties"] = {k: v for k, v in props.items() if k != "shop_id"}
        visible.append(Tool(name=t.name, description=t.description, inputSchema=schema))
    return visible


@app.list_tools()
async def list_tools() -> list[Tool]:
    return _visible_tools()


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    start = time.monotonic()
    success = True
    error_text = None
    shop_id = arguments.get("shop_id", "")
    token = _CALL_CONTEXT.set((name, arguments))
    try:
        result = await _call_tool_impl(name, arguments)
        return result
    except Exception as e:
        success = False
        error_text = f"{type(e).__name__}: {e}"
        return [TextContent(type="text", text=f"Ошибка: {error_text}")]
    finally:
        _CALL_CONTEXT.reset(token)
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
        if not stats.is_enabled():
            return _json({"status": "no_data",
                          "message": "Статистика вызовов не собирается — судить о деградациях не по чему",
                          "hint": f"Каталог DATA_DIR ({DATA_DIR}) недоступен на запись. "
                                  f"Задай DATA_DIR в переменных окружения MCP-клиента."})
        degraded = await stats.get_tool_degradations()
        if not degraded:
            total = (await stats.get_summary())["total"]
            if total == 0:
                return _json({"status": "no_data",
                              "message": "Статистика пуста — записанных вызовов ещё нет, "
                                         "судить о деградациях не по чему"})
            return _json({"status": "ok",
                          "message": f"Деградаций нет — все инструменты работают штатно "
                                     f"(учтено вызовов: {total})"})
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
            limit=arguments.get("limit", 100),
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
            cursor=arguments.get("cursor", ""),
        ))
    if name == "ozon_order_fbs_get":
        return _json(await s.posting_fbs_get(arguments["posting_number"]))
    if name == "ozon_order_fbs_ship":
        return _json(await s.posting_fbs_ship(arguments["posting_number"], arguments["packages"]))
    if name == "ozon_orders_fbs_unfulfilled":
        return _json(await s.posting_fbs_unfulfilled(
            limit=arguments.get("limit", 100),
            cursor=arguments.get("cursor", ""),
        ))
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
        return _json(_trim_category_tree(
            await s.description_category_tree(),
            (arguments.get("search") or "").strip().lower(),
            int(arguments.get("depth") or 1)))
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


def _trim_category_tree(data: Any, search: str, depth: int) -> Any:
    """Ozon отдаёт дерево целиком — 9 800 узлов, 266 000 токенов.

    Поиск и глубина применяются на сервере: у API таких параметров нет, а без них
    инструмент в 10 раз превышает потолок вывода клиента.
    """
    roots = data.get("result") if isinstance(data, dict) else None
    if not isinstance(roots, list):
        return data

    def cut(nodes: list, level: int) -> list:
        out = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = node.get("children") or []
            trimmed = dict(node)
            trimmed["children"] = cut(children, level - 1) if level > 1 else []
            if level <= 1 and children:
                trimmed["hasChildren"] = True
            out.append(trimmed)
        return out

    def matching(nodes: list) -> list:
        out = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = matching(node.get("children") or [])
            hit = search in str(node.get("category_name", "")).lower()
            if hit or children:
                out.append({**node, "children": children})
        return out

    if search:
        found = matching(roots)
        return {**data, "result": found, "filteredBy": search}
    return {**data, "result": cut(roots, max(1, depth)),
            "hint": 'верхний уровень; глубже — depth=2..3 или search="название"'}


# Инструментам с compact-пресетом добавляется переключатель view.
for _tool_with_view in TOOLS:
    if _tool_with_view.name in shaping.VIEWS:
        _tool_with_view.inputSchema.setdefault("properties", {})["view"] = dict(shaping.VIEW_PROP)


# ─── Точка входа ──────────────────────────────────────────

async def _init_stats() -> bool:
    """Поднять сбор статистики для stdio-режима.

    В web-режиме это делает lifespan в app.py. В stdio до сих пор не делал никто,
    поэтому _stats_callback оставался None, вызовы никуда не писались, а
    ozon_degradations всегда отвечал «деградаций нет».

    Каталог DATA_DIR может быть недоступен на запись (по умолчанию это /data,
    а stdio обычно запускают на машине пользователя) — тогда сервер продолжает
    работать без статистики, а ozon_degradations честно отвечает no_data.
    """
    from ozon_mcp import stats

    try:
        await stats.init_db(DATA_DIR)
    except Exception:
        return False
    set_stats_callback(stats.record_call)
    return True


def main():
    async def _run():
        stats_on = await _init_stats()
        try:
            async with stdio_server() as (read_stream, write_stream):
                await app.run(read_stream, write_stream, app.create_initialization_options())
        finally:
            if stats_on:
                from ozon_mcp import stats
                await stats.close_db()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
