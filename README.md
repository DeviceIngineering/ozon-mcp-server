# Ozon MCP Server

MCP-сервер для управления несколькими магазинами Ozon через Claude. Подключается к **Seller API** (товары, цены, акции, финансы, аналитика) и **Performance API** (реклама).

**Поддержка нескольких магазинов** — каждый вызов принимает `shop_id`, что позволяет работать с разными аккаунтами Ozon в одном диалоге.

## 114 инструментов

| Раздел | Инструменты | Приоритет |
|--------|-------------|-----------|
| Магазины | ozon_list_shops | — |
| Акции | ozon_actions_list, ozon_actions_candidates, ozon_actions_products, ozon_actions_activate | P0 |
| Ценовые стратегии | ozon_pricing_strategy_list/create/update/delete, ozon_pricing_currency_convert, ozon_pricing_competitor_prices | P0 |
| Цены | ozon_set_prices, ozon_get_prices, ozon_get_prices_v4, ozon_min_price_timer_status/renew | P0 |
| Финансы | ozon_finance_transactions, ozon_finance_totals, ozon_finance_realization, ozon_finance_cash_flow | P0 |
| Рейтинг | ozon_rating_summary, ozon_rating_history | P0 |
| Отзывы | ozon_reviews, ozon_review_reply, ozon_review_reply_update, ozon_review_reply_delete | P0 |
| Реклама | ozon_ad_campaigns, ozon_ad_statistics, ozon_ad_campaign_stop/create/activate, ozon_ad_campaign_bids, ozon_ad_campaign_budget/update, ozon_ad_statistics_daily/expenses, ozon_ad_campaign_objects/update, ozon_ad_balance | P0-P1 |
| Аналитика | ozon_analytics, ozon_stock_on_warehouses | P1 |
| Товары | ozon_product_list, ozon_product_info, ozon_product_attributes, ozon_product_stocks, ozon_product_certificates | P1 |
| Импорт товаров | ozon_product_import, ozon_product_import_info, ozon_product_update_offer_id/images, ozon_product_description, ozon_product_update_stocks, ozon_product_geo_restrictions, ozon_product_unarchive/delete, ozon_product_limits, ozon_product_rating_by_sku, ozon_product_discounted | P1 |
| Заказы FBS | ozon_orders_fbs, ozon_order_fbs_get/ship/cancel, ozon_order_fbs_cancel_reasons, ozon_order_fbs_act_create/status/pdf/digital, ozon_order_fbs_country_list/set, ozon_order_fbs_restrictions/timeslot, ozon_order_fbo_get | P1 |
| Заказы FBO | ozon_orders_fbo | P1 |
| Возвраты | ozon_returns_fbo, ozon_returns_fbs, ozon_returns_fbs_approve/reject/get, ozon_returns_report | P1 |
| Вопросы | ozon_questions, ozon_question_reply | P1 |
| Чаты | ozon_chat_list, ozon_chat_history, ozon_chat_send, ozon_chat_send_file, ozon_chat_updates, ozon_chat_start, ozon_chat_read | P1 |
| Отмены | ozon_cancellation_list, ozon_cancellation_approve/reject | P1 |
| Склады | ozon_warehouse_list, ozon_delivery_methods | P2 |
| Отчёты | ozon_report_list, ozon_report_info, ozon_report_products/stocks/finance/discounted_create | P1 |
| Бренды | ozon_brand_certificates | P2 |
| Категории | ozon_category_tree, ozon_category_attributes, ozon_category_attribute_values/search | P2 |
| Уведомления | ozon_notifications, ozon_notification_read | P1 |
| Скидки | ozon_discount_tasks, ozon_discount_approve/decline | P0 |
| Компания | ozon_company_info, ozon_company_tariffs | P2 |
| Сертификаты | ozon_certificate_list, ozon_certificate_info | P2 |
| Архив | ozon_product_archive | P2 |

## Запуск через Docker

```bash
./start.sh
```

После запуска:
- **Dashboard**: http://localhost:8000
- **Магазины**: http://localhost:8000/shops
- **Health**: http://localhost:8000/api/health
- **MCP SSE**: http://localhost:8000/sse

## Подключение к Claude Desktop

Файл `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8001/sse"]
    },
    "ozon": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/sse"]
    }
  }
}
```

После редактирования — полный перезапуск Claude Desktop (Cmd+Q → открыть).

## Добавление магазинов

Открыть http://localhost:8000/shops → «Добавить магазин» → ввести ключи → «Проверить».

Ключи шифруются (Fernet) и хранятся в Docker volume `/data`.

### Ключи Seller API
- **OZON_CLIENT_ID** + **OZON_API_KEY** → Ozon Seller ЛК → Настройки → API-ключи

### Ключи Performance API (реклама)
- **OZON_PERF_CLIENT_ID** + **OZON_PERF_CLIENT_SECRET** → Ozon Performance → Настройки → API доступ

### Через переменные окружения (один магазин `default`)

```bash
OZON_CLIENT_ID=123456
OZON_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
OZON_PERF_CLIENT_ID=987654
OZON_PERF_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyyyyyy
```

## Структура проекта

```
ozon-mcp-server/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml          # порт 8000
├── config/
│   ├── claude_desktop_config.json
│   └── claude_code_settings.json
└── ozon_mcp/
    ├── server.py       # MCP-сервер (114 инструментов, мульти-магазин)
    ├── client.py       # HTTP-клиенты Ozon Seller + Performance API
    ├── app.py          # FastAPI (SSE + веб-интерфейс)
    ├── settings.py     # Управление магазинами и ключами (Fernet)
    ├── stats.py        # Статистика вызовов (SQLite)
    └── templates/      # PicoCSS, dashboard + shops
```
