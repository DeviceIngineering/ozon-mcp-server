"""FastAPI-приложение: MCP через SSE + веб-интерфейс (мульти-магазин) + диагностика."""

import os
import asyncio
import secrets
import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from mcp.server.sse import SseServerTransport

from ozon_mcp.server import get_mcp_app, reset_all_clients, reset_shop, set_stats_callback, get_seller_for_shop
from ozon_mcp import settings as cfg
from ozon_mcp import stats
from ozon_mcp import diagnostics as diag

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Токен авторизации MCP-эндпоинтов (для доступа извне).
# Пусто = авторизация выключена (только доверенная сеть!).
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()

# Интервал фоновой health-проверки, минуты (0 = выключить)
HEALTH_CHECK_INTERVAL_MIN = int(os.environ.get("HEALTH_CHECK_INTERVAL_MIN", "30"))

sse_transport = SseServerTransport("/messages")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_health_task: asyncio.Task | None = None


# ─── Фоновая диагностика ────────────────────────────────────

async def _run_health_check_all() -> list[dict]:
    """Прогнать полную диагностику по всем магазинам, записать в БД."""
    results = []
    shops = cfg.load_shops(DATA_DIR)
    for shop_id, shop in shops.items():
        if not shop.get("ozon_client_id") or not shop.get("ozon_api_key"):
            continue
        try:
            seller = get_seller_for_shop(shop_id)
            result = await diag.full_diagnostics(shop_id, shop.get("name", shop_id), shop, seller)
            await stats.record_health_check(
                shop_id=shop_id,
                healthy=result["healthy"],
                ping_failures=sum(1 for h in result["hosts"] if not h["ok"]),
                probe_failures=sum(1 for p in result["probes"] if not p["ok"] and not p.get("skipped")),
                warnings=result["warnings"],
                detail=result,
            )
            results.append(result)
        except Exception as e:
            await stats.record_health_check(
                shop_id=shop_id, healthy=False, ping_failures=0, probe_failures=0,
                warnings=[f"Диагностика упала: {type(e).__name__}: {e}"],
            )
    return results


async def _health_loop():
    """Периодическая фоновая проверка всех магазинов."""
    await asyncio.sleep(15)
    while True:
        try:
            await _run_health_check_all()
        except Exception:
            pass
        await asyncio.sleep(HEALTH_CHECK_INTERVAL_MIN * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _health_task
    await stats.init_db(DATA_DIR)
    set_stats_callback(stats.record_call)
    if HEALTH_CHECK_INTERVAL_MIN > 0:
        _health_task = asyncio.create_task(_health_loop())
    yield
    if _health_task:
        _health_task.cancel()
    await reset_all_clients()
    await stats.close_db()


fastapi_app = FastAPI(lifespan=lifespan)


# ─── Авторизация MCP-эндпоинтов ─────────────────────────────

def _check_mcp_auth(request: Request) -> bool:
    """Проверка Bearer-токена для /sse. Без MCP_AUTH_TOKEN — пропуск."""
    if not MCP_AUTH_TOKEN:
        return True
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        token = request.query_params.get("token", "")
    return secrets.compare_digest(token, MCP_AUTH_TOKEN)


# ─── MCP SSE endpoints ──────────────────────────────────────

@fastapi_app.get("/sse")
async def sse_endpoint(request: Request):
    if not _check_mcp_auth(request):
        return Response("Unauthorized", status_code=401)
    mcp_app = get_mcp_app()
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())


@fastapi_app.post("/messages")
async def messages_endpoint(request: Request):
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )


# ─── Веб-интерфейс ──────────────────────────────────────────

@fastapi_app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    shop_filter = request.query_params.get("shop", None)
    summary = await stats.get_summary(shop_id=shop_filter)
    degradations = await stats.get_tool_degradations()
    health = await stats.get_health_history(limit=1)
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats": summary, "current_shop": shop_filter or "",
        "degradations": degradations,
        "last_health": health[0] if health else None,
    })


@fastapi_app.get("/shops", response_class=HTMLResponse)
async def shops_page(request: Request):
    shops = cfg.load_shops(DATA_DIR)
    masked = {sid: cfg.get_masked_shop(s) for sid, s in shops.items()}
    return templates.TemplateResponse(request, "shops.html", {"shops": masked})


@fastapi_app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics_page(request: Request):
    """Страница диагностики: ключи, хосты, пробы, деградации, история."""
    shops = cfg.load_shops(DATA_DIR)
    shop_data = []
    for shop_id, shop in shops.items():
        last = await stats.get_last_health(shop_id)
        shop_data.append({
            "id": shop_id,
            "name": shop.get("name", shop_id),
            "seller_keys_set": bool(shop.get("ozon_client_id") and shop.get("ozon_api_key")),
            "perf_keys_set": bool(shop.get("ozon_perf_client_id") and shop.get("ozon_perf_client_secret")),
            "last_check": last,
        })
    degradations = await stats.get_tool_degradations()
    history = await stats.get_health_history(limit=30)
    return templates.TemplateResponse(request, "diagnostics.html", {
        "shops": shop_data,
        "degradations": degradations,
        "history": history,
        "interval_min": HEALTH_CHECK_INTERVAL_MIN,
    })


@fastapi_app.post("/api/diagnostics/run")
async def run_diagnostics_now():
    """Запустить диагностику всех магазинов прямо сейчас."""
    results = await _run_health_check_all()
    return JSONResponse({
        "ok": True,
        "shops_checked": len(results),
        "results": [
            {"shop_id": r["shop_id"], "healthy": r["healthy"], "warnings": r["warnings"]}
            for r in results
        ],
    })


@fastapi_app.get("/api/diagnostics/{shop_id}")
async def api_diagnostics_shop(shop_id: str):
    """Полная диагностика конкретного магазина (живой запрос)."""
    shops = cfg.load_shops(DATA_DIR)
    if shop_id not in shops:
        return JSONResponse({"ok": False, "error": "Магазин не найден"}, status_code=404)
    shop = shops[shop_id]
    if not shop.get("ozon_client_id") or not shop.get("ozon_api_key"):
        return JSONResponse({"ok": False, "error": "Ключи Seller API не заданы"}, status_code=400)
    seller = get_seller_for_shop(shop_id)
    result = await diag.full_diagnostics(shop_id, shop.get("name", shop_id), shop, seller)
    await stats.record_health_check(
        shop_id=shop_id, healthy=result["healthy"],
        ping_failures=sum(1 for h in result["hosts"] if not h["ok"]),
        probe_failures=sum(1 for p in result["probes"] if not p["ok"] and not p.get("skipped")),
        warnings=result["warnings"], detail=result,
    )
    return JSONResponse(result)


@fastapi_app.post("/api/shops")
async def save_shop(request: Request):
    data = await request.json()
    shop_id = data.get("shop_id", "").strip()
    if not shop_id:
        return JSONResponse({"ok": False, "error": "shop_id обязателен"}, status_code=400)

    shops = cfg.load_shops(DATA_DIR)
    existing = shops.get(shop_id, {})

    shop = {"name": data.get("name", shop_id)}
    for key in cfg.SHOP_KEYS:
        val = data.get(key, "")
        if val and "***" not in val:
            shop[key] = val
        elif key in existing:
            shop[key] = existing[key]
    shops[shop_id] = shop
    cfg.save_shops(DATA_DIR, shops)
    await reset_shop(shop_id)
    return JSONResponse({"ok": True})


@fastapi_app.delete("/api/shops/{shop_id}")
async def delete_shop(shop_id: str):
    shops = cfg.load_shops(DATA_DIR)
    if shop_id not in shops:
        return JSONResponse({"ok": False, "error": "Магазин не найден"}, status_code=404)
    del shops[shop_id]
    cfg.save_shops(DATA_DIR, shops)
    await reset_shop(shop_id)
    return JSONResponse({"ok": True})


@fastapi_app.post("/api/shops/{shop_id}/test")
async def test_shop_connection(shop_id: str):
    shops = cfg.load_shops(DATA_DIR)
    if shop_id not in shops:
        return JSONResponse({"ok": False, "error": "Магазин не найден"}, status_code=404)

    shop = shops[shop_id]
    results = {"seller_ok": False, "perf_ok": False, "errors": []}

    from ozon_mcp.client import OzonSellerClient, OzonPerformanceClient

    cid = shop.get("ozon_client_id", "")
    akey = shop.get("ozon_api_key", "")
    if cid and akey:
        c = OzonSellerClient(cid, akey)
        try:
            await c.rating_summary()
            results["seller_ok"] = True
        except Exception as e:
            results["errors"].append(f"Seller API: {e}")
        finally:
            await c.close()
    else:
        results["errors"].append("Seller API: ключи не заданы")

    pid = shop.get("ozon_perf_client_id", "")
    psecret = shop.get("ozon_perf_client_secret", "")
    if pid and psecret:
        p = OzonPerformanceClient(pid, psecret)
        try:
            await p.campaigns_list()
            results["perf_ok"] = True
        except Exception as e:
            results["errors"].append(f"Performance API: {e}")
        finally:
            await p.close()
    else:
        results["errors"].append("Performance API: ключи не заданы")

    return JSONResponse(results)


@fastapi_app.get("/api/stats")
async def api_stats(shop: str | None = None):
    return JSONResponse(await stats.get_summary(shop_id=shop))


@fastapi_app.get("/api/health")
async def health():
    """Здоровье самого сервиса + сводка последних проверок Ozon API."""
    history = await stats.get_health_history(limit=5)
    degradations = await stats.get_tool_degradations()
    return JSONResponse({
        "status": "ok",
        "auth_enabled": bool(MCP_AUTH_TOKEN),
        "health_check_interval_min": HEALTH_CHECK_INTERVAL_MIN,
        "recent_checks": history,
        "degraded_tools": degradations,
    })


# ─── Точка входа ─────────────────────────────────────────────

def main():
    uvicorn.run(
        "ozon_mcp.app:fastapi_app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
