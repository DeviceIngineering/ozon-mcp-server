"""HTTP-клиенты для Ozon Seller API и Performance API."""

import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Any

SELLER_BASE = "https://api-seller.ozon.ru"
PERF_BASE = "https://api-performance.ozon.ru"


class OzonSellerClient:
    """Клиент для Ozon Seller API (товары, цены, акции, финансы, аналитика)."""

    def __init__(self, client_id: str, api_key: str):
        self.client_id = client_id
        self.api_key = api_key
        self._http = httpx.AsyncClient(
            base_url=SELLER_BASE,
            headers={"Client-Id": client_id, "Api-Key": api_key},
            timeout=30.0,
        )
        # Справочник видов начислений статичен — грузим один раз на клиента.
        self._accrual_types_cache: dict | None = None

    # 429 и 5xx — повторяем: с переездом финансов на начисления один вызов
    # инструмента превратился в десятки запросов по дням, и лимит Ozon стал
    # достижимым в обычной работе, а не только при нагрузке.
    _RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    async def _send(self, method: str, path: str, *, params: dict | None = None,
                    json_body: Any = None, max_retries: int = 3) -> dict:
        delay = 1.0
        for attempt in range(max_retries + 1):
            r = await self._http.request(method, path, params=params, json=json_body)
            if r.status_code in self._RETRY_STATUSES and attempt < max_retries:
                retry_after = r.headers.get("Retry-After", "")
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                await asyncio.sleep(min(wait, 10.0))
                delay = min(delay * 2, 10.0)
                continue
            r.raise_for_status()
            return r.json() if r.content else {}
        return {}

    async def _post(self, path: str, body: dict | None = None) -> dict:
        return await self._send("POST", path, json_body=body or {})

    async def _get(self, path: str, params: dict | None = None) -> dict:
        return await self._send("GET", path, params=params)

    # ── Акции ──────────────────────────────────────────────
    async def actions_list(self) -> dict:
        """GET /v1/actions — список доступных акций."""
        return await self._get("/v1/actions")

    async def actions_candidates(self, action_id: int, limit: int = 100, last_id: str = "") -> dict:
        """POST /v1/actions/candidates — товары-кандидаты в акцию."""
        body = {"action_id": action_id, "limit": limit}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v1/actions/candidates", body)

    async def actions_products(self, action_id: int, limit: int = 100, last_id: str = "") -> dict:
        """POST /v1/actions/products — товары уже в акции."""
        body = {"action_id": action_id, "limit": limit}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v1/actions/products", body)

    async def actions_products_activate(
        self, action_id: int, products: list[dict]
    ) -> dict:
        """POST /v1/actions/products/activate — добавить товары в акцию."""
        return await self._post(
            "/v1/actions/products/activate",
            {"action_id": action_id, "products": products},
        )

    async def actions_products_deactivate(self, action_id: int, product_ids: list[int]) -> dict:
        """POST /v1/actions/products/deactivate — убрать товары из акции."""
        return await self._post(
            "/v1/actions/products/deactivate",
            {"action_id": action_id, "product_ids": product_ids},
        )

    # ── Собственные акции продавца (/v1/seller-actions/*) ──
    async def seller_actions_list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        """POST /v1/seller-actions/list — список собственных акций продавца."""
        body: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            body["status"] = status
        return await self._post("/v1/seller-actions/list", body)

    async def seller_action_create_discount(self, title: str, date_start: str, date_end: str,
                                            min_action_percent: int) -> dict:
        """POST /v1/seller-actions/create/discount — создать собственную акцию-скидку."""
        return await self._post("/v1/seller-actions/create/discount", {
            "title": title, "date_start": date_start, "date_end": date_end,
            "min_action_percent": min_action_percent,
        })

    async def seller_action_toggle(self, action_id: int, is_turn_on: bool) -> dict:
        """POST /v1/seller-actions/change-activity — включить/выключить собственную акцию."""
        return await self._post("/v1/seller-actions/change-activity",
                                {"action_id": action_id, "is_turn_on": is_turn_on})

    async def seller_action_products(self, action_id: int, limit: int = 100, cursor: str = "") -> dict:
        """POST /v1/seller-actions/products/list — товары собственной акции."""
        body: dict[str, Any] = {"action_id": action_id, "limit": limit}
        if cursor:
            body["cursor"] = cursor
        return await self._post("/v1/seller-actions/products/list", body)

    async def seller_action_products_add(self, action_id: int, products: list[dict]) -> dict:
        """POST /v1/seller-actions/products/add — добавить товары в собственную акцию."""
        return await self._post("/v1/seller-actions/products/add",
                                {"action_id": action_id, "products": products})

    async def seller_action_products_delete(self, action_id: int, product_ids: list[int]) -> dict:
        """POST /v1/seller-actions/products/delete — убрать товары из собственной акции."""
        return await self._post("/v1/seller-actions/products/delete",
                                {"action_id": action_id, "product_ids": product_ids})

    # ── Ценовые стратегии (/v1/pricing-strategy/*) ─────────
    async def pricing_strategy_list(self, page: int = 1, limit: int = 25) -> dict:
        """POST /v1/pricing-strategy/list — список ценовых стратегий (limit строго < 50)."""
        return await self._post("/v1/pricing-strategy/list", {"page": page, "limit": min(limit, 49)})

    async def pricing_strategy_create(self, name: str, competitors: list[dict]) -> dict:
        """POST /v1/pricing-strategy/create — создать стратегию.

        competitors: [{"competitor_id": 123, "coefficient": 1.0}] (0.5-1.2).
        """
        return await self._post("/v1/pricing-strategy/create",
                                {"strategy_name": name, "competitors": competitors})

    async def pricing_strategy_info(self, strategy_id: str) -> dict:
        """POST /v1/pricing-strategy/info — детали стратегии."""
        return await self._post("/v1/pricing-strategy/info", {"strategy_id": strategy_id})

    async def pricing_strategy_update(self, strategy_id: str, name: str, competitors: list[dict]) -> dict:
        """POST /v1/pricing-strategy/update — обновить стратегию."""
        return await self._post("/v1/pricing-strategy/update",
                                {"strategy_id": strategy_id, "strategy_name": name, "competitors": competitors})

    async def pricing_strategy_delete(self, strategy_id: str) -> dict:
        """POST /v1/pricing-strategy/delete — удалить стратегию."""
        return await self._post("/v1/pricing-strategy/delete", {"strategy_id": strategy_id})

    async def pricing_strategy_status(self, strategy_id: str, enabled: bool) -> dict:
        """POST /v1/pricing-strategy/status — включить/выключить стратегию."""
        return await self._post("/v1/pricing-strategy/status",
                                {"strategy_id": strategy_id, "enabled": enabled})

    async def pricing_strategy_products_add(self, strategy_id: str, product_ids: list[int]) -> dict:
        """POST /v1/pricing-strategy/products/add — добавить товары в стратегию."""
        return await self._post("/v1/pricing-strategy/products/add",
                                {"strategy_id": strategy_id, "product_id": product_ids})

    async def pricing_strategy_products_delete(self, product_ids: list[int]) -> dict:
        """POST /v1/pricing-strategy/products/delete — убрать товары из стратегий."""
        return await self._post("/v1/pricing-strategy/products/delete", {"product_id": product_ids})

    async def pricing_strategy_products_list(self, strategy_id: str) -> dict:
        """POST /v1/pricing-strategy/products/list — товары стратегии."""
        return await self._post("/v1/pricing-strategy/products/list", {"strategy_id": strategy_id})

    async def pricing_competitors_list(self, page: int = 1, limit: int = 50) -> dict:
        """POST /v1/pricing-strategy/competitors/list — список конкурентов (другие площадки)."""
        return await self._post("/v1/pricing-strategy/competitors/list", {"page": page, "limit": limit})

    async def pricing_competitor_price(self, product_id: int) -> dict:
        """POST /v1/pricing-strategy/product/info — цена товара у конкурента."""
        return await self._post("/v1/pricing-strategy/product/info", {"product_id": product_id})

    # ── Цены ──────────────────────────────────────────────
    async def product_import_prices(self, prices: list[dict]) -> dict:
        """POST /v1/product/import/prices — установить/обновить цены.

        Каждый элемент prices: {
            "offer_id": "...",
            "price": "1000",
            "old_price": "1200",
            "min_price": "800",
            "auto_action_enabled": "ENABLED",
            "min_price_for_auto_actions_enabled": true
        }
        """
        return await self._post("/v1/product/import/prices", {"prices": prices})

    async def product_info_prices_v4(
        self, offer_id: list[str] | None = None, limit: int = 100
    ) -> dict:
        """Совместимость: /v4/product/info/prices УДАЛЁН Ozon (404) — отдаём v5."""
        return await self.product_info_prices(offer_id=offer_id, limit=limit)

    async def product_info_prices(
        self, offer_id: list[str] | None = None, product_id: list[int] | None = None,
        limit: int = 100, cursor: str = ""
    ) -> dict:
        """POST /v5/product/info/prices — текущие цены по товарам.

        Поле filter ОБЯЗАТЕЛЬНО (минимум visibility=ALL), пагинация через cursor.
        """
        filt: dict[str, Any] = {"visibility": "ALL"}
        if offer_id:
            filt["offer_id"] = offer_id
        if product_id:
            filt["product_id"] = [str(p) for p in product_id]
        body: dict[str, Any] = {"limit": limit, "cursor": cursor, "filter": filt}
        return await self._post("/v5/product/info/prices", body)

    async def action_timer_status(self, product_id: list[int]) -> dict:
        """POST /v1/product/action/timer/status — статус таймера мин. цены."""
        return await self._post(
            "/v1/product/action/timer/status", {"product_id": product_id}
        )

    async def action_timer_update(self, product_id: list[int]) -> dict:
        """POST /v1/product/action/timer/update — продлить таймер мин. цены."""
        return await self._post(
            "/v1/product/action/timer/update", {"product_id": product_id}
        )

    # ── Финансы ────────────────────────────────────────────
    # Услуги в начислениях, которые Ozon относит к возвратам и отменам.
    # Логистика возврата приходит с type_id 32 и относится к доставке, а не к
    # возвратам — разнесение идёт по type_id услуги, а не по типу операции
    # (проверено сообществом на 9 месяцах по двум кабинетам, issue #6).
    RETURN_SERVICE_TYPE_IDS = frozenset({45, 59})

    async def finance_transaction_list(
        self, date_from: str, date_to: str, page: int = 1, page_size: int = 50,
        operation_type: list[str] | None = None,
    ) -> dict:
        """Финансовые операции за период — из начислений по дням.

        `/v3/finance/transaction/list` отключён Ozon (объявленная дата 08.09.2026,
        фактически отвечает 400 уже сейчас). Замены «одним запросом» нет:
        `/v1/finance/accrual/by-day` принимает ровно один день, поэтому период
        обходится по дням. Ограничение сверху — MAX_ACCRUAL_DAYS, иначе один вызов
        инструмента превращается в десятки запросов к Ozon.

        Возвращает начисления с указанием источника; `page`/`page_size` больше не
        применяются на стороне Ozon и используются как срез уже собранного списка.
        """
        days = self._accrual_days(date_from, date_to)
        accruals: list[dict] = []
        for day in days:
            accruals.extend(await self._accruals_for_day(day))

        start = max(0, (page - 1) * page_size)
        page_items = accruals[start:start + page_size]
        return {
            "source": "/v1/finance/accrual/by-day",
            "note": ("Данные собраны по дням: /v3/finance/transaction/list отключён Ozon. "
                     f"Обработано дней: {len(days)}, начислений всего: {len(accruals)}."),
            "period": {"from": date_from, "to": date_to},
            "total": len(accruals),
            "page": page,
            "page_size": page_size,
            "accruals": page_items,
        }

    async def finance_transaction_totals(self, date_from: str, date_to: str) -> dict:
        """Итоги за период — сумма начислений по дням.

        `/v3/finance/transaction/totals` отключён Ozon. Здесь суммы считаются из
        `/v1/finance/accrual/by-day`: итог, разбивка по категориям начислений
        (ITEM / POSTING / NON_ITEM) и по type_id услуги. Разнесение доставки и
        возвратов идёт по type_id услуги — Ozon относит логистику возврата
        (type_id 32) к доставке, а не к возвратам.
        """
        # Справочник берём первым: после обхода дней запросы упираются в лимит Ozon,
        # и расшифровка type_id молча теряется.
        names = await self._accrual_type_names()

        days = self._accrual_days(date_from, date_to)
        total = 0.0
        by_category: dict[str, float] = {}
        by_service: dict[str, float] = {}
        returns_total = 0.0
        count = 0

        for day in days:
            for accrual in await self._accruals_for_day(day):
                count += 1
                amount = self._money(accrual.get("total_amount"))
                total += amount
                category = accrual.get("accrued_category") or "UNKNOWN"
                by_category[category] = round(by_category.get(category, 0.0) + amount, 2)
                for type_id, service_amount in self._services(accrual):
                    key = str(type_id)
                    by_service[key] = round(by_service.get(key, 0.0) + service_amount, 2)
                    if type_id in self.RETURN_SERVICE_TYPE_IDS:
                        returns_total = round(returns_total + service_amount, 2)

        by_service_named = {
            f"{type_id} — {names[int(type_id)]}" if int(type_id) in names else type_id: amount
            for type_id, amount in by_service.items()
        }

        return {
            "source": "/v1/finance/accrual/by-day",
            "note": ("Итоги пересчитаны из начислений: /v3/finance/transaction/totals "
                     "отключён Ozon. Разнесение по type_id услуги, а не по типу операции."),
            "period": {"from": date_from, "to": date_to},
            "days": len(days),
            "accruals": count,
            "total": round(total, 2),
            "by_category": by_category,
            "by_service": by_service_named,
            "returns_and_cancellations": returns_total,
        }

    # Больше дней за один вызов — это десятки запросов к Ozon и минуты ожидания.
    MAX_ACCRUAL_DAYS = 31

    @staticmethod
    def _money(value: Any) -> float:
        """Суммы приходят как {"amount": "-21.75", "currency": "RUB"}."""
        if not isinstance(value, dict):
            return 0.0
        try:
            return float(value.get("amount") or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _services(cls, accrual: dict) -> list[tuple[int, float]]:
        """Услуги начисления: (type_id, сумма) из отправлений и товарных сборов."""
        found: list[tuple[int, float]] = []
        posting = accrual.get("posting") or {}
        for product in posting.get("products") or []:
            delivery = product.get("delivery") or {}
            for service in delivery.get("services") or []:
                found.append((service.get("type_id"), cls._money(service.get("accrued"))))
        item_fees = accrual.get("item_fees") or {}
        for entry in item_fees.get("fees") or []:
            for fee in entry.get("fees") or []:
                found.append((fee.get("type_id"), cls._money(fee.get("accrued"))))
        return [(t, a) for t, a in found if isinstance(t, int)]

    @classmethod
    def _accrual_days(cls, date_from: str, date_to: str) -> list[str]:
        """Список дат периода, не длиннее MAX_ACCRUAL_DAYS."""
        import datetime

        start = datetime.date.fromisoformat(date_from[:10])
        end = datetime.date.fromisoformat(date_to[:10])
        if end < start:
            start, end = end, start
        span = min((end - start).days, cls.MAX_ACCRUAL_DAYS - 1)
        return [str(start + datetime.timedelta(days=i)) for i in range(span + 1)]

    async def _accruals_for_day(self, day: str) -> list[dict]:
        """Все начисления за день с учётом пагинации по last_id."""
        collected: list[dict] = []
        last_id = ""
        for _ in range(50):  # предохранитель от бесконечной пагинации
            page = await self.finance_accrual_by_day(day, last_id=last_id)
            batch = page.get("accruals") or []
            collected.extend(batch)
            last_id = page.get("last_id") or ""
            if not last_id or not batch:
                break
        return collected

    async def finance_realization(self, month: int, year: int) -> dict:
        """POST /v2/finance/realization — отчёт о реализации за месяц (v1 удалён)."""
        return await self._post("/v2/finance/realization", {"month": month, "year": year})

    async def finance_mutual_settlement(self, date: str) -> dict:
        """POST /v1/finance/mutual-settlement — отчёт о взаиморасчётах (date: YYYY-MM)."""
        return await self._post("/v1/finance/mutual-settlement", {"date": date})

    async def finance_accrual_types(self) -> dict:
        """POST /v1/finance/accrual/types — справочник видов начислений.

        Именно он расшифровывает `type_id` в начислениях: 1 — эквайринг,
        32 — обратная логистика и так далее. Справочник статичен, поэтому
        кэшируется на время жизни клиента.
        """
        if self._accrual_types_cache is None:
            self._accrual_types_cache = await self._post("/v1/finance/accrual/types", {})
        return self._accrual_types_cache

    async def _accrual_type_names(self) -> dict[int, str]:
        """{type_id: человеческое название} — пустой словарь, если справочник недоступен."""
        try:
            data = await self.finance_accrual_types()
        except Exception:
            return {}
        names: dict[int, str] = {}
        for entry in data.get("accrual_types") or []:
            type_id = entry.get("id")
            if isinstance(type_id, int):
                names[type_id] = entry.get("description") or entry.get("name") or ""
        return names

    async def finance_accrual_by_day(self, date: str, last_id: str = "") -> dict:
        """POST /v1/finance/accrual/by-day — начисления за один день (YYYY-MM-DD).

        Ровно один день за вызов; следующая страница берётся по `last_id` из ответа.
        """
        body: dict[str, Any] = {"date": date}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v1/finance/accrual/by-day", body)

    async def finance_products_buyout(self, date_from: str, date_to: str) -> dict:
        """POST /v1/finance/products/buyout — выкупленные товары за период."""
        return await self._post("/v1/finance/products/buyout", {"date_from": date_from, "date_to": date_to})

    async def finance_cash_flow(
        self, date_from: str, date_to: str, page: int = 1, page_size: int = 50
    ) -> dict:
        """POST /v1/finance/cash-flow-statement/list — движение средств."""
        return await self._post(
            "/v1/finance/cash-flow-statement/list",
            {"date": {"from": date_from, "to": date_to}, "with_details": True,
             "page": page, "page_size": page_size},
        )

    # ── Рейтинг ───────────────────────────────────────────
    async def rating_summary(self) -> dict:
        """GET /v1/rating/summary — рейтинг продавца."""
        return await self._post("/v1/rating/summary", {})

    async def rating_history(self, date_from: str, date_to: str) -> dict:
        """GET /v1/rating/history — история рейтинга."""
        return await self._post(
            "/v1/rating/history",
            {"date_from": date_from, "date_to": date_to},
        )

    # ── Отзывы ─────────────────────────────────────────────
    async def review_list(
        self, sku: list[int] | None = None, limit: int = 50, sort_dir: str = "DESC",
        last_id: str | None = None
    ) -> dict:
        """POST /v1/review/list — список отзывов."""
        body: dict[str, Any] = {"limit": limit, "sort_dir": sort_dir}
        if sku:
            body["sku"] = sku
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v1/review/list", body)

    async def review_comment_create(self, review_id: str, text: str) -> dict:
        """POST /v1/review/comment/create — ответить на отзыв."""
        return await self._post("/v1/review/comment/create", {"review_id": review_id, "text": text})

    async def review_comment_list(self, review_id: str, limit: int = 20) -> dict:
        """POST /v1/review/comment/list — комментарии к отзыву."""
        return await self._post("/v1/review/comment/list", {"review_id": review_id, "limit": limit})

    async def review_count(self) -> dict:
        """POST /v1/review/count — количество отзывов (обработанные/необработанные)."""
        return await self._post("/v1/review/count", {})

    async def review_comment_delete(self, review_id: str, comment_id: str) -> dict:
        """POST /v1/review/comment/delete — удалить ответ на отзыв."""
        return await self._post("/v1/review/comment/delete", {"review_id": review_id, "comment_id": comment_id})

    # ── Аналитика ──────────────────────────────────────────
    async def analytics_data(
        self, date_from: str, date_to: str,
        metrics: list[str], dimensions: list[str],
        filters: list[dict] | None = None,
        limit: int = 1000, offset: int = 0,
    ) -> dict:
        """POST /v1/analytics/data — аналитические данные."""
        body: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "metrics": metrics,
            "dimension": dimensions,
            "limit": limit,
            "offset": offset,
        }
        if filters:
            body["filters"] = filters
        return await self._post("/v1/analytics/data", body)

    # /v1/analytics/stock_on_warehouses УДАЛЁН из Ozon API (404).
    # Замены: /v1/analytics/stocks (по SKU) и /v1/analytics/turnover/stocks.

    async def analytics_stocks(self, skus: list[int]) -> dict:
        """POST /v1/analytics/stocks — аналитика по остаткам (1-100 SKU за запрос)."""
        return await self._post("/v1/analytics/stocks", {"skus": [str(s) for s in skus]})

    async def analytics_turnover_stocks(self, limit: int = 100, offset: int = 0,
                                        skus: list[int] | None = None) -> dict:
        """POST /v1/analytics/turnover/stocks — оборачиваемость и остатки FBO."""
        body: dict[str, Any] = {"limit": limit, "offset": offset}
        if skus:
            body["sku"] = [str(s) for s in skus]
        return await self._post("/v1/analytics/turnover/stocks", body)

    async def analytics_stock_on_warehouses(
        self, limit: int = 100, offset: int = 0, warehouse_type: str = "ALL"
    ) -> dict:
        """Совместимость: старый stock_on_warehouses удалён — отдаём turnover/stocks."""
        return await self.analytics_turnover_stocks(limit=limit, offset=offset)

    async def product_queries(self, date_from: str, skus: list[int],
                              page_size: int = 50) -> dict:
        """POST /v1/analytics/product-queries — поисковые запросы по моим товарам (Premium).

        КРИТИЧНО: видимость в поиске = продажи.
        """
        if "T" not in date_from:
            date_from += "T00:00:00Z"
        return await self._post("/v1/analytics/product-queries", {
            "date_from": date_from, "skus": [str(s) for s in skus], "page_size": page_size,
        })

    async def product_queries_details(self, date_from: str, skus: list[int],
                                      limit_by_sku: int = 10, page_size: int = 50) -> dict:
        """POST /v1/analytics/product-queries/details — детализация запросов по товарам (Premium)."""
        if "T" not in date_from:
            date_from += "T00:00:00Z"
        return await self._post("/v1/analytics/product-queries/details", {
            "date_from": date_from, "skus": [str(s) for s in skus],
            "limit_by_sku": limit_by_sku, "page_size": page_size,
        })

    async def search_queries_top(self, limit: int = 50, offset: int = 0) -> dict:
        """POST /v1/search-queries/top — популярные поисковые запросы на Ozon."""
        return await self._post("/v1/search-queries/top", {"limit": limit, "offset": offset})

    async def finance_balance(self, date_from: str = "", date_to: str = "") -> dict:
        """POST /v1/finance/balance — баланс продавца за период (Beta).

        Без дат — последние 30 дней. Возвращает opening/closing balance, начисления, выплаты.
        """
        from datetime import date as _d, timedelta as _td
        if not date_to:
            date_to = _d.today().isoformat()
        if not date_from:
            date_from = (_d.today() - _td(days=30)).isoformat()
        return await self._post("/v1/finance/balance", {"date_from": date_from, "date_to": date_to})

    async def product_attributes_update(self, items: list[dict]) -> dict:
        """POST /v1/product/attributes/update — обновить характеристики товаров."""
        return await self._post("/v1/product/attributes/update", {"items": items})

    async def product_import_by_sku(self, items: list[dict]) -> dict:
        """POST /v1/product/import-by-sku — создать товар-копию по SKU."""
        return await self._post("/v1/product/import-by-sku", {"items": items})

    async def product_stocks_by_warehouse(self, skus: list[int] | None = None,
                                          limit: int = 100, cursor: str = "") -> dict:
        """POST /v2/product/info/stocks-by-warehouse/fbs — остатки по складам FBS (v1 отключается 07.04.2026)."""
        body: dict[str, Any] = {"limit": limit}
        if skus:
            body["sku"] = [str(s) for s in skus]
        if cursor:
            body["cursor"] = cursor
        return await self._post("/v2/product/info/stocks-by-warehouse/fbs", body)

    # ── Товары ─────────────────────────────────────────────
    async def product_list(
        self, limit: int = 100, last_id: str = "",
        visibility: str = "ALL",
    ) -> dict:
        """POST /v3/product/list — список товаров."""
        return await self._post(
            "/v3/product/list",
            {"filter": {"visibility": visibility}, "limit": limit, "last_id": last_id},
        )

    async def product_info_list(self, product_id: list[int]) -> dict:
        """POST /v3/product/info/list — расширенная информация по товарам."""
        return await self._post(
            "/v3/product/info/list", {"product_id": product_id}
        )

    async def product_info_attributes(
        self, offer_id: list[str] | None = None, product_id: list[int] | None = None,
        limit: int = 100, last_id: str = "",
    ) -> dict:
        """POST /v4/product/info/attributes — атрибуты товаров (включая бренд)."""
        body: dict[str, Any] = {"limit": limit, "last_id": last_id}
        filt: dict[str, Any] = {}
        if offer_id:
            filt["offer_id"] = offer_id
        if product_id:
            filt["product_id"] = product_id
        if filt:
            body["filter"] = filt
        return await self._post("/v4/product/info/attributes", body)

    async def product_info_stocks(
        self, offer_id: list[str] | None = None, product_id: list[int] | None = None,
        limit: int = 100, last_id: str = "",
    ) -> dict:
        """POST /v4/product/info/stocks — остатки по товарам FBO/FBS."""
        body: dict[str, Any] = {"limit": limit, "last_id": last_id}
        filt: dict[str, Any] = {}
        if offer_id:
            filt["offer_id"] = offer_id
        if product_id:
            filt["product_id"] = product_id
        if filt:
            body["filter"] = filt
        return await self._post("/v4/product/info/stocks", body)

    async def product_certificate_list(
        self, product_id: list[int], page: int = 1, page_size: int = 100
    ) -> dict:
        """POST /v1/product/certificate/list — сертификаты товаров."""
        return await self._post(
            "/v1/product/certificate/list",
            {"filter": {"product_id": product_id}, "page": page, "page_size": page_size},
        )

    async def product_import(self, items: list[dict]) -> dict:
        """POST /v3/product/import — создать/обновить товары."""
        return await self._post("/v3/product/import", {"items": items})

    async def product_import_info(self, task_id: int) -> dict:
        """POST /v1/product/import/info — статус импорта."""
        return await self._post("/v1/product/import/info", {"task_id": task_id})

    async def product_update_offer_id(self, update_offer_id: list[dict]) -> dict:
        """POST /v1/product/update/offer-id — обновить артикулы."""
        return await self._post("/v1/product/update/offer-id", {"update_offer_id": update_offer_id})

    async def product_update_images(self, product_id: int, images: list[str]) -> dict:
        """POST /v1/product/pictures/import — обновить изображения."""
        return await self._post("/v1/product/pictures/import", {"product_id": product_id, "images": images})

    async def product_info_description(self, offer_id: str) -> dict:
        """POST /v1/product/info/description — описание товара."""
        return await self._post("/v1/product/info/description", {"offer_id": offer_id})

    async def product_update_stocks(self, stocks: list[dict]) -> dict:
        """POST /v2/products/stocks — обновить остатки FBS."""
        return await self._post("/v2/products/stocks", {"stocks": stocks})

    async def product_geo_restrictions_set(self, product_id: int, restrictions: list[dict]) -> dict:
        """POST /v1/product/geo-restrictions/set — географические ограничения."""
        return await self._post("/v1/product/geo-restrictions/set", {"product_id": product_id, "restrictions": restrictions})

    async def product_unarchive(self, product_id: list[int]) -> dict:
        """POST /v1/product/unarchive — вернуть товары из архива."""
        return await self._post("/v1/product/unarchive", {"product_id": product_id})

    async def product_delete(self, offer_ids: list[str]) -> dict:
        """POST /v2/products/delete — удалить товары без SKU из архива. Тело: products[{offer_id}]."""
        return await self._post("/v2/products/delete", {"products": [{"offer_id": o} for o in offer_ids]})

    async def product_info_limit(self) -> dict:
        """POST /v4/product/info/limit — лимиты на создание товаров."""
        return await self._post("/v4/product/info/limit", {})

    async def product_rating_by_sku(self, skus: list[int]) -> dict:
        """POST /v1/product/rating-by-sku — рейтинг контента товаров."""
        return await self._post("/v1/product/rating-by-sku", {"skus": skus})

    async def product_info_discounted(self, discounted_skus: list[int]) -> dict:
        """POST /v1/product/info/discounted — информация об уценке по SKU уценённых товаров."""
        return await self._post("/v1/product/info/discounted", {"discounted_skus": [str(s) for s in discounted_skus]})

    # ── Заказы FBO ─────────────────────────────────────────
    async def posting_fbo_list(
        self, since: str, to: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """POST /v3/posting/fbo/list — заказы FBO.

        /v2 отключается 31.08.2026 (issue #6). Контракт запроса тот же.
        """
        return await self._post(
            "/v3/posting/fbo/list",
            {"dir": "DESC", "filter": {"since": since, "to": to},
             "limit": limit, "offset": offset, "with": {"analytics_data": True}},
        )

    # ── Заказы FBS ─────────────────────────────────────────
    async def posting_fbs_list(
        self, since: str, to: str, limit: int = 50, status: str = "", cursor: str = ""
    ) -> dict:
        """POST /v4/posting/fbs/list — заказы FBS.

        /v3 отключается 31.08.2026 (issue #6).

        ВНИМАНИЕ: v4 — это НЕ переименование v3, у него другой ответ:
          * `postings` лежат на ВЕРХНЕМ уровне, а не под `result`;
          * пагинация КУРСОРНАЯ: в ответе `has_next` и `cursor`, параметра
            `offset` больше нет — следующую страницу берут, передав `cursor`
            из предыдущего ответа.
        Если разбирать ответ как в v3 (`d["result"]["postings"]`), получится
        пустой список и ложный вывод «заказов нет».

        Набор данных при этом идентичен v3 — проверено автором issue #6 на
        своём кабинете: обе версии вернули одни и те же 17 отправлений.
        """
        body: dict[str, Any] = {
            "dir": "DESC",
            "filter": {"since": since, "to": to},
            "limit": limit,
            "with": {"analytics_data": True, "financial_data": True},
        }
        if status:
            body["filter"]["status"] = status
        if cursor:
            body["cursor"] = cursor
        return await self._post("/v4/posting/fbs/list", body)

    async def posting_fbs_get(self, posting_number: str) -> dict:
        """POST /v3/posting/fbs/get — детали отправления FBS."""
        return await self._post("/v3/posting/fbs/get", {"posting_number": posting_number, "with": {"analytics_data": True, "financial_data": True}})

    async def posting_fbs_ship(self, posting_number: str, packages: list[dict]) -> dict:
        """POST /v4/posting/fbs/ship — собрать заказ FBS (v3 удалён)."""
        return await self._post("/v4/posting/fbs/ship", {"posting_number": posting_number, "packages": packages})

    # Статусы отправления FBS, означающие «ещё не собрано».
    # awaiting_packaging — ждёт упаковки, awaiting_deliver — упаковано, ждёт отгрузки.
    UNFULFILLED_STATUSES = ("awaiting_packaging", "awaiting_deliver")

    async def posting_fbs_unfulfilled(
        self, limit: int = 100, cutoff_from: str = "", cutoff_to: str = "", cursor: str = ""
    ) -> dict:
        """Несобранные заказы FBS — через POST /v4/posting/fbs/list.

        Отдельного метода больше нет: /v3/posting/fbs/unfulfilled/list отключается
        31.08.2026, и прямой замены Ozon не предложил (issue #6). Поэтому несобранные
        отправления выбираются из общего списка фильтром по статусам
        awaiting_packaging и awaiting_deliver.

        Ответ — как у /v4/posting/fbs/list: `postings` на верхнем уровне,
        курсорная пагинация (`has_next`, `cursor`).

        Отличие от прежнего поведения: старый метод не требовал периода, а v4
        требует `filter.since`/`filter.to`. Если период не задан, берём последние
        30 дней — этого хватает, чтобы покрыть любой несобранный заказ.
        """
        body: dict[str, Any] = {
            "dir": "ASC",
            "limit": limit,
            "with": {"analytics_data": True, "financial_data": True},
        }
        if cutoff_from and cutoff_to:
            flt: dict[str, Any] = {"cutoff_from": cutoff_from, "cutoff_to": cutoff_to}
        else:
            now = datetime.now(timezone.utc)
            flt = {
                "since": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        flt["status"] = list(self.UNFULFILLED_STATUSES)
        body["filter"] = flt
        if cursor:
            body["cursor"] = cursor
        return await self._post("/v4/posting/fbs/list", body)

    async def posting_fbs_package_label(self, posting_numbers: list[str]) -> dict:
        """POST /v2/posting/fbs/package-label — этикетки отправлений (синхронно, PDF base64)."""
        return await self._post("/v2/posting/fbs/package-label", {"posting_number": posting_numbers})

    async def posting_fbs_act_create(self, containers_count: int = 1) -> dict:
        """POST /v2/posting/fbs/act/create — создать акт приёма-передачи.

        ⚠️ Ozon отключает 07.09.2026. Замена — carriage_create + carriage_approve.
        """
        return await self._post("/v2/posting/fbs/act/create", {"containers_count": containers_count})

    async def carriage_create(self, delivery_method_id: int, departure_date: str = "",
                              containers_count: int = 1) -> dict:
        """POST /v1/carriage/create — создать отгрузку (замена акта приёма-передачи).

        ⚠️ У этой ручки нет обязательных полей на стороне Ozon: пустое тело `{}` —
        валидный запрос, по которому Ozon сам подберёт отправления и создаст
        настоящую отгрузку. Поэтому delivery_method_id обязателен здесь: случайный
        вызов без параметров не должен создавать отгрузку по всему кабинету.

        Отгрузка создаётся в статусе `new`; в `formed` её переводит carriage_approve.
        """
        if not delivery_method_id:
            raise ValueError(
                "carriage_create: укажите delivery_method_id. Без него Ozon создаст "
                "отгрузку по всем доступным отправлениям — это необратимо."
            )
        body: dict[str, Any] = {
            "delivery_method_id": delivery_method_id,
            "containers_count": containers_count,
        }
        if departure_date:
            body["departure_date"] = departure_date
        return await self._post("/v1/carriage/create", body)

    async def carriage_delivery_list(self, limit: int = 50, offset: int = 0) -> dict:
        """POST /v2/carriage/delivery/list — методы доставки и их отгрузки.

        Отсюда берётся delivery_method_id для carriage_create: без него отгрузку
        создавать нельзя, а больше он нигде не отдаётся.
        """
        return await self._post("/v2/carriage/delivery/list", {"limit": limit, "offset": offset})

    async def action_auto_add_products(self, action_id: int, auto_add_date: str,
                                       limit: int = 50, offset: int = 0) -> dict:
        """POST /v1/actions/auto-add/products/list — товары, которые Ozon добавит в акцию сам."""
        return await self._post("/v1/actions/auto-add/products/list", {
            "action_id": action_id, "auto_add_date": auto_add_date,
            "limit": limit, "offset": offset,
        })

    async def action_auto_add_candidates(self, action_id: int, auto_add_date: str,
                                         limit: int = 50, offset: int = 0) -> dict:
        """POST /v1/actions/auto-add/products/candidates — кандидаты на автодобавление."""
        return await self._post("/v1/actions/auto-add/products/candidates", {
            "action_id": action_id, "auto_add_date": auto_add_date,
            "limit": limit, "offset": offset,
        })

    async def action_auto_add_delete(self, action_id: int, product_ids: list[int]) -> dict:
        """POST /v1/actions/auto-add/products/delete — убрать товары из автодобавления."""
        return await self._post("/v1/actions/auto-add/products/delete", {
            "action_id": action_id, "product_id": product_ids,
        })

    async def carriage_approve(self, carriage_id: int) -> dict:
        """POST /v1/carriage/approve — подтвердить отгрузку, статус new → formed."""
        return await self._post("/v1/carriage/approve", {"carriage_id": carriage_id})

    async def posting_fbs_act_check_status(self, id: int) -> dict:
        """POST /v2/posting/fbs/act/check-status — статус формирования акта."""
        return await self._post("/v2/posting/fbs/act/check-status", {"id": id})

    async def posting_fbs_act_get_pdf(self, id: int) -> dict:
        """POST /v2/posting/fbs/act/get-pdf — скачать PDF акта."""
        return await self._post("/v2/posting/fbs/act/get-pdf", {"id": id})

    async def posting_fbs_digital_act_create(self, id: int) -> dict:
        """Совместимость: цифровые акты удалены Ozon 22.03.2026 — используем статус обычного акта."""
        return await self.posting_fbs_act_check_status(id)

    async def posting_fbs_cancel(self, posting_number: str, cancel_reason_id: int, cancel_reason_message: str = "") -> dict:
        """POST /v2/posting/fbs/cancel — отменить FBS отправление."""
        return await self._post("/v2/posting/fbs/cancel", {"posting_number": posting_number, "cancel_reason_id": cancel_reason_id, "cancel_reason_message": cancel_reason_message})

    async def posting_fbs_cancel_reasons(self) -> dict:
        """POST /v2/posting/fbs/cancel-reason/list — причины отмены FBS."""
        return await self._post("/v2/posting/fbs/cancel-reason/list", {})

    async def posting_fbs_product_country_list(self, posting_number: str) -> dict:
        """POST /v2/posting/fbs/product/country/list — справочник стран-изготовителей."""
        return await self._post("/v2/posting/fbs/product/country/list", {"posting_number": posting_number})

    async def posting_fbs_product_country_set(self, posting_number: str, product_id: int, country_iso: str) -> dict:
        """POST /v2/posting/fbs/product/country/set — указать страну-изготовителя товара."""
        return await self._post("/v2/posting/fbs/product/country/set", {"posting_number": posting_number, "product_id": product_id, "country_iso_code": country_iso})

    async def posting_fbs_restrictions(self, posting_number: list[str]) -> dict:
        """POST /v1/posting/fbs/restrictions — ограничения отправлений."""
        return await self._post("/v1/posting/fbs/restrictions", {"posting_number": posting_number})

    async def posting_fbs_timeslot_change(self, posting_number: str, new_timeslot_id: int) -> dict:
        """POST /v1/posting/fbs/timeslot/change — изменить тайм-слот."""
        return await self._post("/v1/posting/fbs/timeslot/change", {"posting_number": posting_number, "new_timeslot_id": new_timeslot_id})

    async def posting_fbo_get(self, posting_number: str) -> dict:
        """POST /v2/posting/fbo/get — детали FBO отправления."""
        return await self._post("/v2/posting/fbo/get", {"posting_number": posting_number, "with": {"analytics_data": True, "financial_data": True}})

    # ── Поставки FBO (supply-order, v2 удалены → v3) ───────
    async def supply_orders_list(self, states: list[int] | None = None, limit: int = 50) -> dict:
        """POST /v3/supply-order/list — заявки на поставку FBO (возвращает order_ids).

        states — ЦЕЛОЧИСЛЕННЫЕ коды статусов 1-8 (по умолчанию все).
        Детали заявок — через supply_orders_get.
        """
        return await self._post("/v3/supply-order/list", {
            "limit": limit, "sort_by": 1,
            "filter": {"states": states or [1, 2, 3, 4, 5, 6, 7, 8]},
        })

    async def supply_orders_get(self, order_ids: list[int]) -> dict:
        """POST /v3/supply-order/get — детали заявок на поставку (1-50)."""
        return await self._post("/v3/supply-order/get", {"order_ids": order_ids})

    async def supply_order_status_counter(self) -> dict:
        """POST /v1/supply-order/status/counter — счётчики заявок по статусам."""
        return await self._post("/v1/supply-order/status/counter", {})

    async def supply_order_timeslots(self, supply_order_id: int) -> dict:
        """POST /v1/supply-order/timeslot/get — доступные таймслоты поставки."""
        return await self._post("/v1/supply-order/timeslot/get", {"supply_order_id": supply_order_id})

    # ── Возвраты ───────────────────────────────────────────
    # /v3/returns/company/fbo|fbs OBSOLETE → единый /v1/returns/list.
    # Заявки rFBS — /v2/returns/rfbs/* (v1 удалены).

    async def returns_list(self, filter_params: dict | None = None, limit: int = 100, last_id: int = 0) -> dict:
        """POST /v1/returns/list — ЕДИНЫЙ список возвратов (FBO + FBS)."""
        body: dict[str, Any] = {"filter": filter_params or {}, "limit": limit}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v1/returns/list", body)

    async def returns_rfbs_list(self, limit: int = 100, last_id: int = 0) -> dict:
        """POST /v2/returns/rfbs/list — заявки покупателей на возврат rFBS."""
        body: dict[str, Any] = {"limit": limit}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v2/returns/rfbs/list", body)

    async def returns_rfbs_get(self, return_id: int) -> dict:
        """POST /v2/returns/rfbs/get — детали заявки rFBS."""
        return await self._post("/v2/returns/rfbs/get", {"return_id": return_id})

    async def returns_rfbs_action(self, action: str, return_id: int, comment: str = "") -> dict:
        """POST /v2/returns/rfbs/{action} — действие по заявке rFBS.

        action: verify (одобрить), reject (отклонить, нужен comment),
        receive-return (подтвердить получение), return-money (вернуть деньги),
        compensate (компенсация без возврата товара).
        """
        body: dict[str, Any] = {"return_id": return_id}
        if comment:
            body["comment"] = comment
        return await self._post(f"/v2/returns/rfbs/{action}", body)

    async def report_returns_create(self, filter_params: dict) -> dict:
        """POST /v2/report/returns/create — создать отчёт по возвратам."""
        return await self._post("/v2/report/returns/create", {"filter": filter_params})

    # ── Вопросы ────────────────────────────────────────────
    async def question_list(self, limit: int = 50, last_id: str = "", sort_dir: str = "DESC") -> dict:
        """POST /v1/question/list — список вопросов."""
        body: dict[str, Any] = {"limit": limit, "sort_dir": sort_dir}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v1/question/list", body)

    async def question_reply(self, question_id: str, sku: int, text: str) -> dict:
        """POST /v1/question/answer/create — ответить на вопрос (нужен sku товара)."""
        return await self._post("/v1/question/answer/create",
                                {"question_id": question_id, "sku": sku, "text": text})

    async def question_count(self) -> dict:
        """POST /v1/question/count — количество вопросов по статусам."""
        return await self._post("/v1/question/count", {})

    # ── Чат ────────────────────────────────────────────────
    # v1/v2 list, v1/v2 history и v1/v2 updates УДАЛЕНЫ (404). Актуально:
    # list v3, history v3, send/message v1, read v2.

    async def chat_list(self, page_size: int = 100, cursor: str = "",
                        unread_only: bool = False, chat_status: str = "All") -> dict:
        """POST /v3/chat/list — список чатов."""
        body: dict[str, Any] = {
            "limit": page_size,
            "filter": {"chat_status": chat_status, "unread_only": unread_only},
        }
        if cursor:
            body["cursor"] = cursor
        return await self._post("/v3/chat/list", body)

    async def chat_history(self, chat_id: str, limit: int = 50, from_message_id: int | None = None) -> dict:
        """POST /v3/chat/history — история сообщений чата (новые → старые)."""
        body: dict[str, Any] = {"chat_id": chat_id, "limit": limit, "direction": "Backward"}
        if from_message_id:
            body["from_message_id"] = from_message_id
        return await self._post("/v3/chat/history", body)

    async def chat_send_message(self, chat_id: str, text: str) -> dict:
        """POST /v1/chat/send/message — отправить сообщение в чат."""
        return await self._post("/v1/chat/send/message", {"chat_id": chat_id, "text": text})

    async def chat_send_file(self, chat_id: str, file_url: str, file_name: str) -> dict:
        """POST /v1/chat/send/file — отправить файл в чат."""
        return await self._post("/v1/chat/send/file", {"chat_id": chat_id, "file_url": file_url, "file_name": file_name})

    async def chat_updates(self, from_id: str = "", limit: int = 50) -> dict:
        """Совместимость: /v1/chat/updates удалён — отдаём непрочитанные чаты (v3 list)."""
        return await self.chat_list(page_size=limit, unread_only=True)

    async def chat_start(self, posting_number: str) -> dict:
        """POST /v1/chat/start — начать чат по отправлению."""
        return await self._post("/v1/chat/start", {"posting_number": posting_number})

    async def chat_read(self, chat_id: str, from_message_id: int | None = None) -> dict:
        """POST /v2/chat/read — пометить чат как прочитанный (v1 удалён)."""
        body: dict[str, Any] = {"chat_id": chat_id}
        if from_message_id:
            body["from_message_id"] = from_message_id
        return await self._post("/v2/chat/read", body)

    # ── Отмены (v1 obsolete → v2) ──────────────────────────
    async def conditional_cancellation_list(self, posting_number: str = "", state: str = "ON_APPROVAL",
                                            limit: int = 100, last_id: int = 0) -> dict:
        """POST /v2/conditional-cancellation/list — заявки покупателей на отмену.

        state: ALL | ON_APPROVAL | APPROVED | REJECTED.
        """
        filters: dict[str, Any] = {"state": state}
        if posting_number:
            filters["posting_number"] = posting_number
        body: dict[str, Any] = {"filters": filters, "limit": limit}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v2/conditional-cancellation/list", body)

    async def conditional_cancellation_approve(self, cancellation_id: int, comment: str = "") -> dict:
        """POST /v2/conditional-cancellation/approve — одобрить отмену."""
        body: dict[str, Any] = {"cancellation_id": cancellation_id}
        if comment:
            body["comment"] = comment
        return await self._post("/v2/conditional-cancellation/approve", body)

    async def conditional_cancellation_reject(self, cancellation_id: int, comment: str = "") -> dict:
        """POST /v2/conditional-cancellation/reject — отклонить отмену (comment обязателен)."""
        return await self._post("/v2/conditional-cancellation/reject", {"cancellation_id": cancellation_id, "comment": comment})

    # ── Склады ─────────────────────────────────────────────
    async def warehouse_list(self) -> dict:
        """POST /v2/warehouse/list — список складов FBS (v1 — obsolete)."""
        return await self._post("/v2/warehouse/list", {})

    async def delivery_method_list(self, limit: int = 50, offset: int = 0) -> dict:
        """POST /v2/delivery-method/list — методы доставки (v1 — obsolete)."""
        return await self._post("/v2/delivery-method/list", {"limit": limit, "offset": offset})

    # ── Отчёты ─────────────────────────────────────────────
    async def report_list(self, page: int = 1, page_size: int = 50, report_type: str = "") -> dict:
        """POST /v1/report/list — список отчётов."""
        body: dict[str, Any] = {"page": page, "page_size": page_size}
        if report_type:
            body["report_type"] = report_type
        return await self._post("/v1/report/list", body)

    async def report_info(self, code: str) -> dict:
        """POST /v1/report/info — статус отчёта."""
        return await self._post("/v1/report/info", {"code": code})

    async def report_products_create(self, visibility: str = "ALL", language: str = "DEFAULT") -> dict:
        """POST /v1/report/products/create — создать отчёт по товарам."""
        return await self._post("/v1/report/products/create", {"visibility": visibility, "language": language})

    async def report_stocks_create(self, warehouse_id: str = "", language: str = "DEFAULT") -> dict:
        """Отчёт по остаткам: /v1/report/stocks/create УДАЛЁН Ozon.

        warehouse_id задан → /v1/report/warehouse/stock (остатки FBS-склада),
        иначе — текущие остатки через /v1/analytics/turnover/stocks.
        """
        if warehouse_id:
            return await self._post("/v1/report/warehouse/stock", {"warehouseId": warehouse_id, "language": language})
        return await self.analytics_turnover_stocks(limit=1000)

    async def report_finance_create(self, date_from: str, date_to: str) -> dict:
        """Финансовый отчёт: /v1/report/finance/create УДАЛЁН Ozon — отдаём cash-flow-statement."""
        return await self.finance_cash_flow(date_from, date_to)

    async def report_discounted_create(self) -> dict:
        """POST /v1/report/discounted/create — отчёт по уценённым товарам."""
        return await self._post("/v1/report/discounted/create", {})

    # ── Бренд ──────────────────────────────────────────────
    async def brand_company_certification_list(self, page: int = 1, page_size: int = 100) -> dict:
        """POST /v1/brand/company-certification/list — сертификаты бренда."""
        return await self._post("/v1/brand/company-certification/list", {"page": page, "page_size": page_size})

    # ── Категории и характеристики ────────────────────────
    async def description_category_tree(self, language: str = "DEFAULT") -> dict:
        """POST /v1/description-category/tree — дерево категорий."""
        return await self._post("/v1/description-category/tree", {"language": language})

    async def description_category_attribute(self, description_category_id: int, type_id: int = 0, language: str = "DEFAULT") -> dict:
        """POST /v1/description-category/attribute — атрибуты категории."""
        return await self._post("/v1/description-category/attribute", {"description_category_id": description_category_id, "type_id": type_id, "language": language})

    async def description_category_attribute_values(self, description_category_id: int, attribute_id: int, limit: int = 100, last_value_id: int = 0, language: str = "DEFAULT") -> dict:
        """POST /v1/description-category/attribute/values — значения атрибута."""
        return await self._post("/v1/description-category/attribute/values", {"description_category_id": description_category_id, "attribute_id": attribute_id, "limit": limit, "last_value_id": last_value_id, "language": language})

    async def description_category_attribute_values_search(self, description_category_id: int, attribute_id: int, value: str, limit: int = 100, language: str = "DEFAULT") -> dict:
        """POST /v1/description-category/attribute/values/search — поиск значений."""
        return await self._post("/v1/description-category/attribute/values/search", {"description_category_id": description_category_id, "attribute_id": attribute_id, "value": value, "limit": limit, "language": language})

    # ── Push-уведомления (вебхуки, бета 04.2026) ───────────
    async def notification_list(self) -> dict:
        """POST /v1/notification/list — список подписок на push-уведомления (вебхуки)."""
        return await self._post("/v1/notification/list", {})

    async def notification_push_types(self) -> dict:
        """POST /v1/notification/push-type/list — справочник типов push-событий."""
        return await self._post("/v1/notification/push-type/list", {})

    async def notification_set(self, url: str) -> dict:
        """POST /v1/notification/set — создать подписку на вебхук."""
        return await self._post("/v1/notification/set", {"url": url})

    # ── «Хочу скидку» (заявки покупателей на скидку) ───────
    async def discount_task_list(self, status: str = "NEW", limit: int = 50, last_id: str = "") -> dict:
        """POST /v2/actions/discounts-task/list — заявки покупателей на скидку (v1 deprecated)."""
        body: dict[str, Any] = {"status": status, "limit": limit}
        if last_id:
            body["last_id"] = last_id
        return await self._post("/v2/actions/discounts-task/list", body)

    async def discount_task_approve(self, tasks: list[dict]) -> dict:
        """POST /v1/actions/discounts-task/approve — одобрить заявки.

        tasks: [{"id": ..., "approved_price": 990, "seller_comment": "",
                 "approved_quantity_min": 1, "approved_quantity_max": 1}]
        """
        return await self._post("/v1/actions/discounts-task/approve", {"tasks": tasks})

    async def discount_task_decline(self, tasks: list[dict]) -> dict:
        """POST /v1/actions/discounts-task/decline — отклонить заявки. tasks: [{"id", "seller_comment"}]"""
        return await self._post("/v1/actions/discounts-task/decline", {"tasks": tasks})

    # ── Компания ───────────────────────────────────────────
    async def company_info(self) -> dict:
        return {"error": "Endpoint /v1/company/info не существует в публичном Ozon API."}

    async def company_tariffs(self) -> dict:
        return {"error": "Endpoint /v1/company/tariffs не существует в публичном Ozon API."}

    # ── Сертификаты ────────────────────────────────────────
    async def certificate_list(self, page: int = 1, page_size: int = 100, status: str = "") -> dict:
        return {"error": "Endpoint /v1/certificate/list не существует в публичном Ozon API. Используйте ozon_brand_certificates."}

    async def certificate_info(self, certificate_id: int) -> dict:
        return {"error": "Endpoint /v1/certificate/info не существует в публичном Ozon API."}

    # ── Архив ──────────────────────────────────────────────
    async def product_archive(self, product_id: list[int]) -> dict:
        """POST /v1/product/archive — отправить товары в архив."""
        return await self._post("/v1/product/archive", {"product_id": product_id})

    async def close(self):
        await self._http.aclose()


class OzonPerformanceClient:
    """Клиент для Ozon Performance API (реклама).

    Бюджеты и ставки CPC — в МИКРОРУБЛЯХ (1000000 = 1 ₽), строкой.
    Токен живёт 30 минут — обновляется автоматически.
    """

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_at: float = 0.0
        self._http = httpx.AsyncClient(
            base_url=PERF_BASE,
            timeout=60.0,
        )

    async def _ensure_token(self):
        import time as _t
        # Токен живёт 1800 с — обновляем за 60 с до истечения
        if self._token and (_t.monotonic() - self._token_at) < 1740:
            return
        r = await self._http.post(
            "/api/client/token",
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        self._token_at = _t.monotonic()
        self._http.headers["Authorization"] = f"Bearer {self._token}"

    async def _get(self, path: str, params: dict | None = None) -> dict:
        await self._ensure_token()
        r = await self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def _post(self, path: str, body: dict | None = None) -> dict:
        await self._ensure_token()
        r = await self._http.post(path, json=body or {})
        r.raise_for_status()
        return r.json()

    async def _put(self, path: str, body: dict | None = None) -> dict:
        await self._ensure_token()
        r = await self._http.put(path, json=body or {})
        r.raise_for_status()
        return r.json()

    # ── Кампании ───────────────────────────────────────────
    async def campaigns_list(self, campaign_ids: list[int] | None = None,
                             adv_object_type: str | None = None,
                             state: str | None = None,
                             page: int = 1, page_size: int = 100) -> dict:
        """GET /api/client/campaign — список кампаний.

        adv_object_type: SKU (трафареты CPC) | SEARCH_PROMO (оплата за заказ) | BANNER | VIDEO_BANNER.
        state: CAMPAIGN_STATE_RUNNING | _STOPPED (нет бюджета) | _INACTIVE | _PLANNED | _ARCHIVED | _FINISHED.
        Бюджет кампании — в полях budget/dailyBudget/weeklyBudget ответа (микрорубли).
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if campaign_ids:
            params["campaignIds"] = [str(c) for c in campaign_ids]
        if adv_object_type:
            params["advObjectType"] = adv_object_type
        if state:
            params["state"] = state
        return await self._get("/api/client/campaign", params)

    async def campaign_create(self, title: str, placement: str = "PLACEMENT_SEARCH_AND_CATEGORY",
                              autopilot_strategy: str = "MAX_CLICKS",
                              daily_budget_rub: float = 0, weekly_budget_rub: float = 0,
                              from_date: str = "", to_date: str = "") -> dict:
        """POST /api/client/campaign/cpc/v2/product — создать CPC-кампанию (трафареты).

        placement: PLACEMENT_SEARCH_AND_CATEGORY (поиск+рекомендации) | PLACEMENT_TOP_PROMOTION (вывод в топ).
        autopilot_strategy: MAX_CLICKS | TOP_MAX_CLICKS | TARGET_BIDS | TOP_PROMOTION | NO_AUTO_STRATEGY.
        Бюджеты в РУБЛЯХ (конвертируются в микрорубли). Мин. бюджет с 09.2025: 2000 ₽ × SKU.
        """
        body: dict[str, Any] = {
            "title": title,
            "placement": placement,
            "productAutopilotStrategy": autopilot_strategy,
        }
        if daily_budget_rub:
            body["dailyBudget"] = str(int(daily_budget_rub * 1_000_000))
        if weekly_budget_rub:
            body["weeklyBudget"] = str(int(weekly_budget_rub * 1_000_000))
        if from_date:
            body["fromDate"] = from_date
        if to_date:
            body["toDate"] = to_date
        return await self._post("/api/client/campaign/cpc/v2/product", body)

    async def campaign_update(self, campaign_id: int, daily_budget_rub: float | None = None,
                              weekly_budget_rub: float | None = None,
                              from_date: str = "", to_date: str = "") -> dict:
        """PATCH /api/client/campaign/{id} — изменить бюджет/период кампании."""
        body: dict[str, Any] = {}
        if daily_budget_rub is not None:
            body["dailyBudget"] = str(int(daily_budget_rub * 1_000_000))
        if weekly_budget_rub is not None:
            body["weeklyBudget"] = str(int(weekly_budget_rub * 1_000_000))
        if from_date:
            body["fromDate"] = from_date
        if to_date:
            body["toDate"] = to_date
        await self._ensure_token()
        r = await self._http.patch(f"/api/client/campaign/{campaign_id}", json=body)
        r.raise_for_status()
        return r.json()

    async def campaign_activate(self, campaign_id: int) -> dict:
        """POST /api/client/campaign/{id}/activate — запустить кампанию."""
        return await self._post(f"/api/client/campaign/{campaign_id}/activate")

    async def campaign_deactivate(self, campaign_id: int) -> dict:
        """POST /api/client/campaign/{id}/deactivate — остановить кампанию."""
        return await self._post(f"/api/client/campaign/{campaign_id}/deactivate")

    async def campaign_products_list(self, campaign_id: int, page: int = 1, page_size: int = 100) -> dict:
        """GET /api/client/campaign/{id}/v2/products — товары и ставки в кампании."""
        return await self._get(f"/api/client/campaign/{campaign_id}/v2/products",
                               {"page": page, "pageSize": page_size})

    async def campaign_products_add(self, campaign_id: int, bids: list[dict]) -> dict:
        """POST /api/client/campaign/{id}/products — добавить товары (≤500 на кампанию).

        bids: [{"sku": 123, "bid": "10000000"}] — ставка в микрорублях; без bid — конкурентная.
        """
        return await self._post(f"/api/client/campaign/{campaign_id}/products", {"bids": bids})

    async def campaign_products_update(self, campaign_id: int, bids: list[dict]) -> dict:
        """PUT /api/client/campaign/{id}/products — обновить ставки товаров."""
        return await self._put(f"/api/client/campaign/{campaign_id}/products", {"bids": bids})

    async def campaign_products_delete(self, campaign_id: int, skus: list[int]) -> dict:
        """POST /api/client/campaign/{id}/products/delete — убрать товары из кампании."""
        return await self._post(f"/api/client/campaign/{campaign_id}/products/delete",
                                {"sku": [str(s) for s in skus]})

    async def bids_competitive(self, campaign_id: int, skus: list[int]) -> dict:
        """GET /api/client/campaign/{id}/products/bids/competitive — конкурентные ставки (≤200 SKU)."""
        return await self._get(f"/api/client/campaign/{campaign_id}/products/bids/competitive",
                               {"skus": [str(s) for s in skus]})

    async def min_sku_bids(self, skus: list[int], payment_type: str = "CPC") -> dict:
        """POST /api/client/min/sku — минимальные ставки по SKU (CPC | CPO | CPC_TOP), в рублях."""
        return await self._post("/api/client/min/sku", {
            "marketplaceId": "MARKETPLACE_ID_RU", "paymentType": payment_type,
            "sku": [str(s) for s in skus],
        })

    async def limits_list(self) -> dict:
        """GET /api/client/limits/list — мин/макс ставки по типам размещения."""
        return await self._get("/api/client/limits/list")

    async def campaign_objects(self, campaign_id: int) -> dict:
        """GET /api/client/campaign/{id}/objects — продвигаемые объекты кампании."""
        return await self._get(f"/api/client/campaign/{campaign_id}/objects")

    # ── Оплата за заказ (search_promo, бывший «вывод в топ» CPO) ──
    # С 26.02.2025 ставки CPO фиксированные — установка ставок deprecated.

    async def search_promo_products(self, page: int = 1, page_size: int = 100) -> dict:
        """POST /api/client/campaign/search_promo/v2/products — товары в «Оплате за заказ»."""
        return await self._post("/api/client/campaign/search_promo/v2/products",
                                {"page": page, "pageSize": page_size})

    async def search_promo_enable(self, skus: list[int]) -> dict:
        """POST /api/client/search_promo/product/enable — включить продвижение (≤1000 SKU)."""
        return await self._post("/api/client/search_promo/product/enable", {"skus": [str(s) for s in skus]})

    async def search_promo_disable(self, skus: list[int]) -> dict:
        """POST /api/client/search_promo/product/disable — отключить продвижение (≤1000 SKU)."""
        return await self._post("/api/client/search_promo/product/disable", {"skus": [str(s) for s in skus]})

    async def search_promo_cpo_bids(self, skus: list[int]) -> dict:
        """POST /api/client/search_promo/get_cpo_min_bids — фиксированные ставки CPO (≤200 SKU)."""
        return await self._post("/api/client/search_promo/get_cpo_min_bids", {"skus": [str(s) for s in skus]})

    # ── Статистика ─────────────────────────────────────────

    async def statistics(
        self, campaigns: list[int], date_from: str, date_to: str,
        group_by: str = "DATE",
    ) -> Any:
        """Асинхронный отчёт: POST /api/client/statistics/json → poll → report.

        Лимиты: ≤10 кампаний, период ≤62 дня, 1 одновременная выгрузка на аккаунт.
        """
        import asyncio as _aio
        submit = await self._post("/api/client/statistics/json", {
            "campaigns": [str(c) for c in campaigns],
            "dateFrom": date_from, "dateTo": date_to,
            "groupBy": group_by,
        })
        uuid = submit.get("UUID")
        if not uuid:
            return submit
        for _ in range(30):  # до ~2.5 минут
            await _aio.sleep(5)
            status = await self._get(f"/api/client/statistics/{uuid}")
            if status.get("state") == "OK":
                await self._ensure_token()
                r = await self._http.get("/api/client/statistics/report", params={"UUID": uuid})
                r.raise_for_status()
                try:
                    return r.json()
                except Exception:
                    return {"format": "csv", "content": r.text[:50000]}
            if status.get("state") == "ERROR":
                return {"uuid": uuid, "state": "ERROR", "detail": status}
        return {"uuid": uuid, "state": "timeout",
                "hint": f"Отчёт ещё готовится: GET /api/client/statistics/report?UUID={uuid}"}

    async def statistics_daily(self, campaigns: list[int] | None, date_from: str, date_to: str) -> dict:
        """GET /api/client/statistics/daily/json — дневная статистика (синхронно)."""
        params: dict[str, Any] = {"dateFrom": date_from, "dateTo": date_to}
        if campaigns:
            params["campaignIds"] = [str(c) for c in campaigns]
        return await self._get("/api/client/statistics/daily/json", params)

    async def statistics_expenses(self, campaigns: list[int] | None, date_from: str, date_to: str) -> dict:
        """GET /api/client/statistics/expense/json — расходы по кампаниям (синхронно)."""
        params: dict[str, Any] = {"dateFrom": date_from, "dateTo": date_to}
        if campaigns:
            params["campaignIds"] = [str(c) for c in campaigns]
        return await self._get("/api/client/statistics/expense/json", params)

    async def statistics_products(self, campaigns: list[int], date_from: str, date_to: str) -> dict:
        """GET /api/client/statistics/campaign/product/json — статистика CPC-кампаний по товарам: расход, CTR, CPC, заказы, ДРР."""
        return await self._get("/api/client/statistics/campaign/product/json", {
            "campaignIds": [str(c) for c in campaigns],
            "dateFrom": date_from, "dateTo": date_to,
        })

    # ── Баланс ─────────────────────────────────────────────
    async def balance(self) -> dict:
        return {"error": "Официального метода баланса в Performance API нет. Расход с абонентского счёта виден в ozon_ad_statistics_expenses."}

    async def close(self):
        await self._http.aclose()
