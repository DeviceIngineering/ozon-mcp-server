"""Профили инструментов: урезать каталог можно, прятать причину — нельзя."""

import pytest

from ozon_mcp import toolsets
from ozon_mcp.server import TOOLS, _enabled_tools, _visible_tools


def test_every_tool_belongs_to_a_profile():
    """Инструмент без профиля потерялся бы при любом OZON_TOOLSETS."""
    unassigned = [t.name for t in TOOLS if toolsets.profile_of(t.name) not in toolsets.ALL_PROFILES]
    assert not unassigned, unassigned


def test_no_limit_by_default(monkeypatch):
    monkeypatch.delenv("OZON_TOOLSETS", raising=False)
    assert toolsets.enabled_profiles() is None
    assert len(_enabled_tools(_visible_tools())) == len(TOOLS)


def test_profile_narrows_the_catalogue(monkeypatch):
    monkeypatch.setenv("OZON_TOOLSETS", "pricing,ads")
    tools = _enabled_tools(_visible_tools())
    assert 0 < len(tools) < len(TOOLS)
    profiles = {toolsets.profile_of(t.name) for t in tools}
    assert profiles <= {"core", "pricing", "ads"}


def test_core_survives_any_profile(monkeypatch):
    """Диагностика нужна ровно тогда, когда что-то сломалось."""
    monkeypatch.setenv("OZON_TOOLSETS", "pricing")
    names = {t.name for t in _enabled_tools(_visible_tools())}
    for required in ("ozon_list_shops", "ozon_diagnostics", "ozon_degradations", "ozon_company_info"):
        assert required in names, required


def test_disabled_profiles_are_named_in_list_shops(monkeypatch):
    monkeypatch.setenv("OZON_TOOLSETS", "pricing")
    description = next(t.description for t in _enabled_tools(_visible_tools())
                       if t.name == "ozon_list_shops")
    assert "OZON_TOOLSETS" in description
    assert "finance" in description and "orders" in description


def test_unknown_profile_is_ignored(monkeypatch):
    monkeypatch.setenv("OZON_TOOLSETS", "нет-такого-профиля")
    assert toolsets.enabled_profiles() is None


@pytest.mark.asyncio
async def test_disabled_tool_explains_itself(monkeypatch):
    """Отказ должен называть причину, иначе модель скажет «это невозможно»."""
    monkeypatch.setenv("OZON_TOOLSETS", "pricing")
    from ozon_mcp.server import _call_tool_impl

    blocks = await _call_tool_impl("ozon_reviews", {"shop_id": "нет-такого"})
    text = blocks[0].text
    assert "feedback" in text and "OZON_TOOLSETS" in text
