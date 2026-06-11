"""HTTP-клиенты для Ozon Seller API и Performance API."""

import httpx
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

    async def _post(self, path: str, body: dict | None = None) -> dict:
        r = await self._http.post(path, json=body or {})
        r.raise_for_status()
        return r.json()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        r = await self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    # ── Акции ──────────────────────────────────────────────
    async def actions_list(self) -> dict:
        """GET /v1/actions — список доступных акций."""
        return await self._get("/v1/actions")

    async def actions_candidates(self, action_id: int) -> dict:
        """POST /v1/actions/candidates — товары-кандидаты в акцию."""
        return await self._post("/v1/actions/candidates", {"action_id": action_id})

    async def actions_products(self, action_id: int) -> dict:
        """POST /v1/actions/products — товары уже в акции."""
        return await self._post("/v1/actions/products", {"action_id": action_id})

    async def actions_products_activate(
        self, action_id: int, products: list[dict]
    ) -> dict:
        """POST /v1/actions/products/activate — добавить/убрать товар из акции."""
        return await self._post(
            "/v1/actions/products/activate",
            {"action_id": action_id, "products": products},
        )

    # ── Ценовые стратегии ──────────────────────────────────
    async def pricing_strategy_list(self, product_id: list[int]) -> dict:
        return {"error": "Endpoint /v1/pricing/strategy/list не существует в публичном Ozon API. Управление стратегиями доступно только через интерфейс Ozon."}

    async def pricing_strategy_create(self, strategy: dict) -> dict:
        return {"error": "Endpoint не существует в публичном Ozon API."}

    async def pricing_strategy_update(self, strategy: dict) -> dict:
        return {"error": "Endpoint не существует в публичном Ozon API."}

    async def pricing_strategy_delete(self, strategy_id: int) -> dict:
        return {"error": "Endpoint не существует в публичном Ozon API."}

    async def pricing_currency_convert(self, currency_from: str, currency_to: str, amount: float) -> dict:
        return {"error": "Endpoint /v1/pricing/currency/convert не существует в публичном Ozon API."}

    async def pricing_competitor_prices(self, product_id: list[int]) -> dict:
        return {"error": "Endpoint /v1/pricing/competitor/prices не существует в публичном Ozon API. Анализ конкурентов доступен только через интерфейс Ozon Seller."}

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
    async def finance_transaction_list(
        self, date_from: str, date_to: str, page: int = 1, page_size: int = 50,
        operation_type: list[str] | None = None,
    ) -> dict:
        """POST /v3/finance/transaction/list — финансовые транзакции."""
        body: dict[str, Any] = {
            "filter": {
                "date": {"from": date_from, "to": date_to},
            },
            "page": page,
            "page_size": page_size,
        }
        if operation_type:
            body["filter"]["operation_type"] = operation_type
        return await self._post("/v3/finance/transaction/list", body)

    async def finance_transaction_totals(
        self, date_from: str, date_to: str
    ) -> dict:
        """POST /v3/finance/transaction/totals — итоги финансов за период.

        Тело: {date, posting_number, transaction_type} (НЕ filter!).
        """
        return await self._post(
            "/v3/finance/transaction/totals",
            {"date": {"from": date_from, "to": date_to},
             "posting_number": "", "transaction_type": "all"},
        )

    async def finance_realization(self, date: str) -> dict:
        """POST /v1/finance/realization — отчёт о реализации за месяц (формат YYYY-MM)."""
        return await self._post("/v1/finance/realization", {"date": date})

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

    async def review_comment_update(self, review_id: str, comment_id: str, text: str) -> dict:
        """POST /v1/review/comment/update — обновить ответ на отзыв."""
        return await self._post("/v1/review/comment/update", {"review_id": review_id, "comment_id": comment_id, "text": text})

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
        """POST /v4/products/info/attributes — атрибуты товаров (включая бренд)."""
        body: dict[str, Any] = {"limit": limit, "last_id": last_id}
        filt: dict[str, Any] = {}
        if offer_id:
            filt["offer_id"] = offer_id
        if product_id:
            filt["product_id"] = product_id
        if filt:
            body["filter"] = filt
        return await self._post("/v4/products/info/attributes", body)

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

    async def product_delete(self, product_id: list[int]) -> dict:
        """POST /v2/products/delete — удалить товары без продаж."""
        return await self._post("/v2/products/delete", {"product_id": product_id})

    async def product_info_limit(self) -> dict:
        """POST /v4/product/info/limit — лимиты на создание товаров."""
        return await self._post("/v4/product/info/limit", {})

    async def product_rating_by_sku(self, skus: list[int]) -> dict:
        """POST /v1/product/rating-by-sku — рейтинг контента товаров."""
        return await self._post("/v1/product/rating-by-sku", {"skus": skus})

    async def product_info_discounted(self, product_id: list[int]) -> dict:
        """POST /v1/product/info/discounted — уценённые товары."""
        return await self._post("/v1/product/info/discounted", {"product_id": product_id})

    # ── Заказы FBO ─────────────────────────────────────────
    async def posting_fbo_list(
        self, since: str, to: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """POST /v2/posting/fbo/list — заказы FBO."""
        return await self._post(
            "/v2/posting/fbo/list",
            {"dir": "DESC", "filter": {"since": since, "to": to},
             "limit": limit, "offset": offset, "with": {"analytics_data": True}},
        )

    # ── Заказы FBS ─────────────────────────────────────────
    async def posting_fbs_list(self, since: str, to: str, limit: int = 50, offset: int = 0, status: str = "") -> dict:
        """POST /v3/posting/fbs/list — заказы FBS."""
        body: dict[str, Any] = {
            "dir": "DESC",
            "filter": {"since": since, "to": to},
            "limit": limit, "offset": offset,
            "with": {"analytics_data": True, "financial_data": True},
        }
        if status:
            body["filter"]["status"] = status
        return await self._post("/v3/posting/fbs/list", body)

    async def posting_fbs_get(self, posting_number: str) -> dict:
        """POST /v3/posting/fbs/get — детали отправления FBS."""
        return await self._post("/v3/posting/fbs/get", {"posting_number": posting_number, "with": {"analytics_data": True, "financial_data": True}})

    async def posting_fbs_ship(self, posting_number: str, packages: list[dict]) -> dict:
        """POST /v3/posting/fbs/ship — отгрузить FBS."""
        return await self._post("/v3/posting/fbs/ship", {"posting_number": posting_number, "packages": packages})

    async def posting_fbs_act_create(self, containers_count: int = 1) -> dict:
        """POST /v2/posting/fbs/act/create — создать акт приёма-передачи."""
        return await self._post("/v2/posting/fbs/act/create", {"containers_count": containers_count})

    async def posting_fbs_act_check_status(self, id: int) -> dict:
        """POST /v2/posting/fbs/act/check-status — статус формирования акта."""
        return await self._post("/v2/posting/fbs/act/check-status", {"id": id})

    async def posting_fbs_act_get_pdf(self, id: int) -> dict:
        """POST /v2/posting/fbs/act/get-pdf — скачать PDF акта."""
        return await self._post("/v2/posting/fbs/act/get-pdf", {"id": id})

    async def posting_fbs_digital_act_create(self, id: int) -> dict:
        """POST /v2/posting/fbs/digital/act/create — создать электронный акт."""
        return await self._post("/v2/posting/fbs/digital/act/create", {"id": id})

    async def posting_fbs_cancel(self, posting_number: str, cancel_reason_id: int, cancel_reason_message: str = "") -> dict:
        """POST /v2/posting/fbs/cancel — отменить FBS отправление."""
        return await self._post("/v2/posting/fbs/cancel", {"posting_number": posting_number, "cancel_reason_id": cancel_reason_id, "cancel_reason_message": cancel_reason_message})

    async def posting_fbs_cancel_reasons(self) -> dict:
        """POST /v2/posting/fbs/cancel-reason/list — причины отмены FBS."""
        return await self._post("/v2/posting/fbs/cancel-reason/list", {})

    async def posting_fbs_product_country_list(self, posting_number: str) -> dict:
        """POST /v1/posting/fbs/product/country/list — страны для отправления."""
        return await self._post("/v1/posting/fbs/product/country/list", {"posting_number": posting_number})

    async def posting_fbs_product_country_set(self, posting_number: str, product_id: int, country_iso: str) -> dict:
        """POST /v1/posting/fbs/product/country/set — указать страну товара."""
        return await self._post("/v1/posting/fbs/product/country/set", {"posting_number": posting_number, "product_id": product_id, "country_iso_code": country_iso})

    async def posting_fbs_restrictions(self, posting_number: list[str]) -> dict:
        """POST /v1/posting/fbs/restrictions — ограничения отправлений."""
        return await self._post("/v1/posting/fbs/restrictions", {"posting_number": posting_number})

    async def posting_fbs_timeslot_change(self, posting_number: str, new_timeslot_id: int) -> dict:
        """POST /v1/posting/fbs/timeslot/change — изменить тайм-слот."""
        return await self._post("/v1/posting/fbs/timeslot/change", {"posting_number": posting_number, "new_timeslot_id": new_timeslot_id})

    async def posting_fbo_get(self, posting_number: str) -> dict:
        """POST /v2/posting/fbo/get — детали FBO отправления."""
        return await self._post("/v2/posting/fbo/get", {"posting_number": posting_number, "with": {"analytics_data": True, "financial_data": True}})

    # ── Возвраты ───────────────────────────────────────────
    async def returns_fbo_list(self, filter_params: dict, limit: int = 50, offset: int = 0) -> dict:
        """POST /v3/returns/company/fbo — возвраты FBO."""
        return await self._post("/v3/returns/company/fbo", {"filter": filter_params, "limit": limit, "offset": offset})

    async def returns_fbs_list(self, filter_params: dict, limit: int = 50, offset: int = 0) -> dict:
        """POST /v3/returns/company/fbs — возвраты FBS."""
        return await self._post("/v3/returns/company/fbs", {"filter": filter_params, "limit": limit, "offset": offset})

    async def returns_fbs_approve(self, return_id: int) -> dict:
        """POST /v1/returns/fbs/approve — одобрить возврат FBS."""
        return await self._post("/v1/returns/fbs/approve", {"return_id": return_id})

    async def returns_fbs_reject(self, return_id: int, reason: str) -> dict:
        """POST /v1/returns/fbs/reject — отклонить возврат FBS."""
        return await self._post("/v1/returns/fbs/reject", {"return_id": return_id, "rejection_reason": reason})

    async def returns_fbs_get(self, return_id: int) -> dict:
        """POST /v1/returns/fbs/get — детали возврата FBS."""
        return await self._post("/v1/returns/fbs/get", {"return_id": return_id})

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

    async def question_reply(self, question_id: str, text: str) -> dict:
        """POST /v1/question/reply — ответить на вопрос."""
        return await self._post("/v1/question/reply", {"question_id": question_id, "text": text})

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

    # ── Отмены ─────────────────────────────────────────────
    async def conditional_cancellation_list(self, posting_number: str = "", status: str = "ON_APPROVAL", page: int = 1, page_size: int = 50) -> dict:
        """POST /v1/conditional-cancellation/list — заявки на отмену покупателем."""
        body: dict[str, Any] = {"filter": {"status": status}, "paging": {"page": page, "page_size": page_size}}
        if posting_number:
            body["filter"]["posting_number"] = posting_number
        return await self._post("/v1/conditional-cancellation/list", body)

    async def conditional_cancellation_approve(self, cancellation_id: int, comment: str = "") -> dict:
        """POST /v1/conditional-cancellation/approve — одобрить отмену."""
        body: dict[str, Any] = {"cancellation_id": cancellation_id}
        if comment:
            body["comment"] = comment
        return await self._post("/v1/conditional-cancellation/approve", body)

    async def conditional_cancellation_reject(self, cancellation_id: int, comment: str = "") -> dict:
        """POST /v1/conditional-cancellation/reject — отклонить отмену."""
        return await self._post("/v1/conditional-cancellation/reject", {"cancellation_id": cancellation_id, "comment": comment})

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

    async def report_stocks_create(self, language: str = "DEFAULT") -> dict:
        """POST /v1/report/stocks/create — создать отчёт по остаткам."""
        return await self._post("/v1/report/stocks/create", {"language": language})

    async def report_finance_create(self, date_from: str, date_to: str) -> dict:
        """POST /v1/report/finance/create — создать финансовый отчёт."""
        return await self._post("/v1/report/finance/create", {"filter": {"date_from": date_from, "date_to": date_to}})

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

    # ── Уведомления ────────────────────────────────────────
    async def notification_list(self, limit: int = 50, offset: int = 0) -> dict:
        """POST /v1/notification/list — список уведомлений."""
        return await self._post("/v1/notification/list", {"limit": limit, "offset": offset})

    async def notification_mark_read(self, notification_ids: list[str]) -> dict:
        """POST /v1/notification/mark-as-read — пометить уведомления как прочитанные."""
        return await self._post("/v1/notification/mark-as-read", {"notification_ids": notification_ids})

    # ── Хочу скидку ────────────────────────────────────────
    async def discount_task_list(self, limit: int = 50, offset: int = 0) -> dict:
        return {"error": "Endpoint /v1/discount/task/list не существует в публичном Ozon API."}

    async def discount_task_approve(self, task_id: int, price: float) -> dict:
        return {"error": "Endpoint не существует в публичном Ozon API."}

    async def discount_task_decline(self, task_id: int) -> dict:
        return {"error": "Endpoint не существует в публичном Ozon API."}

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
    """Клиент для Ozon Performance API (реклама)."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._http = httpx.AsyncClient(
            base_url=PERF_BASE,
            timeout=30.0,
        )

    async def _ensure_token(self):
        if self._token:
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
    async def campaigns_list(self) -> dict:
        """GET /api/client/campaign — список рекламных кампаний."""
        return await self._get("/api/client/campaign")

    async def campaign_create(self, title: str, campaign_type: str, products: list[dict], daily_budget: float = 0) -> dict:
        """POST /api/client/campaign — создать рекламную кампанию."""
        body = {"title": title, "type": campaign_type, "products": products}
        if daily_budget:
            body["dailyBudget"] = daily_budget
        return await self._post("/api/client/campaign", body)

    async def campaign_activate(self, campaign_id: int) -> dict:
        """POST /api/client/campaign/{id}/activate — запустить кампанию."""
        return await self._post(f"/api/client/campaign/{campaign_id}/activate")

    async def campaign_deactivate(self, campaign_id: int) -> dict:
        """POST /api/client/campaign/{id}/deactivate — остановить кампанию."""
        return await self._post(f"/api/client/campaign/{campaign_id}/deactivate")

    async def campaign_update_bids(self, campaign_id: int, bids: list[dict]) -> dict:
        """PUT /api/client/campaign/{id}/bids — обновить ставки."""
        return await self._put(f"/api/client/campaign/{campaign_id}/bids", {"bids": bids})

    async def campaign_budget(self, campaign_id: int) -> dict:
        """GET /api/client/campaign/{id}/budget — бюджет кампании."""
        return await self._get(f"/api/client/campaign/{campaign_id}/budget")

    async def campaign_update_budget(self, campaign_id: int, daily_budget: float, total_budget: float = 0) -> dict:
        """PUT /api/client/campaign/{id}/budget — обновить бюджет."""
        body: dict = {"dailyBudget": daily_budget}
        if total_budget:
            body["totalBudget"] = total_budget
        return await self._put(f"/api/client/campaign/{campaign_id}/budget", body)

    async def campaign_objects(self, campaign_id: int) -> dict:
        """GET /api/client/campaign/{id}/objects — товары и ставки в кампании."""
        return await self._get(f"/api/client/campaign/{campaign_id}/objects")

    async def campaign_objects_update(self, campaign_id: int, objects: list[dict]) -> dict:
        """PUT /api/client/campaign/{id}/objects — обновить товары в кампании."""
        return await self._put(f"/api/client/campaign/{campaign_id}/objects", {"objects": objects})

    # ── Статистика ─────────────────────────────────────────
    async def statistics(
        self, campaigns: list[int], date_from: str, date_to: str,
        group_by: str = "DATE",
    ) -> dict:
        """POST /api/client/statistics — статистика по кампаниям."""
        return await self._post(
            "/api/client/statistics",
            {
                "campaigns": campaigns,
                "dateFrom": date_from,
                "dateTo": date_to,
                "groupBy": group_by,
            },
        )

    async def statistics_daily(self, campaigns: list[int], date_from: str, date_to: str) -> dict:
        """POST /api/client/statistics/daily — ежедневная статистика."""
        return await self._post("/api/client/statistics/daily", {"campaigns": campaigns, "dateFrom": date_from, "dateTo": date_to})

    async def statistics_expenses(self, campaigns: list[int], date_from: str, date_to: str) -> dict:
        """POST /api/client/statistics/expenses — расходы по кампаниям."""
        return await self._post("/api/client/statistics/expenses", {"campaigns": campaigns, "dateFrom": date_from, "dateTo": date_to})

    # ── Баланс ─────────────────────────────────────────────
    async def balance(self) -> dict:
        return {"error": "Endpoint /api/client/balance не существует в Performance API."}

    async def close(self):
        await self._http.aclose()
