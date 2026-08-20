# Справочник инструментов

Всего инструментов: **151**.

Список сгенерирован из `ozon_mcp/server.py` (константа `TOOLS`) — он же отдаётся
клиенту в ответ на `tools/list`. Метки `[P0]`…`[P3]` — приоритет инструмента для
бизнеса: P0 — прямые денежные потери, P1 — операционные метрики, P2 — справочники,
P3 — администрирование.

Каждый инструмент, кроме `ozon_list_shops`, принимает обязательный параметр
`shop_id` (см. `ozon_list_shops`). Звёздочкой отмечены обязательные параметры.

## Магазины

1. **`ozon_list_shops`** — Список зарегистрированных магазинов Ozon. Возвращает shop_id и название каждого магазина. Используй shop_id из этого списка для всех остальных инструментов.

## Акции

2. **`ozon_actions_list`** — [P0] Список всех доступных акций Ozon. Показывает какие акции сейчас активны и какие товары могут быть затянуты. КРИТИЧНО: товары в акциях могут продаваться ниже себестоимости.
3. **`ozon_actions_candidates`** — [P0] Товары-кандидаты в акцию — какие товары Ozon ПЛАНИРУЕТ затянуть в акцию. Упреждающий мониторинг для защиты от продажи в минус.  
   Параметры: `action_id`*
4. **`ozon_actions_products`** — [P0] Товары уже УЧАСТВУЮЩИЕ в акции. Показывает какие товары сейчас продаются по акционной цене.  
   Параметры: `action_id`*
5. **`ozon_actions_activate`** — [P0] Добавить товары в акцию с указанной акционной ценой.  
   Параметры: `action_id`*, `products`*
6. **`ozon_actions_deactivate`** — [P0] УБРАТЬ товары из акции. Используй для вывода убыточных товаров из акции.  
   Параметры: `action_id`*, `product_ids`*

## Собственные акции продавца

7. **`ozon_seller_actions`** — [P1] Список СОБСТВЕННЫХ акций продавца (создаются продавцом, в отличие от акций Ozon).  
   Параметры: `status`, `limit`
8. **`ozon_seller_action_create`** — [P1] Создать собственную акцию-скидку.  
   Параметры: `title`*, `date_start`*, `date_end`*, `min_action_percent`*
9. **`ozon_seller_action_toggle`** — [P1] Включить/выключить собственную акцию.  
   Параметры: `action_id`*, `is_turn_on`*
10. **`ozon_seller_action_products`** — [P1] Товары собственной акции.  
   Параметры: `action_id`*, `limit`
11. **`ozon_seller_action_products_add`** — [P1] Добавить товары в собственную акцию.  
   Параметры: `action_id`*, `products`*
12. **`ozon_seller_action_products_delete`** — [P1] Убрать товары из собственной акции.  
   Параметры: `action_id`*, `product_ids`*

## Ценовые стратегии

13. **`ozon_pricing_strategy_list`** — [P1] Список ценовых стратегий (автоуправление ценами по конкурентам).  
   Параметры: `page`, `limit`
14. **`ozon_pricing_strategy_create`** — [P1] Создать ценовую стратегию. competitors: [{competitor_id, coefficient}] (коэффициент 0.5-1.2 от цены конкурента).  
   Параметры: `name`*, `competitors`*
15. **`ozon_pricing_strategy_info`** — [P2] Детали ценовой стратегии.  
   Параметры: `strategy_id`*
16. **`ozon_pricing_strategy_update`** — [P1] Обновить ценовую стратегию.  
   Параметры: `strategy_id`*, `name`*, `competitors`*
17. **`ozon_pricing_strategy_delete`** — [P2] Удалить ценовую стратегию.  
   Параметры: `strategy_id`*
18. **`ozon_pricing_strategy_status`** — [P1] Включить/выключить ценовую стратегию.  
   Параметры: `strategy_id`*, `enabled`*
19. **`ozon_pricing_strategy_products`** — [P1] Товары стратегии: action=list | add | delete.  
   Параметры: `action`*, `strategy_id`, `product_ids`
20. **`ozon_pricing_competitors`** — [P1] Список конкурентов (товары с других площадок) для ценовых стратегий.  
   Параметры: `page`, `limit`
21. **`ozon_pricing_competitor_prices`** — [P1] Цена товара у конкурента (для товаров в стратегиях).  
   Параметры: `product_id`*

## Цены

22. **`ozon_set_prices`** — [P0] Установить/обновить цены на товары. КРИТИЧНО: используй min_price для защиты от акций ниже себестоимости.  
   Параметры: `prices`*
23. **`ozon_get_prices`** — [P0] Получить текущие цены, скидки, мин. цену и индекс цен. price_index > 1.15 = риск карантина.  
   Параметры: `offer_id`, `product_id`, `limit`
24. **`ozon_get_prices_v4`** — [P1] Получить цены через v4 API (включает purchase_price/себестоимость).  
   Параметры: `offer_id`, `limit`
25. **`ozon_min_price_timer_status`** — [P0] Статус таймера минимальной цены (30 дней). Если истёк — товар уязвим для акций ниже себестоимости!  
   Параметры: `product_id`*
26. **`ozon_min_price_timer_renew`** — [P0] Продлить таймер минимальной цены на 30 дней.  
   Параметры: `product_id`*

## Финансы

27. **`ozon_finance_transactions`** — [P0] Финансовые транзакции: комиссии, логистика, хранение, возвраты — ВСЕ расходы по каждой продаже.  
   Параметры: `date_from`*, `date_to`*, `page`, `page_size`, `operation_type`
28. **`ozon_finance_totals`** — [P0] Итоги финансов за период: суммарные комиссии, логистика, хранение.  
   Параметры: `date_from`*, `date_to`*
29. **`ozon_finance_realization`** — [P1] Отчёт о реализации за месяц (v2).  
   Параметры: `month`*, `year`*
30. **`ozon_finance_mutual_settlement`** — [P1] Отчёт о взаиморасчётах за месяц.  
   Параметры: `date`*
31. **`ozon_finance_accruals`** — [P1] Начисления по дням.  
   Параметры: `date`*
32. **`ozon_finance_balance`** — [P0] Баланс продавца за период: входящий/исходящий остаток, начисления, выплаты (Beta). Без дат — последние 30 дней.  
   Параметры: `date_from`, `date_to`
33. **`ozon_finance_cash_flow`** — [P1] Движение денежных средств.  
   Параметры: `date_from`*, `date_to`*

## Рейтинг

34. **`ozon_rating_summary`** — [P0] Рейтинг продавца. Влияет на позиции в выдаче, доступ к акциям, стоимость хранения.
35. **`ozon_rating_history`** — [P1] История изменения рейтинга.  
   Параметры: `date_from`*, `date_to`*

## Отзывы

36. **`ozon_reviews`** — [P0] Список отзывов на товары. Негатив снижает конверсию.  
   Параметры: `sku`, `limit`
37. **`ozon_review_reply`** — Ответить на отзыв.  
   Параметры: `review_id`*, `text`*
38. **`ozon_review_comments`** — Комментарии к отзыву (метода «обновить ответ» в Ozon API нет — удалите и создайте заново).  
   Параметры: `review_id`*, `limit`
39. **`ozon_review_reply_delete`** — Удалить ответ на отзыв.  
   Параметры: `review_id`*, `comment_id`*

## Реклама

40. **`ozon_ad_campaigns`** — [P0] Список рекламных кампаний: бюджеты (микрорубли: 1000000=1₽), статусы. adv_object_type: SKU (трафареты) | SEARCH_PROMO (оплата за заказ) | BANNER. state: CAMPAIGN_STATE_RUNNING | _STOPPED | _INACTIVE.  
   Параметры: `campaign_ids`, `adv_object_type`, `state`
41. **`ozon_ad_statistics`** — [P0] Статистика по кампаниям (асинхронный отчёт Ozon, ожидание до ~2 мин). ЛИМИТ: ≤10 кампаний, период ≤62 дня, 1 отчёт одновременно.  
   Параметры: `campaigns`*, `date_from`*, `date_to`*, `group_by`
42. **`ozon_ad_campaign_stop`** — [P0] Экстренная остановка рекламной кампании.  
   Параметры: `campaign_id`*
43. **`ozon_ad_campaign_objects`** — [P1] Товары и ставки внутри рекламной кампании.  
   Параметры: `campaign_id`*
44. **`ozon_ad_campaign_create`** — [P1] Создать CPC-кампанию «Трафареты» (единственный тип, создаваемый через API). placement: PLACEMENT_SEARCH_AND_CATEGORY | PLACEMENT_TOP_PROMOTION. strategy: MAX_CLICKS | TOP_MAX_CLICKS | TARGET_BIDS | TOP_PROMOTION | NO_AUTO_STRATEGY. Мин. бюджет: 2000₽ × SKU. Товары добавляются отдельно через ozon_ad_products_add.  
   Параметры: `title`*, `placement`, `strategy`, `daily_budget_rub`, `weekly_budget_rub`
45. **`ozon_ad_campaign_activate`** — Запустить рекламную кампанию.  
   Параметры: `campaign_id`*
46. **`ozon_ad_campaign_bids`** — [P0] Обновить ставки товаров в кампании. bids: [{sku, bid}] — ставка в МИКРОРУБЛЯХ строкой (10000000 = 10₽).  
   Параметры: `campaign_id`*, `bids`*
47. **`ozon_ad_campaign_budget`** — [P1] Бюджет кампании (из списка кампаний; отдельного эндпоинта у Ozon нет).  
   Параметры: `campaign_id`*
48. **`ozon_ad_campaign_budget_update`** — [P1] Изменить бюджет/период кампании (PATCH). Бюджеты в РУБЛЯХ.  
   Параметры: `campaign_id`*, `daily_budget_rub`, `weekly_budget_rub`, `from_date`, `to_date`
49. **`ozon_ad_campaign_products`** — [P1] Товары и ставки в кампании.  
   Параметры: `campaign_id`*, `page`
50. **`ozon_ad_products_add`** — [P1] Добавить товары в CPC-кампанию (≤500). bids: [{sku, bid}] в микрорублях; без bid — конкурентная ставка.  
   Параметры: `campaign_id`*, `bids`*
51. **`ozon_ad_products_delete`** — [P1] Убрать товары из кампании.  
   Параметры: `campaign_id`*, `skus`*
52. **`ozon_ad_bids_competitive`** — [P1] Конкурентные ставки по SKU в кампании (≤200).  
   Параметры: `campaign_id`*, `skus`*
53. **`ozon_ad_min_bids`** — [P1] Минимальные ставки по SKU. payment_type: CPC | CPO | CPC_TOP.  
   Параметры: `skus`*, `payment_type`
54. **`ozon_search_promo_products`** — [P0] Товары в «Оплате за заказ» (вывод в топ, CPO): ставки %, видимость. КРИТИЧНО: ставки фиксированные с 02.2025.  
   Параметры: `page`
55. **`ozon_search_promo_enable`** — [P1] ВКЛЮЧИТЬ продвижение «Оплата за заказ» для товаров (≤1000 SKU).  
   Параметры: `skus`*
56. **`ozon_search_promo_disable`** — [P0] ОТКЛЮЧИТЬ продвижение «Оплата за заказ» (≤1000 SKU). Используй при высоком ДРР.  
   Параметры: `skus`*
57. **`ozon_search_promo_bids`** — [P1] Фиксированные ставки CPO по SKU (≤200).  
   Параметры: `skus`*
58. **`ozon_ad_statistics_daily`** — Ежедневная статистика рекламы.  
   Параметры: `campaigns`*, `date_from`*, `date_to`*
59. **`ozon_ad_statistics_expenses`** — Расходы по рекламным кампаниям.  
   Параметры: `campaigns`*, `date_from`*, `date_to`*
60. **`ozon_ad_statistics_products`** — [P0] Статистика CPC-кампаний по товарам: расход, CTR, CPC, заказы, ДРР (синхронно).  
   Параметры: `campaigns`*, `date_from`*, `date_to`*
61. **`ozon_ad_balance`** — Баланс рекламного кабинета (официального метода нет — см. расходы в ozon_ad_statistics_expenses).

## Аналитика

62. **`ozon_analytics`** — [P1] Аналитика по SKU. ВНИМАНИЕ: метрики воронки (session_view, hits_view, position_category) Ozon пометил deprecated — работают торговые: revenue, ordered_units, delivered_units, returns, cancellations. Для позиций в поиске — ozon_product_queries.  
   Параметры: `date_from`*, `date_to`*, `metrics`*, `dimensions`*, `limit`
63. **`ozon_stock_on_warehouses`** — [P1] Остатки и оборачиваемость товаров на складах Ozon (через turnover/stocks — старый эндпоинт удалён Ozon).  
   Параметры: `limit`, `offset`
64. **`ozon_analytics_stocks`** — [P1] Аналитика по остаткам конкретных товаров: доступность, дефицитность, ликвидность (1-100 SKU).  
   Параметры: `skus`*
65. **`ozon_product_queries`** — [P0] Поисковые запросы и позиции моих товаров в поиске Ozon (Premium). КРИТИЧНО: видимость в поиске = продажи.  
   Параметры: `date_from`*, `skus`*, `details`
66. **`ozon_search_queries_top`** — [P1] Популярные поисковые запросы на Ozon (для SEO карточек).  
   Параметры: `limit`

## Поставки FBO

67. **`ozon_supply_orders`** — [P1] Заявки на поставку FBO (v3, возвращает order_ids — детали через ozon_supply_order_get).  
   Параметры: `states`, `limit`
68. **`ozon_supply_order_get`** — [P2] Детали заявок на поставку FBO (1-50).  
   Параметры: `order_ids`*
69. **`ozon_supply_order_counters`** — [P2] Счётчики заявок на поставку по статусам.
70. **`ozon_supply_order_timeslots`** — [P2] Доступные таймслоты для поставки FBO.  
   Параметры: `supply_order_id`*

## Товары

71. **`ozon_product_list`** — [P1] Список всех товаров. visibility: ALL, VISIBLE, QUARANTINE, ARCHIVED и др.  
   Параметры: `visibility`, `limit`
72. **`ozon_product_info`** — [P1] Расширенная информация по товарам.  
   Параметры: `product_id`*
73. **`ozon_product_attributes`** — [P1] Атрибуты товаров включая БРЕНД.  
   Параметры: `offer_id`, `product_id`, `limit`
74. **`ozon_product_stocks`** — [P1] Остатки товаров на складах FBO/FBS.  
   Параметры: `offer_id`, `product_id`, `limit`
75. **`ozon_product_certificates`** — [P1] Сертификаты товаров. Просроченный = блокировка.  
   Параметры: `product_id`*

## Импорт и обновление товаров

76. **`ozon_product_import`** — Создать/обновить товары (массовый импорт).  
   Параметры: `items`*
77. **`ozon_product_import_info`** — Статус задачи импорта товаров.  
   Параметры: `task_id`*
78. **`ozon_product_update_offer_id`** — Обновить артикулы товаров.  
   Параметры: `update_offer_id`*
79. **`ozon_product_update_images`** — Обновить изображения товара.  
   Параметры: `product_id`*, `images`*
80. **`ozon_product_description`** — Описание товара по артикулу.  
   Параметры: `offer_id`*
81. **`ozon_product_update_stocks`** — Обновить остатки FBS.  
   Параметры: `stocks`*
82. **`ozon_product_geo_restrictions`** — Установить географические ограничения.  
   Параметры: `product_id`*, `restrictions`*
83. **`ozon_product_unarchive`** — Вернуть товары из архива.  
   Параметры: `product_id`*
84. **`ozon_product_delete`** — Удалить товары без SKU из архива (по артикулам).  
   Параметры: `offer_ids`*
85. **`ozon_product_limits`** — Лимиты на создание товаров.
86. **`ozon_product_rating_by_sku`** — Рейтинг контента товаров.  
   Параметры: `skus`*
87. **`ozon_product_discounted`** — Информация об уценке по SKU уценённых товаров.  
   Параметры: `discounted_skus`*
88. **`ozon_product_attributes_update`** — [P1] Обновить характеристики товаров (без полной перезаливки карточки).  
   Параметры: `items`*
89. **`ozon_product_import_by_sku`** — [P2] Создать товар-копию по SKU существующего товара Ozon.  
   Параметры: `items`*
90. **`ozon_product_stocks_by_warehouse`** — [P1] Остатки товаров по складам FBS (v2; v1 отключается 07.04.2026).  
   Параметры: `skus`, `limit`

## Заказы FBS

91. **`ozon_orders_fbs`** — Заказы FBS с финансовыми данными.  
   Параметры: `since`*, `to`*, `limit`, `status`
92. **`ozon_order_fbs_get`** — Детали отправления FBS.  
   Параметры: `posting_number`*
93. **`ozon_order_fbs_ship`** — Собрать заказ FBS (v4). packages: [{products: [{product_id, quantity}]}].  
   Параметры: `posting_number`*, `packages`*
94. **`ozon_orders_fbs_unfulfilled`** — [P1] Несобранные заказы FBS (ожидают сборки).  
   Параметры: `limit`
95. **`ozon_order_fbs_label`** — [P1] Этикетки отправлений FBS (PDF base64).  
   Параметры: `posting_numbers`*
96. **`ozon_order_fbs_cancel`** — Отменить отправление FBS.  
   Параметры: `posting_number`*, `cancel_reason_id`*, `cancel_reason_message`
97. **`ozon_order_fbs_cancel_reasons`** — Список причин отмены FBS.
98. **`ozon_order_fbs_act_create`** — Создать акт приёма-передачи FBS.  
   Параметры: `containers_count`
99. **`ozon_order_fbs_act_status`** — Статус формирования акта.  
   Параметры: `id`*
100. **`ozon_order_fbs_act_pdf`** — Скачать PDF акта приёма-передачи.  
   Параметры: `id`*
101. **`ozon_order_fbs_digital_act`** — Статус акта (цифровые акты удалены Ozon 22.03.2026 — используется обычный акт).  
   Параметры: `id`*
102. **`ozon_order_fbs_country_list`** — Страны для отправления FBS.  
   Параметры: `posting_number`*
103. **`ozon_order_fbs_country_set`** — Указать страну товара в отправлении.  
   Параметры: `posting_number`*, `product_id`*, `country_iso`*
104. **`ozon_order_fbs_restrictions`** — Ограничения отправлений FBS.  
   Параметры: `posting_number`*
105. **`ozon_order_fbs_timeslot`** — Изменить тайм-слот отправления.  
   Параметры: `posting_number`*, `new_timeslot_id`*
106. **`ozon_order_fbo_get`** — Детали отправления FBO.  
   Параметры: `posting_number`*

## Заказы FBO

107. **`ozon_orders_fbo`** — [P1] Заказы FBO.  
   Параметры: `since`*, `to`*, `limit`

## Возвраты

108. **`ozon_returns_fbo`** — [P1] ЕДИНЫЙ список возвратов FBO+FBS (/v1/returns/list; старые returns/company/* отключены Ozon).  
   Параметры: `filter`, `limit`
109. **`ozon_returns_fbs`** — [P1] Заявки покупателей на возврат rFBS (требуют решения продавца!).  
   Параметры: `limit`
110. **`ozon_returns_fbs_get`** — [P1] Детали заявки на возврат rFBS.  
   Параметры: `return_id`*
111. **`ozon_returns_fbs_approve`** — [P1] Одобрить заявку rFBS (verify — согласовать возврат).  
   Параметры: `return_id`*
112. **`ozon_returns_fbs_reject`** — [P1] Отклонить заявку rFBS (комментарий обязателен).  
   Параметры: `return_id`*, `reason`*
113. **`ozon_returns_rfbs_action`** — [P1] Действие по заявке rFBS: receive-return (подтвердить получение товара), return-money (вернуть деньги), compensate (компенсация без возврата).  
   Параметры: `action`*, `return_id`*, `comment`

## Возвраты (LEGACY)

114. **`ozon_returns_report`** — [P1] Создать отчёт по возвратам.  
   Параметры: `filter`*

## Вопросы

115. **`ozon_questions`** — Список вопросов покупателей.  
   Параметры: `limit`, `last_id`
116. **`ozon_question_reply`** — Ответить на вопрос покупателя (нужен sku товара).  
   Параметры: `question_id`*, `sku`*, `text`*

## Чаты

117. **`ozon_chat_list`** — Список чатов с покупателями (v3). unread_only=true — только с непрочитанными.  
   Параметры: `unread_only`, `page_size`
118. **`ozon_chat_history`** — История сообщений чата.  
   Параметры: `chat_id`*, `limit`
119. **`ozon_chat_send`** — Отправить сообщение в чат.  
   Параметры: `chat_id`*, `text`*
120. **`ozon_chat_send_file`** — Отправить файл в чат.  
   Параметры: `chat_id`*, `file_url`*, `file_name`*
121. **`ozon_chat_updates`** — Обновления чатов.  
   Параметры: `limit`
122. **`ozon_chat_start`** — Начать чат по отправлению.  
   Параметры: `posting_number`*
123. **`ozon_chat_read`** — Пометить чат как прочитанный.  
   Параметры: `chat_id`*

## Отмены

124. **`ozon_cancellation_list`** — [P1] Заявки покупателей на отмену (v2). state: ALL | ON_APPROVAL | APPROVED | REJECTED.  
   Параметры: `posting_number`, `state`, `limit`
125. **`ozon_cancellation_approve`** — Одобрить заявку на отмену.  
   Параметры: `cancellation_id`*, `comment`
126. **`ozon_cancellation_reject`** — Отклонить заявку на отмену.  
   Параметры: `cancellation_id`*, `comment`

## Склады

127. **`ozon_warehouse_list`** — Список складов FBS продавца.
128. **`ozon_delivery_methods`** — Методы доставки.  
   Параметры: `limit`

## Отчёты

129. **`ozon_report_list`** — Список сформированных отчётов.  
   Параметры: `report_type`, `page`
130. **`ozon_report_info`** — Статус и ссылка на отчёт.  
   Параметры: `code`*
131. **`ozon_report_products_create`** — Создать отчёт по товарам.  
   Параметры: `visibility`
132. **`ozon_report_stocks_create`** — Создать отчёт по остаткам.
133. **`ozon_report_finance_create`** — Создать финансовый отчёт.  
   Параметры: `date_from`*, `date_to`*
134. **`ozon_report_discounted_create`** — Отчёт по уценённым товарам.

## Бренды

135. **`ozon_brand_certificates`** — Сертификаты бренда.

## Категории

136. **`ozon_category_tree`** — Дерево категорий Ozon.
137. **`ozon_category_attributes`** — Атрибуты категории.  
   Параметры: `description_category_id`*, `type_id`
138. **`ozon_category_attribute_values`** — Значения атрибута категории.  
   Параметры: `description_category_id`*, `attribute_id`*, `limit`
139. **`ozon_category_attribute_search`** — Поиск значений атрибута.  
   Параметры: `description_category_id`*, `attribute_id`*, `value`*

## Уведомления

140. **`ozon_notifications`** — Подписки на push-уведомления (вебхуки). Старого «списка уведомлений» в Ozon API нет.
141. **`ozon_notification_push_types`** — Справочник типов push-событий (новые сообщения, статусы отправлений и т.д.).

## Скидки

142. **`ozon_discount_tasks`** — [P1] Заявки покупателей «Хочу скидку». status: NEW | SEEN | APPROVED | PARTLY_APPROVED | DECLINED | AUTO_DECLINED.  
   Параметры: `status`, `limit`
143. **`ozon_discount_approve`** — [P1] Одобрить заявки на скидку.  
   Параметры: `tasks`*
144. **`ozon_discount_decline`** — [P1] Отклонить заявки на скидку.  
   Параметры: `tasks`*

## Компания

145. **`ozon_company_info`** — Информация о компании продавца.
146. **`ozon_company_tariffs`** — Тарифы компании.

## Сертификаты

147. **`ozon_certificate_list`** — Список всех сертификатов.  
   Параметры: `status`
148. **`ozon_certificate_info`** — Детали сертификата.  
   Параметры: `certificate_id`*

## Архив

149. **`ozon_product_archive`** — [P2] Отправить товары в архив.  
   Параметры: `product_id`*

## Диагностика

150. **`ozon_diagnostics`** — [P0] ПОЛНАЯ САМОДИАГНОСТИКА: доступность хостов Ozon + лёгкие реальные запросы по 12 категориям Seller API + проверка ключей Performance API. Используй ПЕРВЫМ ДЕЛОМ если какой-то инструмент не работает — покажет, проблема в ключах, в конкретной категории API или в изменении API со стороны Ozon.
151. **`ozon_degradations`** — [P0] Деградации инструментов: какие MCP-инструменты раньше работали, а теперь стабильно падают (сигнал изменения Ozon API). Без параметров.
