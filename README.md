# Ozon MCP Server v2.0

MCP-сервер для управления несколькими магазинами Ozon через Claude / OpenClaw.
**Seller API** (товары, цены, акции, финансы, аналитика) + **Performance API** (реклама).
151 инструмент, мульти-магазин, веб-дашборд, встроенная диагностика Ozon API.

Эндпоинты приведены в соответствие с актуальным Ozon API (июнь 2026, сверка
живыми запросами): единый список возвратов, отмены v2, реализация v2, ship v4,
supply-order v3, реальные ценовые стратегии и «Хочу скидку», собственные акции
продавца, новая модель рекламы (трафареты CPC + «Оплата за заказ»).

**Поддержка нескольких магазинов** — каждый вызов принимает `shop_id`.

## 151 инструмент

| Раздел | Ключевые инструменты | Приоритет |
|--------|-------------|-----------|
| Магазины | ozon_list_shops | — |
| Диагностика | ozon_diagnostics, ozon_degradations | P0 |
| Акции Ozon | ozon_actions_list/candidates/products, activate, deactivate | P0 |
| Собственные акции | ozon_seller_actions, ozon_seller_action_create/toggle/products(+add/delete) | P1 |
| Ценовые стратегии | ozon_pricing_strategy_list/create/info/update/delete/status/products, ozon_pricing_competitors, ozon_pricing_competitor_prices | P1 |
| Цены | ozon_set_prices, ozon_get_prices (v5), ozon_min_price_timer_status/renew | P0 |
| «Хочу скидку» | ozon_discount_tasks (v2), ozon_discount_approve/decline | P1 |
| Финансы | ozon_finance_balance, ozon_finance_transactions*, ozon_finance_totals*, ozon_finance_realization (v2), ozon_finance_cash_flow, ozon_finance_mutual_settlement, ozon_finance_accruals | P0 |
| Реклама (Performance) | ozon_ad_campaigns, ozon_ad_campaign_create (трафареты), activate/stop, budget_update, ozon_ad_campaign_products(+add/delete), bids, bids_competitive, min_bids, статистика (async + daily/expenses/products) | P0 |
| Оплата за заказ | ozon_search_promo_products/enable/disable/bids | P0 |
| Аналитика | ozon_analytics, ozon_analytics_stocks, ozon_stock_on_warehouses, ozon_product_queries (позиции в поиске), ozon_search_queries_top | P0-P1 |
| Товары | ozon_product_list/info/attributes/stocks, create/import, attributes_update, import_by_sku, media, описание, архив, rating-by-sku | P1 |
| Заказы FBO | ozon_orders_fbo, ozon_order_fbo_get | P1 |
| Поставки FBO | ozon_supply_orders (v3), ozon_supply_order_get/counters/timeslots | P1 |
| Заказы FBS | ozon_orders_fbs, unfulfilled, get, ship (v4), label, cancel, акты, страна товара | P1 |
| Возвраты | ozon_returns_fbo (единый список), ozon_returns_fbs (rFBS-заявки), approve/reject, ozon_returns_rfbs_action | P1 |
| Отмены | ozon_cancellation_list (v2), approve/reject | P1 |
| Отзывы/Вопросы | ozon_reviews, ozon_review_reply, ozon_review_comments, ozon_questions, ozon_question_reply — требуют Premium Plus | P1 |
| Чаты | ozon_chat_list (v3), history (v3), send, read | P1 |
| Рейтинг | ozon_rating_summary, ozon_rating_history | P1 |
| Склады/Отчёты | ozon_warehouses (v2), ozon_delivery_methods (v2), report_* | P2 |
| Push-вебхуки | ozon_notifications, ozon_notification_push_types | P2 |

\* `ozon_finance_transactions/totals` — Ozon отключает старый эндпоинт 06.07.2026; замена уже встроена (`cash_flow`, `accruals`).

## Диагностика

- Страница **`/diagnostics`**: статус по каждому магазину — доступность хостов,
  12 проб категорий Seller API, проверка ключей Performance API, история проверок.
- Фоновая автопроверка каждые `HEALTH_CHECK_INTERVAL_MIN` минут (по умолчанию 30).
- Детектор деградаций: инструмент работал → стабильно падает = алерт «возможно
  Ozon изменил API» на дашборде.
- MCP-инструменты: `ozon_diagnostics`, `ozon_degradations`.
- Особенности Ozon: ключи не содержат срока действия (истечение ловится по 401);
  403 на отзывах/вопросах = нет подписки Premium Plus (не считается поломкой).

## Запуск через Docker

```bash
cp .env.example .env   # задать MCP_AUTH_TOKEN при внешнем доступе
docker compose up -d --build
```

После запуска:
- **Dashboard**: http://localhost:8000
- **Диагностика**: http://localhost:8000/diagnostics
- **Магазины**: http://localhost:8000/shops
- **Health**: http://localhost:8000/api/health
- **MCP SSE**: http://localhost:8000/sse

Деплой на отдельный Mac mini и подключение OpenClaw — см. **[DEPLOY.md](DEPLOY.md)**.

## Подключение клиентов

Claude Code:

```bash
claude mcp add --transport sse ozon "http://<host>:8000/sse" \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

OpenClaw / другие MCP-клиенты — SSE URL `http://<host>:8000/sse` + заголовок
`Authorization: Bearer <MCP_AUTH_TOKEN>` (или `?token=...`).

## Добавление магазинов

http://localhost:8000/shops → «Добавить магазин» → Client-Id + Api-Key (Seller API)
и Client-Id + Client-Secret (Performance API). Ключи шифруются (Fernet), хранятся в томе `/data`.

## Структура проекта

```
ozon-mcp-server/
├── docker-compose.yml          # порт 8000
├── DEPLOY.md                   # деплой на отдельный Mac mini + OpenClaw
└── ozon_mcp/
    ├── server.py       # MCP-сервер (151 инструмент, мульти-магазин)
    ├── client.py       # Seller API + Performance API клиенты
    ├── app.py          # FastAPI (SSE + веб + авторизация + health-loop)
    ├── diagnostics.py  # пробы категорий, детектор деградаций
    ├── settings.py     # магазины и ключи (Fernet)
    ├── stats.py        # статистика вызовов + история проверок (SQLite)
    └── templates/      # dashboard, diagnostics, shops
```

## Известные ограничения Ozon API (июнь 2026)

- Реклама: бюджеты и ставки CPC — в микрорублях (1000000 = 1 ₽); создание кампаний
  через API — только «Трафареты» (CPC); асинхронная статистика — 1 отчёт одновременно,
  ≤10 кампаний, ≤62 дня; официального метода баланса рекламы нет.
- «Оплата за заказ»: ставки фиксированные (с 02.2025), управление — только вкл/выкл.
- Отзывы, вопросы, часть аналитики — требуют подписку Premium Plus (ошибка code 7).
- Метрики воронки в ozon_analytics помечены Ozon как deprecated — для позиций
  в поиске используйте ozon_product_queries.
- /v3/finance/transaction/* отключаются 06.07.2026.
- supply-order v3: статусы — целочисленные коды 1-8.

## Лицензия

MIT — см. [LICENSE](LICENSE).
