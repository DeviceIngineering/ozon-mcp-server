"""Сбор и хранение статистики вызовов MCP-инструментов."""

import aiosqlite
from pathlib import Path
from datetime import datetime

_db: aiosqlite.Connection | None = None


async def init_db(data_dir: Path):
    """Инициализировать SQLite базу статистики."""
    global _db
    data_dir.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(data_dir / "stats.db")
    _db.row_factory = aiosqlite.Row
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            duration_ms REAL,
            success BOOLEAN,
            error_text TEXT,
            shop_id TEXT DEFAULT ''
        )
    """)
    await _db.commit()

    # Миграция: добавить shop_id если таблица старая
    try:
        await _db.execute("SELECT shop_id FROM tool_calls LIMIT 1")
    except Exception:
        await _db.execute("ALTER TABLE tool_calls ADD COLUMN shop_id TEXT DEFAULT ''")
        await _db.commit()

    # История health-проверок (диагностика)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS health_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            healthy BOOLEAN,
            ping_failures INTEGER DEFAULT 0,
            probe_failures INTEGER DEFAULT 0,
            warnings TEXT DEFAULT '[]',
            detail TEXT DEFAULT '{}'
        )
    """)
    await _db.commit()


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


def is_enabled() -> bool:
    """Собирается ли статистика: init_db прошёл и база доступна.

    Нужно, чтобы отличать «деградаций нет» от «судить не по чему»:
    без этого пустая база выглядит так же, как здоровый сервер.
    """
    return _db is not None


async def record_call(
    tool_name: str, duration_ms: float, success: bool,
    error_text: str | None, shop_id: str = ""
):
    """Записать вызов инструмента."""
    if not _db:
        return
    await _db.execute(
        "INSERT INTO tool_calls (tool_name, duration_ms, success, error_text, shop_id) VALUES (?, ?, ?, ?, ?)",
        (tool_name, duration_ms, success, error_text, shop_id),
    )
    await _db.commit()


async def record_health_check(
    shop_id: str, healthy: bool, ping_failures: int,
    probe_failures: int, warnings: list, detail: dict | None = None,
):
    """Записать результат health-проверки."""
    import json
    if not _db:
        return
    await _db.execute(
        "INSERT INTO health_checks (shop_id, healthy, ping_failures, probe_failures, warnings, detail) VALUES (?, ?, ?, ?, ?, ?)",
        (shop_id, healthy, ping_failures, probe_failures,
         json.dumps(warnings, ensure_ascii=False),
         json.dumps(detail or {}, ensure_ascii=False, default=str)),
    )
    # Ротация: храним последние 1000 записей
    await _db.execute(
        "DELETE FROM health_checks WHERE id NOT IN (SELECT id FROM health_checks ORDER BY id DESC LIMIT 1000)"
    )
    await _db.commit()


async def get_health_history(shop_id: str | None = None, limit: int = 50) -> list[dict]:
    """История health-проверок (последние N)."""
    import json
    if not _db:
        return []
    where, params = ("WHERE shop_id = ?", (shop_id,)) if shop_id else ("", ())
    cur = await _db.execute(
        f"SELECT * FROM health_checks {where} ORDER BY id DESC LIMIT ?", (*params, limit)
    )
    return [
        {"shop": r["shop_id"], "at": r["checked_at"], "healthy": bool(r["healthy"]),
         "ping_failures": r["ping_failures"], "probe_failures": r["probe_failures"],
         "warnings": json.loads(r["warnings"] or "[]")}
        for r in await cur.fetchall()
    ]


async def get_last_health(shop_id: str) -> dict | None:
    """Последняя health-проверка магазина (полная, с detail)."""
    import json
    if not _db:
        return None
    cur = await _db.execute(
        "SELECT * FROM health_checks WHERE shop_id = ? ORDER BY id DESC LIMIT 1", (shop_id,)
    )
    r = await cur.fetchone()
    if not r:
        return None
    return json.loads(r["detail"] or "{}") or None


async def get_tool_degradations(min_calls: int = 3) -> list[dict]:
    """Найти инструменты, которые РАНЬШЕ работали, а ТЕПЕРЬ стабильно падают.

    Сигнал возможного изменения WB API: последние min_calls вызовов — ошибки,
    при этом ранее были успешные вызовы.
    """
    if not _db:
        return []
    cur = await _db.execute("SELECT DISTINCT tool_name FROM tool_calls")
    tools = [r["tool_name"] for r in await cur.fetchall()]

    degraded = []
    for tool in tools:
        cur = await _db.execute(
            "SELECT success, error_text, called_at FROM tool_calls WHERE tool_name = ? ORDER BY id DESC LIMIT ?",
            (tool, min_calls),
        )
        recent = await cur.fetchall()
        if len(recent) < min_calls or any(r["success"] for r in recent):
            continue
        # Последние N — все ошибки. Были ли успехи раньше?
        cur = await _db.execute(
            "SELECT COUNT(*) as cnt, MAX(called_at) as last_ok FROM tool_calls WHERE tool_name = ? AND success = 1",
            (tool,),
        )
        row = await cur.fetchone()
        if row["cnt"] > 0:
            degraded.append({
                "tool": tool,
                "last_success": row["last_ok"],
                "consecutive_errors": len(recent),
                "last_error": recent[0]["error_text"],
                "first_error_at": recent[-1]["called_at"],
            })
    return degraded


async def get_summary(shop_id: str | None = None) -> dict:
    """Агрегированная статистика. shop_id=None — все магазины."""
    if not _db:
        return {"total": 0, "today": 0, "errors": 0, "avg_ms": 0, "top_tools": [], "recent": [], "shops": []}

    where = ""
    params: tuple = ()
    if shop_id:
        where = "WHERE shop_id = ?"
        params = (shop_id,)

    cur = await _db.execute(f"SELECT COUNT(*) as cnt FROM tool_calls {where}", params)
    total = (await cur.fetchone())["cnt"]

    cur = await _db.execute(f"SELECT COUNT(*) as cnt FROM tool_calls {where} {'AND' if where else 'WHERE'} success = 0", params)
    errors = (await cur.fetchone())["cnt"]

    cur = await _db.execute(f"SELECT AVG(duration_ms) as avg FROM tool_calls {where}", params)
    row = await cur.fetchone()
    avg_ms = round(row["avg"] or 0, 1)

    # Топ-10
    cur = await _db.execute(f"""
        SELECT tool_name, COUNT(*) as cnt, AVG(duration_ms) as avg_ms,
               SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errs
        FROM tool_calls {where} GROUP BY tool_name ORDER BY cnt DESC LIMIT 10
    """, params)
    top_tools = [
        {"name": r["tool_name"], "count": r["cnt"],
         "avg_ms": round(r["avg_ms"] or 0, 1), "errors": r["errs"]}
        for r in await cur.fetchall()
    ]

    # Последние 50
    cur = await _db.execute(f"""
        SELECT tool_name, called_at, duration_ms, success, error_text, shop_id
        FROM tool_calls {where} ORDER BY id DESC LIMIT 50
    """, params)
    recent = [
        {"tool": r["tool_name"], "at": r["called_at"],
         "ms": round(r["duration_ms"] or 0, 1), "ok": bool(r["success"]),
         "error": r["error_text"], "shop": r["shop_id"]}
        for r in await cur.fetchall()
    ]

    # За сегодня
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cur = await _db.execute(
        f"SELECT COUNT(*) as cnt FROM tool_calls {where} {'AND' if where else 'WHERE'} called_at >= ?",
        (*params, today),
    )
    today_count = (await cur.fetchone())["cnt"]

    # Список магазинов в статистике
    cur = await _db.execute("SELECT DISTINCT shop_id FROM tool_calls WHERE shop_id != '' ORDER BY shop_id")
    shops = [r["shop_id"] for r in await cur.fetchall()]

    return {
        "total": total,
        "today": today_count,
        "errors": errors,
        "avg_ms": avg_ms,
        "top_tools": top_tools,
        "recent": recent,
        "shops": shops,
    }
