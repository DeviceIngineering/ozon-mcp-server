"""Интеграционный тест stdio-режима: статистика вызовов и ozon_degradations.

Ловит сбой, из-за которого диагностика в stdio была слепой:
set_stats_callback вызывался только из lifespan в app.py, то есть в web-режиме,
а stdio-точка входа server.main() статистику не поднимала вовсе. В итоге
_stats_callback оставался None, база stats.db не создавалась, и инструмент
ozon_degradations на любой вопрос отвечал «Деградаций нет — все инструменты
работают штатно» — даже когда падал каждый вызов.

Тест поднимает реальный сервер по stdio настоящим MCP-клиентом:
initialize → call_tool → проверка записей в stats.db.
"""

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[1]


async def _probe(data_dir: Path, calls: int):
    """Поднять сервер по stdio, сделать `calls` заведомо падающих вызовов."""
    env = {
        **os.environ,
        "DATA_DIR": str(data_dir),
        "PYTHONPATH": str(REPO_ROOT),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from ozon_mcp.server import main; main()"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(calls):
                await session.call_tool("ozon_actions_list", {"shop_id": "нет-такого"})
            degradations = await session.call_tool("ozon_degradations", {})
            return json.loads(degradations.content[0].text)


def test_stdio_records_calls_to_stats_db(tmp_path):
    """В stdio вызовы инструментов попадают в stats.db, а не теряются."""
    verdict = asyncio.run(asyncio.wait_for(_probe(tmp_path, calls=3), 60))

    db = tmp_path / "stats.db"
    assert db.exists(), "stdio-режим не создал базу статистики"

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT tool_name, success FROM tool_calls ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    failed = [r for r in rows if r[0] == "ozon_actions_list"]
    assert len(failed) == 3, f"вызовы не записались: {rows}"
    assert all(r[1] == 0 for r in failed), "падавшие вызовы записались как успешные"
    assert verdict is not None


def test_degradations_never_claims_ok_without_data(tmp_path):
    """Пустая статистика — это no_data, а не «всё штатно»."""
    verdict = asyncio.run(asyncio.wait_for(_probe(tmp_path, calls=0), 60))

    assert verdict["status"] == "no_data", verdict
    assert "Деградаций нет" not in verdict["message"]


def test_degradations_reports_call_count(tmp_path):
    """Когда данные есть, вердикт опирается на число учтённых вызовов."""
    verdict = asyncio.run(asyncio.wait_for(_probe(tmp_path, calls=3), 60))

    # Три падения подряд без единого успеха раньше — это ещё не деградация
    # (get_tool_degradations требует прежних успехов), но и не «нет данных».
    assert verdict["status"] == "ok", verdict
    assert "учтено вызовов: 3" in verdict["message"], verdict


def test_unwritable_data_dir_does_not_kill_server(tmp_path):
    """Недоступный DATA_DIR не роняет stdio-сервер, а отключает статистику.

    По умолчанию DATA_DIR = /data, а stdio запускают на машине пользователя,
    где такого каталога обычно нет и создать его нельзя.
    """
    blocker = tmp_path / "это-файл-а-не-каталог"
    blocker.write_text("")
    verdict = asyncio.run(asyncio.wait_for(_probe(blocker / "data", calls=1), 60))

    assert verdict["status"] == "no_data", verdict
    assert not (blocker / "data").exists()
