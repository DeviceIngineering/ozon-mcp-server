"""Интеграционный тест MCP-подключения по SSE.

Ловит именно тот сбой, из-за которого сервер был нерабочим:
POST /messages обрабатывался маршрутом FastAPI поверх ASGI-приложения
транспорта, второй ASGI-ответ ронял соединение (`RuntimeError: Unexpected
ASGI message ... after response already completed`), а у клиента это выглядело
как httpx.ReadError на стадии initialize.

Тест поднимает реальный uvicorn в отдельном процессе и ходит настоящим
MCP-клиентом: initialize → list_tools → call_tool. Прогоняется в двух режимах —
без MCP_AUTH_TOKEN и с ним.
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from mcp import ClientSession
from mcp.client.sse import sse_client

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN = "test-token-placeholder"


def _free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module", params=[False, True], ids=["без токена", "с токеном"])
def server(request, tmp_path_factory):
    """Живой сервер на свободном порту. Возвращает (base_url, token|None)."""
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("data")
    env = {
        **os.environ,
        "DATA_DIR": str(data_dir),
        "HEALTH_CHECK_INTERVAL_MIN": "0",
        "MCP_AUTH_TOKEN": TOKEN if request.param else "",
        "PYTHONPATH": str(REPO_ROOT),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ozon_mcp.app:fastapi_app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail(f"Сервер не запустился:\n{proc.stdout.read()}")
            try:
                if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            pytest.fail("Сервер не поднялся за 20 секунд")
        yield base, (TOKEN if request.param else None)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


async def _session_probe(base: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with sse_client(f"{base}/sse", headers=headers, timeout=15) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("ozon_list_shops", {})
            return tools.tools, result


def test_mcp_client_connects_and_calls_tool(server):
    """initialize → list_tools → call_tool проходят целиком."""
    base, token = server
    tools, result = asyncio.run(asyncio.wait_for(_session_probe(base, token), 60))

    from ozon_mcp.server import TOOLS
    assert len(tools) == len(TOOLS), "list_tools вернул не все инструменты"
    assert "ozon_list_shops" in {t.name for t in tools}
    assert not result.isError, result.content
    assert result.content and result.content[0].text is not None


def test_unauthorized_is_rejected(server):
    """С включённым токеном без него доступ закрыт, а /messages не пускает чужих."""
    base, token = server
    if token is None:
        pytest.skip("режим без авторизации")

    assert httpx.get(f"{base}/sse", timeout=5).status_code == 401
    assert httpx.post(
        f"{base}/messages/?session_id=00000000000000000000000000000000",
        json={}, timeout=5,
    ).status_code == 401
