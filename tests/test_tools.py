"""Схемы инструментов: то, что уходит клиенту в каждой сессии."""


def test_visible_tools_hides_shop_id_for_single_shop(tmp_path, monkeypatch):
    """Один магазин — shop_id из схем убран, несколько — возвращается."""
    import json
    from ozon_mcp import server

    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    with_shop_id = lambda tools: sum(
        1 for t in tools if "shop_id" in (t.inputSchema.get("properties") or {})
    )

    tools = server._visible_tools()
    assert len(tools) == len(server.TOOLS)
    assert with_shop_id(tools) == 0, "при одном магазине shop_id не нужен в схеме"

    (tmp_path / "shops.json").write_text(json.dumps({"a": {"name": "A"}, "b": {"name": "B"}}))
    tools = server._visible_tools()
    assert with_shop_id(tools) > 0, "при нескольких магазинах shop_id обязан вернуться"


def test_json_output_is_compact():
    """Ответы сериализуются без отступов — indent=2 стоил 39% лишних токенов."""
    from ozon_mcp.server import _json

    text = _json({"a": [1, 2], "b": "тест"})[0].text
    assert "\n" not in text and ", " not in text, text
    assert "\\u" not in text, "кириллица не должна экранироваться"


def test_no_duplicate_tools():
    """Нет дублей в TOOLS."""
    from ozon_mcp.server import TOOLS

    names = [t.name for t in TOOLS]
    assert len(names) == len(set(names))


def test_limit_defaults_are_modest():
    """Дефолтный limit не должен выдавать ответ крупнее потолка клиента.

    В Claude Code потолок вывода одного вызова — MAX_MCP_OUTPUT_TOKENS,
    по умолчанию 25 000 токенов; ответ на тысячи строк в него не помещается
    и молча обрезается.
    """
    from ozon_mcp.server import TOOLS

    too_big = [
        (t.name, (t.inputSchema.get("properties") or {})["limit"]["default"])
        for t in TOOLS
        if isinstance((t.inputSchema.get("properties") or {}).get("limit"), dict)
        and (t.inputSchema["properties"]["limit"].get("default") or 0) > 500
    ]
    assert not too_big, f"слишком крупный дефолтный limit: {too_big}"
