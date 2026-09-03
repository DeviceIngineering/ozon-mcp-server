"""Формирование ответа: пресеты, сигнал усечения, предохранитель размера.

Проверяется главное свойство: урезать данные можно, молчать об этом — нельзя.
"""

import json

from ozon_mcp import shaping
from ozon_mcp.server import _trim_category_tree


def _prices(n=3):
    return {"items": [{"product_id": 100 + i, "offer_id": f"ART-{i}",
                       "price": {"price": "1290", "old_price": "1990"},
                       "acquiring": 10.14, "volume_weight": 0.1,
                       "price_indexes": {"color_index": "COLOR_INDEX_GREEN"},
                       "commissions": {"fbo_deliv_to_customer_amount": 25},
                       "marketing_actions": {"actions": [{"title": "Акция"}] * 20}}
                      for i in range(n)]}


def test_compact_drops_marketing_history_and_says_so():
    data, notes = shaping.shape("ozon_get_prices", {}, _prices())
    item = data["items"][0]
    assert "marketing_actions" not in item and "commissions" not in item
    assert item["product_id"] == 100 and item["price"]["price"] == "1290"
    assert notes and "marketing_actions" in notes[0] and "view=" in notes[0]


def test_full_view_keeps_everything_and_stays_silent():
    data, notes = shaping.shape("ozon_get_prices", {"view": "full"}, _prices())
    assert "marketing_actions" in data["items"][0]
    assert notes == []


def test_unknown_tool_passes_through():
    payload = {"whatever": [1, 2, 3]}
    data, notes = shaping.shape("ozon_some_other_tool", {}, payload)
    assert data == payload and notes == []


def test_truncation_is_announced_when_page_is_full():
    _, notes = shaping.shape("ozon_get_prices", {"limit": 3}, _prices(3))
    assert any("ровно 3" in n for n in notes), notes


def test_no_truncation_note_when_page_is_short():
    _, notes = shaping.shape("ozon_get_prices", {"limit": 50}, _prices(3))
    assert not any("ровно" in n for n in notes), notes


def test_guard_cuts_oversized_array_and_reports_the_cut():
    huge = {"returns": [{"id": i, "name": f"Возврат {i}", "reason": "не подошёл размер"}
                        for i in range(5000)]}
    data, note = shaping.guard_size(huge, max_chars=20_000)
    kept = len(data["returns"])
    assert 0 < kept < 5000
    assert note and str(kept) in note and "5000" in note


def test_category_tree_returns_top_level_by_default():
    tree = {"result": [{"description_category_id": 1, "category_name": "Дом",
                        "children": [{"description_category_id": 2, "category_name": "Хранение",
                                      "children": [{"description_category_id": 3,
                                                    "category_name": "Ящики", "children": []}]}]}]}
    top = _trim_category_tree(tree, "", 1)
    assert top["result"][0]["children"] == []
    assert top["result"][0]["hasChildren"] is True
    assert "hint" in top

    deep = _trim_category_tree(tree, "", 3)
    assert deep["result"][0]["children"][0]["children"][0]["category_name"] == "Ящики"


def test_category_tree_search_keeps_the_branch():
    tree = {"result": [{"description_category_id": 1, "category_name": "Дом",
                        "children": [{"description_category_id": 2, "category_name": "Ящики",
                                      "children": []}]},
                       {"description_category_id": 9, "category_name": "Электроника",
                        "children": []}]}
    found = _trim_category_tree(tree, "ящик", 1)
    assert len(found["result"]) == 1
    assert found["result"][0]["children"][0]["category_name"] == "Ящики"
    assert found["filteredBy"] == "ящик"
