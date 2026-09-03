"""Формирование ответа инструмента: пресеты полей, сигнал усечения, предохранитель размера.

Зачем: ответы Ozon API рассчитаны на программу, а не на модель с ограниченным
контекстом. Замер на живом кабинете (сентябрь 2026):

    ozon_category_tree     266 000 токенов  (9 797 узлов дерева целиком)
    ozon_get_prices         53 000 токенов  (93 % веса — история marketing_actions)
    ozon_warehouse_list     20 000 токенов  (99 % веса — расписание склада на год)

Потолок вывода одного вызова у клиента — 25 000 токенов (MAX_MCP_OUTPUT_TOKENS
в Claude Code), дальше ответ молча обрезается. Поэтому:

* compact-пресет отдаёт поля, по которым инструмент и вызывают, full — всё;
* если записей ровно столько, сколько просили, ответ дополняется предупреждением
  об усечении — иначе модель строит вывод по срезу, считая его полным;
* предохранитель по размеру не даёт ответу превысить потолок клиента молча.
"""

from __future__ import annotations

import json
import os
from typing import Any

MAX_RESPONSE_CHARS = int(os.environ.get("OZON_MAX_RESPONSE_CHARS", "60000"))

# инструмент → (путь до массива записей, поля compact-режима)
VIEWS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "ozon_get_prices": (
        ("items",),
        ("product_id", "offer_id", "price", "price_indexes", "acquiring", "volume_weight"),
    ),
    "ozon_get_prices_v4": (
        ("items",),
        ("product_id", "offer_id", "price", "price_indexes", "acquiring", "volume_weight"),
    ),
    "ozon_ad_campaigns": (
        ("list",),
        ("id", "title", "state", "advObjectType", "budget", "dailyBudget", "weeklyBudget",
         "budgetType", "fromDate", "toDate", "placement", "productCampaignMode",
         "expenseStrategy", "autostopStatus", "PaymentType"),
    ),
    "ozon_warehouse_list": (
        ("warehouses",),
        ("warehouse_id", "name", "status", "is_rfbs", "is_kgt", "has_entrusted_acceptance",
         "first_mile", "address_info", "working_days", "min_working_days", "is_able_to_set_price"),
    ),
    "ozon_returns_fbo": (
        ("returns",),
        ("id", "product", "return_reason_name", "visual", "exemplars", "is_opened"),
    ),
    "ozon_search_promo_products": (
        ("products",),
        ("sku", "sourceSku", "title", "bid", "bidPrice", "carrotsStatus", "views", "visibility"),
    ),
    "ozon_actions_list": (
        ("result",),
        ("id", "title", "action_type", "date_start", "date_end", "participating",
         "is_participating_available", "potential_products_count", "participating_products_count"),
    ),
}

COMPACT_BY_DEFAULT = frozenset(VIEWS)

VIEW_PROP = {
    "type": "string",
    "enum": ["compact", "full"],
    "description": "compact (default) trims heavy fields; full returns the raw API response",
}


def _dig(data: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _put(data: Any, path: tuple[str, ...], value: Any) -> Any:
    if not path:
        return value
    if not isinstance(data, dict):
        return data
    head, rest = path[0], path[1:]
    if head not in data:
        return data
    copy = dict(data)
    copy[head] = _put(copy[head], rest, value)
    return copy


def apply_view(name: str, data: Any, view: str) -> tuple[Any, str | None]:
    """Оставить в записях только поля compact-пресета."""
    if view == "full" or name not in VIEWS:
        return data, None
    path, fields = VIEWS[name]
    items = _dig(data, path)
    if not isinstance(items, list) or not items:
        return data, None
    keep = set(fields)
    dropped: set[str] = set()
    slim = []
    for item in items:
        if not isinstance(item, dict):
            slim.append(item)
            continue
        dropped |= set(item) - keep
        slim.append({k: v for k, v in item.items() if k in keep})
    if not dropped:
        return data, None
    note = (f'Показаны основные поля ({len(items)} записей). '
            f'Скрыто: {", ".join(sorted(dropped)[:8])}'
            f'{"…" if len(dropped) > 8 else ""}. Полный ответ — с view="full".')
    return _put(data, path, slim), note


def truncation_note(name: str, arguments: dict, data: Any) -> str | None:
    """Предупредить, если записей ровно столько, сколько запрошено."""
    limit = arguments.get("limit")
    if not isinstance(limit, int) or limit <= 0:
        return None
    items = _dig(data, VIEWS[name][0]) if name in VIEWS else None
    if not isinstance(items, list):
        items = data if isinstance(data, list) else None
    if not isinstance(items, list) or len(items) < limit:
        return None
    return (f'Вернулось ровно {limit} записей — данные почти наверняка неполные. '
            f'Повторите со следующей страницей или сузьте фильтр, прежде чем делать '
            f'выводы по всему ассортименту.')


def _longest_list(data: Any, path: tuple[str, ...] = ()) -> tuple[tuple[str, ...], list | None]:
    best_path: tuple[str, ...] = ()
    best: list | None = None
    if isinstance(data, list):
        return path, data
    if isinstance(data, dict):
        for key, value in data.items():
            sub_path, sub = _longest_list(value, path + (key,))
            if sub is not None and (best is None or len(sub) > len(best)):
                best_path, best = sub_path, sub
    return best_path, best


def guard_size(data: Any, max_chars: int = MAX_RESPONSE_CHARS) -> tuple[Any, str | None]:
    """Не дать ответу молча упереться в потолок вывода клиента."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(payload) <= max_chars:
        return data, None

    target_path, target = _longest_list(data)
    if target is None or len(target) < 2:
        return data, (f"Ответ слишком велик ({len(payload)} символов) и будет обрезан клиентом. "
                      f"Сузьте период или фильтр.")

    per_item = max(1, len(payload) // len(target))
    keep = max(1, min(len(target) - 1, max_chars // per_item))
    note = (f"Показаны {keep} записей из {len(target)}: полный ответ ({len(payload)} символов) "
            f"не помещается в лимит вывода клиента. Сузьте фильтр или запросите остальное "
            f"постранично — выводы по этому срезу неполные.")
    return _put(data, target_path, target[:keep]), note


def shape(name: str, arguments: dict, data: Any) -> tuple[Any, list[str]]:
    """Применить пресет, проверить усечение и размер. Возвращает (данные, заметки)."""
    notes: list[str] = []
    view = arguments.get("view") or ("compact" if name in COMPACT_BY_DEFAULT else "full")

    data, note = apply_view(name, data, view)
    if note:
        notes.append(note)

    note = truncation_note(name, arguments, data)
    if note:
        notes.append(note)

    data, note = guard_size(data)
    if note:
        notes.append(note)

    return data, notes
