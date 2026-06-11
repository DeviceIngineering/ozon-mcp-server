"""Диагностика работоспособности MCP и Ozon API.

Уровни проверки:
  1. reachability — доступность хостов api-seller / api-performance
  2. keys         — какие ключи заданы (Seller / Performance), валидность в бою
  3. probe        — лёгкие реальные запросы по каждой категории Seller API
                    + получение токена Performance API

Плюс анализ деградаций: если инструмент стабильно работал и начал
стабильно падать — это сигнал об изменении Ozon API.

Ozon API-ключи не содержат срока действия внутри (в отличие от JWT WB),
поэтому срок истечения отслеживается только по факту 403/401.
"""

import time
import asyncio
from typing import Any

import httpx

SELLER_HOST = "https://api-seller.ozon.ru"
PERF_HOST = "https://api-performance.ozon.ru"


# ─── Доступность хостов ──────────────────────────────────────

async def check_host(name: str, url: str) -> dict[str, Any]:
    """Любой HTTP-ответ хоста = доступен (без авторизации)."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        return {
            "host": name, "url": url, "ok": True,
            "status_code": r.status_code,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        }
    except Exception as e:
        return {
            "host": name, "url": url, "ok": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": f"{type(e).__name__}: {e}",
        }


async def check_hosts() -> list[dict[str, Any]]:
    return list(await asyncio.gather(
        check_host("Seller API", SELLER_HOST),
        check_host("Performance API", PERF_HOST),
    ))


# ─── Пробы Seller API ────────────────────────────────────────

def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _iso(days_ago: int = 0) -> str:
    return time.strftime("%Y-%m-%dT00:00:00Z", time.localtime(time.time() - days_ago * 86400))


def build_probes(seller) -> list[tuple[str, str, Any]]:
    """Лёгкие реальные запросы по категориям Seller API."""
    return [
        ("Товары", "POST /v3/product/list (limit=1)",
         lambda: seller.product_list(limit=1)),
        ("Цены", "POST /v5/product/info/prices (limit=1)",
         lambda: seller.product_info_prices(limit=1)),
        ("Акции", "GET /v1/actions",
         lambda: seller.actions_list()),
        ("Рейтинг", "POST /v1/rating/summary",
         lambda: seller.rating_summary()),
        ("Аналитика", "POST /v1/analytics/turnover/stocks (limit=1)",
         lambda: seller.analytics_turnover_stocks(limit=1)),
        ("Заказы FBS", "POST /v3/posting/fbs/list (сегодня)",
         lambda: seller.posting_fbs_list(_iso(1), _iso(0), limit=1)),
        ("Финансы", "POST /v3/finance/transaction/totals (вчера)",
         lambda: seller.finance_transaction_totals(_iso(1), _iso(0))),
        ("Отзывы", "POST /v1/review/list (limit=20)",
         lambda: seller.review_list(limit=20)),
        ("Вопросы", "POST /v1/question/list (limit=20)",
         lambda: seller.question_list(limit=20)),
        ("Чаты", "POST /v3/chat/list (limit=1)",
         lambda: seller.chat_list(page_size=1)),
        ("Склады", "POST /v1/warehouse/list",
         lambda: seller.warehouse_list()),
        ("Отчёты", "POST /v1/report/list (page_size=1)",
         lambda: seller.report_list(page_size=1)),
    ]


HINTS = {
    401: "Ключ не действует (истёк или отозван) — создайте новый в ЛК Ozon",
    403: "Доступ запрещён — нет прав у ключа или нужна подписка Premium Plus",
    404: "Эндпоинт не найден — возможно, Ozon изменил API!",
    429: "Превышен лимит запросов",
}


async def run_probes(seller) -> list[dict[str, Any]]:
    """Выполнить пробы Seller API параллельно."""

    async def _run(category: str, endpoint: str, factory) -> dict[str, Any]:
        start = time.monotonic()
        try:
            await factory()
            return {
                "category": category, "endpoint": endpoint, "ok": True,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
            }
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                return {
                    "category": category, "endpoint": endpoint, "ok": True,
                    "rate_limited": True, "status_code": 429,
                    "latency_ms": round((time.monotonic() - start) * 1000, 1),
                    "note": "429: лимит запросов — API доступен",
                }
            if code == 403 and category in ("Отзывы", "Вопросы"):
                # Отсутствие Premium Plus — ограничение тарифа, а не поломка
                return {
                    "category": category, "endpoint": endpoint, "ok": True,
                    "premium_required": True, "status_code": 403,
                    "latency_ms": round((time.monotonic() - start) * 1000, 1),
                    "note": "403: нужна подписка Premium Plus",
                }
            return {
                "category": category, "endpoint": endpoint, "ok": False,
                "status_code": code, "hint": HINTS.get(code, ""),
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error": e.response.text[:300],
            }
        except Exception as e:
            return {
                "category": category, "endpoint": endpoint, "ok": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    probes = build_probes(seller)
    return list(await asyncio.gather(*[_run(c, e, f) for c, e, f in probes]))


# ─── Проба Performance API (реклама) ─────────────────────────

async def probe_performance(client_id: str, client_secret: str) -> dict[str, Any]:
    """Получить токен Performance API — проверка рекламных ключей."""
    if not client_id or not client_secret:
        return {"category": "Реклама", "ok": False, "skipped": True,
                "error": "Ключи Performance API не заданы"}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=PERF_HOST, timeout=15.0) as c:
            r = await c.post("/api/client/token", json={
                "client_id": client_id, "client_secret": client_secret,
                "grant_type": "client_credentials",
            })
            r.raise_for_status()
            data = r.json()
        return {
            "category": "Реклама", "endpoint": "POST /api/client/token", "ok": True,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "token_expires_in_sec": data.get("expires_in"),
        }
    except httpx.HTTPStatusError as e:
        return {
            "category": "Реклама", "endpoint": "POST /api/client/token", "ok": False,
            "status_code": e.response.status_code,
            "hint": "Ключи Performance API не действуют" if e.response.status_code in (401, 403) else "",
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": e.response.text[:300],
        }
    except Exception as e:
        return {
            "category": "Реклама", "endpoint": "POST /api/client/token", "ok": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": f"{type(e).__name__}: {e}",
        }


# ─── Полная самодиагностика магазина ─────────────────────────

async def full_diagnostics(shop_id: str, shop_name: str, keys: dict, seller) -> dict[str, Any]:
    """Полная диагностика: хосты + пробы Seller + токен Performance."""
    keys_info = {
        "seller_keys_set": bool(keys.get("ozon_client_id") and keys.get("ozon_api_key")),
        "perf_keys_set": bool(keys.get("ozon_perf_client_id") and keys.get("ozon_perf_client_secret")),
        "client_id": keys.get("ozon_client_id", ""),
    }

    hosts, probes, perf = await asyncio.gather(
        check_hosts(),
        run_probes(seller),
        probe_performance(keys.get("ozon_perf_client_id", ""), keys.get("ozon_perf_client_secret", "")),
    )

    host_fail = [h for h in hosts if not h["ok"]]
    probe_fail = [p for p in probes if not p["ok"]]
    perf_fail = not perf["ok"] and not perf.get("skipped")

    warnings = []
    for p in probe_fail:
        code = p.get("status_code")
        if code == 404:
            warnings.append(f"⛔ {p['category']}: 404 на {p['endpoint']} — возможно, Ozon изменил API")
        elif code == 401:
            warnings.append(f"⛔ {p['category']}: 401 — ключ Seller API не действует (истёк/отозван)!")
        elif code == 403:
            warnings.append(f"⚠️ {p['category']}: 403 — нет прав (для отзывов/чатов нужна подписка Premium Plus)")
        else:
            warnings.append(f"⛔ {p['category']}: {code or p.get('error', 'ошибка')}")
    if perf_fail:
        warnings.append(f"⛔ Реклама: ключи Performance API не работают — {perf.get('status_code') or perf.get('error')}")
    for h in host_fail:
        warnings.append(f"⛔ Хост {h['host']} недоступен: {h.get('error')}")

    # 401 по всем пробам = истёк сам ключ
    auth_fails = [p for p in probe_fail if p.get("status_code") in (401,)]
    if len(auth_fails) >= 3:
        warnings.insert(0, "⛔ КЛЮЧ SELLER API ИСТЁК ИЛИ ОТОЗВАН — все запросы падают с 401!")

    healthy = not host_fail and not probe_fail and not perf_fail

    return {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "healthy": healthy,
        "warnings": warnings,
        "keys": keys_info,
        "hosts": hosts,
        "probes": probes + [perf],
    }
