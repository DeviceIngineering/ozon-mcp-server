"""Тесты модуля статистики."""

import pytest
import pytest_asyncio
from ozon_mcp import stats


@pytest_asyncio.fixture
async def db(tmp_path):
    await stats.init_db(tmp_path)
    yield
    await stats.close_db()


@pytest.mark.asyncio
async def test_empty_summary(db):
    s = await stats.get_summary()
    assert s["total"] == 0
    assert s["errors"] == 0
    assert s["shops"] == []


@pytest.mark.asyncio
async def test_record_and_summary(db):
    await stats.record_call("ozon_rating_summary", 150.5, True, None, "shop1")
    await stats.record_call("ozon_rating_summary", 200.0, True, None, "shop1")
    await stats.record_call("ozon_get_prices", 50.0, False, "ValueError", "shop2")

    s = await stats.get_summary()
    assert s["total"] == 3
    assert s["errors"] == 1
    assert set(s["shops"]) == {"shop1", "shop2"}


@pytest.mark.asyncio
async def test_filter_by_shop(db):
    await stats.record_call("tool_a", 10.0, True, None, "s1")
    await stats.record_call("tool_b", 20.0, True, None, "s2")

    s1 = await stats.get_summary(shop_id="s1")
    assert s1["total"] == 1
    assert s1["recent"][0]["tool"] == "tool_a"

    s2 = await stats.get_summary(shop_id="s2")
    assert s2["total"] == 1


@pytest.mark.asyncio
async def test_recent_order(db):
    await stats.record_call("tool_a", 10.0, True, None, "s1")
    await stats.record_call("tool_b", 20.0, True, None, "s1")

    s = await stats.get_summary()
    assert s["recent"][0]["tool"] == "tool_b"
